#!/usr/bin/env python3
"""
Hollow Tide 静态检查（本地和 CI 都能跑，不需要启动游戏）

检查项
  1. 所有 .lua 文件：UTF-8、无 BOM、Lua 5.1 语法可编译
  2. modinfo.lua：在和游戏相同的沙盒里（只有 locale / folder_name / ChooseTranslationTable）
     分别以英文和中文执行；检查必填字段、api_version、配置项默认值是否合法
  3. modmain.lua：在"桩环境"里分别以 en / zh / auto 三种语言设置执行，收集 PrefabFiles / Assets，
     并以服务器端、客户端两种身份执行 AddSimPostInit / AddPrefabPostInit 注册的回调
  4. prefab 文件：在桩环境里分别以服务器端、客户端身份调用一次构造函数（冒烟测试），
     检查 Mod 自带资源文件是否存在、每个 prefab 是否有中英文名字
  5. 贴图：mod/images 下的图集 .xml -> 引用的 .tex 是否存在、KTEX 文件头是否合法、尺寸是否合理
     动画包：mod/anim/*.zip 的 build.bin / anim.bin 能否完整解析、atlas 贴图是否齐全、UV 是否越界；
     prefab 里 SetBank / SetBuild / PlayAnimation 用到的名字是否真的在 Mod 自己的动画包里
  6. API 核对（需要游戏脚本，见下）：桩环境执行过程中用到的
       - 全局函数/变量          是否在原版脚本中存在
       - TUNING.XXX              是否在原版 tuning 中存在
       - modmain 环境函数        是否是 modutil.lua / mods.lua 提供的
       - AddComponent("x")       组件 x 是否存在（原版或 Mod 的 scripts/components）
       - inst.components.x:Y()   组件 x 是否有方法 Y
       - 其他方法调用 obj:Y()    方法名是否在原版脚本里出现过（只给警告）
       - AddPrefabPostInit("x")  x 是否是已知 prefab（只给警告）
       - 本 Mod 的 prefab / 组件名 是否与原版重名
     这一步专门用来拦截 AI 编造的 API。

桩环境的局限：游戏全局对象在这里都是"什么都接受"的假对象，只有实际执行到的代码路径会被核对；
它不能代替游戏内测试（不检查运行时行为、不检查联机同步）。

用法
  pip install -r tools/requirements.txt
  python tools/check_mod.py
  python tools/check_mod.py --game-scripts "D:\\...\\Don't Starve Together\\data\\databundles\\scripts.zip"
  也可以设置环境变量 DST_SCRIPTS 指向 scripts.zip（或解压后的 scripts 目录）
退出码：有 ERROR 时为 1
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "art"))
import kanim  # noqa: E402  动画包格式读写（只用标准库）

try:
    from lupa import lua51
except ImportError:  # pragma: no cover
    print("缺少依赖 lupa：请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)

# 游戏当前的 MOD_API_VERSION（scripts/mods.lua 第 6 行，build 756039 核实）。游戏更新后如有变化在这里改。
EXPECTED_API_VERSION = 10
MODINFO_REQUIRED = ["name", "description", "author", "version", "api_version"]

errors: list[str] = []
warnings: list[str] = []


def error(msg: str) -> None:
    errors.append(msg)
    print(f"  [ERROR] {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  [WARN]  {msg}")


def ok(msg: str) -> None:
    print(f"  [OK]    {msg}")


def info(msg: str) -> None:
    print(f"  [INFO]  {msg}")


# ---------------------------------------------------------------------------
# Lua 运行时与桩环境
# ---------------------------------------------------------------------------

LUA_HARNESS = r"""
local harness = {}

harness.assets = {}
harness.prefabs = {}
harness.calls = {}          -- 被调用过的假对象路径，如 "G:CreateEntity().entity.AddTransform"
harness.indexes = {}        -- 被读取过的假对象路径，如 "G:TUNING.STACK_SIZE_SMALLITEM"
harness.components = {}     -- AddComponent 的参数
harness.requires = {}       -- require 了哪些游戏自带模块（如 "prefabutil"）
harness.simpostinit = {}
harness.prefabpostinit = {}
harness.animrefs = {}       -- AnimState:SetBank / SetBuild / PlayAnimation / PushAnimation 的字符串参数

local ANIM_METHODS = { SetBank = true, SetBuild = true, PlayAnimation = true, PushAnimation = true }

-- "什么都接受"的假对象：读任何字段都返回新的假对象并缓存；可以被调用；可以被赋值。
local function make_stub(name)
    local s = {}
    return setmetatable(s, {
        __index = function(t, k)
            local path = name .. "." .. tostring(k)
            harness.indexes[path] = true
            local v = make_stub(path)
            rawset(t, k, v)
            return v
        end,
        __call = function(self, a1, a2)
            harness.calls[name] = true
            if string.sub(name, -13) == ".AddComponent" and type(a2) == "string" then
                harness.components[a2] = true
            end
            local method = string.match(name, "%.AnimState%.(%a+)$")
            if method ~= nil and ANIM_METHODS[method] and type(a2) == "string" then
                table.insert(harness.animrefs, { method = method, value = a2 })
            end
            return make_stub(name .. "()")
        end,
        __tostring = function() return "<stub " .. name .. ">" end,
        __concat = function(a, b) return tostring(a) .. tostring(b) end,
    })
end
harness.make_stub = make_stub

function harness.Asset(kind, file, param)
    local a = { type = kind, file = file }
    table.insert(harness.assets, a)
    return a
end

function harness.Prefab(name, fn, assets, deps)
    local p = { name = name, fn = fn, assets = assets or {}, deps = deps or {} }
    table.insert(harness.prefabs, p)
    return p
end

local function read_source(path)
    local f = io.open(path, "rb")
    if f == nil then return nil end
    local src = f:read("*a")
    f:close()
    if string.sub(src, 1, 3) == "\239\187\191" then src = string.sub(src, 4) end -- BOM 已在第 1 步报错
    return src
end

-- 全局环境（模拟游戏的 _G）：标准库是真的，其余全局对象是假对象（路径前缀 "G:"）。
function harness.make_global_env()
    local g = {}
    for _, k in ipairs({ "string", "table", "math", "pairs", "ipairs", "select", "unpack", "tostring",
                         "tonumber", "type", "next", "pcall", "xpcall", "error", "assert", "setmetatable",
                         "getmetatable", "rawget", "rawset", "require", "setfenv", "getfenv", "loadstring" }) do
        g[k] = _G[k]
    end
    g.print = function() end -- 静音
    g.Asset = harness.Asset
    g.Prefab = harness.Prefab
    g._G = g
    setmetatable(g, { __index = function(t, k)
        local path = "G:" .. tostring(k)
        harness.indexes[path] = true
        local v = make_stub(path)
        rawset(t, k, v)
        return v
    end })
    return g
end

function harness.set_side(g, ismastersim)
    local world = make_stub("G:TheWorld")
    rawset(world, "ismastersim", ismastersim)
    rawset(world, "prefab", "world")        -- 运行中的世界实体 prefab 名固定为 "world"
    rawset(world, "worldprefab", "forest")  -- 真正的世界类型（forest / cave）
    rawset(g, "TheWorld", world)
end

-- Mod 沙盒（模拟 mods.lua: CreateEnvironment 的字段；未列出的 AddXxx 走假对象，路径前缀 "ENV:"）
function harness.make_mod_env(g, modroot, modname, modinfo, config)
    local env = {
        pairs = pairs, ipairs = ipairs, print = function() end, math = math, table = table, type = type,
        string = string, tostring = tostring, require = require, Class = g.Class,
        TUNING = g.TUNING, GLOBAL = g, modname = modname, MODROOT = modroot,
        modinfo = modinfo, Asset = harness.Asset, Prefab = harness.Prefab, Ingredient = g.Ingredient,
    }
    env.env = env
    env.GetModConfigData = function(optionname) return config[optionname] end
    env.AddSimPostInit = function(fn) table.insert(harness.simpostinit, fn) end
    env.AddPrefabPostInit = function(prefab, fn) table.insert(harness.prefabpostinit, { prefab = prefab, fn = fn }) end
    env.modimport = function(modulename)
        if string.sub(modulename, -4) ~= ".lua" then modulename = modulename .. ".lua" end
        local src = read_source(modroot .. modulename)
        if src == nil then error("modimport: " .. modulename .. " not found") end
        local fn, err = loadstring(src, "@" .. modulename)
        if fn == nil then error(err) end
        setfenv(fn, env)
        fn()
    end
    setmetatable(env, { __index = function(t, k)
        local path = "ENV:" .. tostring(k)
        harness.indexes[path] = true
        local v = make_stub(path)
        rawset(t, k, v)
        return v
    end })
    return env
end

function harness.run_in_env(src, chunkname, env)
    local fn, err = loadstring(src, chunkname)
    if fn == nil then return false, err end
    setfenv(fn, env)
    local good, e = pcall(fn)
    return good, e
end

function harness.clear_animrefs()
    harness.animrefs = {}
end

function harness.pcall1(fn, arg)
    local good, e = pcall(fn, arg)
    return good, e
end

function harness.compile(src, chunkname)
    local fn, err = loadstring(src, chunkname)
    if fn == nil then return false, err end
    return true, nil
end

function harness.reset()
    harness.assets = {}
    harness.prefabs = {}
    harness.simpostinit = {}
    harness.prefabpostinit = {}
    harness.animrefs = {}
    for k in pairs(package.loaded) do
        if type(k) == "string" and string.find(k, "^hollowtide/") then package.loaded[k] = nil end
    end
end

-- require 的模块在游戏里运行在全局环境；这里让它们运行在桩全局环境 g 里
local current_loader_env = nil
local loader_root = nil
function harness.install_loader(g, scripts_root)
    current_loader_env = g
    if loader_root == nil then
        loader_root = scripts_root
        table.insert(package.loaders, 2, function(modname)
            local src = read_source(loader_root .. modname .. ".lua")
            if src == nil then return nil end
            local fn, err = loadstring(src, "@scripts/" .. modname .. ".lua")
            if fn == nil then error(err) end
            setfenv(fn, current_loader_env)
            return fn
        end)
        -- 最后一个加载器：Mod 里找不到的模块视为游戏自带模块（如 "prefabutil"），记录下来，返回假对象
        table.insert(package.loaders, function(modname)
            harness.requires[modname] = true
            return function() return make_stub("require:" .. modname) end
        end)
    end
end

return harness
"""


def lua_list(tbl) -> list:
    if tbl is None:
        return []
    out = []
    i = 1
    while tbl[i] is not None:
        out.append(tbl[i])
        i += 1
    return out


def lua_keys(tbl) -> set:
    return {k for k in tbl.keys()} if tbl is not None else set()


# ---------------------------------------------------------------------------
# 游戏脚本索引（用于第 6 步 API 核对）
# ---------------------------------------------------------------------------

LUA_BUILTINS = {
    "string", "table", "math", "pairs", "ipairs", "select", "unpack", "tostring", "tonumber", "type", "next",
    "pcall", "xpcall", "error", "assert", "setmetatable", "getmetatable", "rawget", "rawset", "rawequal",
    "require", "setfenv", "getfenv", "loadstring", "print", "os", "io", "debug", "coroutine", "package", "_G",
}
LUA_KEYWORDS = {
    "and", "break", "do", "else", "elseif", "end", "false", "for", "function", "if", "in", "local", "nil",
    "not", "or", "repeat", "return", "then", "true", "until", "while",
}


class GameIndex:
    def __init__(self, files: dict[str, str]):
        self.files = files
        self.globals: set[str] = set(LUA_BUILTINS)
        self.methods: set[str] = set()
        self.tuning: set[str] = set()
        self.env_fns: set[str] = set()
        self.components: dict[str, set[str]] = {}
        self.prefabs: set[str] = set()

        re_gfunc = re.compile(r"^function\s+([A-Za-z_]\w*)\s*\(", re.M)
        re_gassign = re.compile(r"^([A-Za-z_]\w*)\s*=", re.M)
        re_gcall = re.compile(r"(?<![\w.:])([A-Za-z_]\w*)\s*\(")
        re_engine = re.compile(r"\b(The[A-Z]\w*)\b")
        re_methods = re.compile(r"[:.]([A-Za-z_]\w*)\s*\(")
        re_tuning_set = re.compile(r"TUNING\.([A-Z0-9_]+)\s*=")
        re_prefab = re.compile(r"(?:Prefab|MakePlacer|MakeWorld)\(\s*\"([\w]+)\"")
        re_comp_method = re.compile(r"^function\s+\w+[:.](\w+)\s*\(", re.M)

        for path, src in files.items():
            self.globals.update(re_gfunc.findall(src))
            self.globals.update(re_gassign.findall(src))
            self.globals.update(n for n in re_gcall.findall(src) if n not in LUA_KEYWORDS)
            self.globals.update(re_engine.findall(src))
            self.methods.update(re_methods.findall(src))
            self.tuning.update(re_tuning_set.findall(src))
            self.prefabs.update(re_prefab.findall(src))
            m = re.match(r"^scripts/components/(\w+)\.lua$", path)
            if m:
                self.components[m.group(1)] = set(re_comp_method.findall(src))

        # fx.lua 里的特效表由 prefabs/fx.lua 批量生成 prefab（如 mining_moonglass_fx），名字不在 Prefab("...") 里
        self.prefabs.update(re.findall(r'^\s*name\s*=\s*"(\w+)"', files.get("scripts/fx.lua", ""), re.M))

        tuning_src = files.get("scripts/tuning.lua", "")
        self.tuning.update(re.findall(r"^\s+([A-Z][A-Z0-9_]*)\s*=", tuning_src, re.M))

        self.env_fns.update(re.findall(r"env\.(\w+)\s*=", files.get("scripts/modutil.lua", "")))
        mods_src = files.get("scripts/mods.lua", "")
        m = re.search(r"function CreateEnvironment\(.*?env\.env = env", mods_src, re.S)
        if m:
            self.env_fns.update(re.findall(r"(\w+)\s*=", m.group(0)))
            self.env_fns.update(re.findall(r"env\.(\w+)\s*=", m.group(0)))

    @staticmethod
    def load(location: Path) -> "GameIndex":
        files: dict[str, str] = {}
        if location.is_file() and zipfile.is_zipfile(location):
            with zipfile.ZipFile(location) as z:
                for name in z.namelist():
                    if name.endswith(".lua"):
                        files[name] = z.read(name).decode("utf-8", errors="replace")
        elif location.is_dir():
            base = location.parent if location.name == "scripts" else location
            for p in location.rglob("*.lua"):
                files[p.relative_to(base).as_posix()] = p.read_text(encoding="utf-8", errors="replace")
        else:
            raise FileNotFoundError(location)
        if "scripts/mods.lua" not in files:
            raise FileNotFoundError(f"{location} 里没有找到 scripts/mods.lua，确认是 DST 的 scripts.zip")
        return GameIndex(files)


def find_game_scripts(arg: str | None) -> Path | None:
    candidates = [arg, os.environ.get("DST_SCRIPTS")]
    for c in candidates:
        if c:
            return Path(c)
    return None


# ---------------------------------------------------------------------------
# 1. 语法与编码
# ---------------------------------------------------------------------------

def check_lua_files(harness, mod: Path) -> dict[Path, str]:
    print("\n[1] Lua 文件编码与语法")
    sources: dict[Path, str] = {}
    errors_before = len(errors)
    files = sorted(mod.rglob("*.lua"))
    if not files:
        error(f"{mod} 下没有找到任何 .lua 文件")
    for f in files:
        rel = f.relative_to(mod).as_posix()
        raw = f.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            error(f"{rel}: 文件带 UTF-8 BOM，游戏会报语法错误。请另存为 UTF-8（无 BOM）")
            raw = raw[3:]
        try:
            src = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            error(f"{rel}: 不是合法的 UTF-8 编码（{e}）")
            continue
        good, err = harness.compile(src, "@" + rel)
        if not good:
            error(f"{rel}: 语法错误 -> {err}")
        sources[f] = src
    if len(errors) == errors_before:
        ok(f"{len(files)} 个 .lua 文件全部可编译")
    return sources


# ---------------------------------------------------------------------------
# 2. modinfo.lua
# ---------------------------------------------------------------------------

def check_modinfo(lua, harness, mod: Path, sources: dict[Path, str]):
    print("\n[2] modinfo.lua")
    path = mod / "modinfo.lua"
    if path not in sources:
        error("缺少 modinfo.lua")
        return None
    result = None
    make_env = lua.eval("function(loc, folder) return { locale = loc, folder_name = folder, "
                        "ChooseTranslationTable = function(tbl) return tbl[loc] or tbl[1] end } end")
    for locale in ("en", "zh"):
        env = make_env(locale, mod.name)
        good, err = harness.run_in_env(sources[path], "@modinfo.lua", env)
        if not good:
            error(f"modinfo.lua 在 locale={locale} 下执行失败（这里不能用 string/table 等标准库）: {err}")
            continue
        for field in MODINFO_REQUIRED:
            if env[field] is None:
                error(f"modinfo.lua (locale={locale}) 缺少必填字段 {field}")
        if env["api_version"] != EXPECTED_API_VERSION:
            error(f"api_version = {env['api_version']}，当前游戏为 {EXPECTED_API_VERSION}")
        if env["dst_compatible"] is not True:
            warn("dst_compatible 不是 true")
        if env["client_only_mod"] and env["all_clients_require_mod"]:
            error("client_only_mod 和 all_clients_require_mod 不能同时为 true")
        for opt in lua_list(env["configuration_options"]):
            name = opt["name"]
            datas = [o["data"] for o in lua_list(opt["options"])]
            if not datas:
                error(f"配置项 {name} 没有 options")
            elif opt["default"] not in datas:
                error(f"配置项 {name} 的 default={opt['default']!r} 不在 options 里 {datas!r}")
        if locale == "en":
            result = env
    if result is not None:
        ok(f"name={result['name']!r} version={result['version']!r} api_version={result['api_version']}")
    return result


def default_config(modinfo) -> dict:
    cfg = {}
    if modinfo is None:
        return cfg
    for opt in lua_list(modinfo["configuration_options"]):
        cfg[opt["name"]] = opt["default"]
    return cfg


# ---------------------------------------------------------------------------
# 3 & 4. modmain + prefabs
# ---------------------------------------------------------------------------

def run_postinits(harness, genv, label: str) -> None:
    for side, mastersim in (("server", True), ("client", False)):
        harness.set_side(genv, mastersim)
        for fn in lua_list(harness.simpostinit):
            good, err = harness.pcall1(fn, None)
            if not good:
                error(f"{label}: AddSimPostInit 回调在 {side} 端执行出错 -> {err}")
        for entry in lua_list(harness.prefabpostinit):
            good, err = harness.pcall1(entry["fn"], harness.make_stub("G:CreateEntity()"))
            if not good:
                error(f"{label}: AddPrefabPostInit({entry['prefab']!r}) 回调在 {side} 端执行出错 -> {err}")


def check_modmain_and_prefabs(lua, harness, mod: Path, sources: dict[Path, str], modinfo) -> dict:
    print("\n[3] modmain.lua（桩环境，language = en / zh / auto）")
    found = {"prefabs": [], "postinit_targets": [], "deps": {}}
    modmain = mod / "modmain.lua"
    if modmain not in sources:
        error("缺少 modmain.lua")
        return found

    if modinfo is None:  # modinfo 失败时用一个最小替身，继续检查后面的内容
        modinfo = lua.table_from({"version": "?", "configuration_options": lua.table_from({})})

    modroot = mod.as_posix() + "/"
    names_by_lang: dict[str, dict] = {}
    prefab_files: list[str] = []
    mod_assets: list[tuple[str, str]] = []
    modmain_failed = False

    for lang in ("en", "zh", "auto"):
        harness.reset()
        genv = harness.make_global_env()
        config = default_config(modinfo)
        config["language"] = lang
        env = harness.make_mod_env(genv, modroot, mod.name, modinfo, lua.table_from(config))
        harness.install_loader(genv, modroot + "scripts/")
        good, err = harness.run_in_env(sources[modmain], "@modmain.lua", env)
        if not good:
            error(f"modmain.lua (language={lang}) 执行失败: {err}")
            modmain_failed = True
            continue
        run_postinits(harness, genv, "modmain")
        prefab_files = [str(p) for p in lua_list(env["PrefabFiles"])]
        mod_assets = [(a["type"], a["file"]) for a in lua_list(env["Assets"])]
        found["postinit_targets"] = [e["prefab"] for e in lua_list(harness.prefabpostinit)]
        if lang != "auto":
            names = genv["STRINGS"]["NAMES"]
            names_by_lang[lang] = {k: v for k, v in names.items() if isinstance(v, str)}

    if modmain_failed:
        return found
    ok(f"PrefabFiles = {prefab_files}")

    for kind, file in mod_assets:
        if not (mod / file).exists():
            error(f"modmain Assets 引用了不存在的文件: {kind} {file}")

    print("\n[4] prefab 文件（桩环境冒烟测试：服务器端 + 客户端各执行一次构造函数）")
    for pf in prefab_files:
        path = mod / "scripts" / "prefabs" / f"{pf}.lua"
        if path not in sources:
            error(f"PrefabFiles 里的 {pf!r} 找不到文件 scripts/prefabs/{pf}.lua")
            continue
        harness.reset()
        genv = harness.make_global_env()
        harness.install_loader(genv, modroot + "scripts/")
        good, err = harness.run_in_env(sources[path], f"@scripts/prefabs/{pf}.lua", genv)
        if not good:
            error(f"scripts/prefabs/{pf}.lua 载入失败: {err}")
            continue
        prefabs = lua_list(harness.prefabs)
        if not prefabs:
            error(f"scripts/prefabs/{pf}.lua 没有 return 任何 Prefab")
        for p in prefabs:
            name = p["name"]
            found["prefabs"].append(name)
            found["deps"][name] = [str(d) for d in lua_list(p["deps"])]
            harness.clear_animrefs()
            for side, mastersim in (("server", True), ("client", False)):
                harness.set_side(genv, mastersim)
                good, err = harness.pcall1(p["fn"], None)
                if not good:
                    error(f"prefab {name}: 构造函数在 {side} 端执行出错 -> {err}")
            # 服务器端和客户端各执行一次，调用序列相同：去重但保持顺序（SetBank 要在 PlayAnimation 之前）
            refs = list(dict.fromkeys((r["method"], r["value"]) for r in lua_list(harness.animrefs)))
            check_anim_refs(mod, name, refs, [a["file"] for a in lua_list(p["assets"]) if a["type"] == "ANIM"])
            for a in lua_list(p["assets"]):
                file = a["file"]
                if (mod / file).exists():
                    continue
                if file.startswith(("anim/", "images/", "sound/", "minimap/", "bigportraits/")):
                    info(f"prefab {name}: {file} 不在 Mod 内，视为原版资源（游戏内验证）")
                else:
                    error(f"prefab {name}: 资源路径无法识别 {file}")
            upper = name.upper()
            if not name.endswith("_placer"):
                for lang, names in names_by_lang.items():
                    if upper not in names:
                        error(f"prefab {name}: 缺少 STRINGS.NAMES.{upper}（language={lang}）")
            ok(f"prefab {name}: 构造函数可执行，名称 en={names_by_lang.get('en', {}).get(upper)!r} "
               f"zh={names_by_lang.get('zh', {}).get(upper)!r}")
    return found


# ---------------------------------------------------------------------------
# 5. 贴图
# ---------------------------------------------------------------------------

KTEX_COMPRESSION = {0: "DXT1", 1: "DXT3", 2: "DXT5", 4: "RGBA", 5: "RGB"}


def read_ktex(path: Path) -> dict:
    return read_ktex_bytes(path.read_bytes())


def read_ktex_bytes(data: bytes) -> dict:
    if len(data) < 8 or data[:4] != b"KTEX":
        raise ValueError("不是 KTEX 文件（缺少 'KTEX' 文件头）")
    word = struct.unpack("<I", data[4:8])[0]
    result = {
        "platform": word & 0xF,
        "compression": (word >> 4) & 0x1F,
        "texture_type": (word >> 9) & 0xF,
        "mipmaps": (word >> 13) & 0x1F,
        "flags": (word >> 18) & 0x3,
    }
    offset = 8
    mips = []
    for _ in range(result["mipmaps"]):
        w, h, _pitch, size = struct.unpack("<HHHI", data[offset:offset + 10])
        mips.append((w, h, size))
        offset += 10
    expected = offset + sum(m[2] for m in mips)
    if expected != len(data):
        raise ValueError(f"文件长度 {len(data)} 与 mipmap 描述 {expected} 不符（文件可能损坏）")
    result["width"], result["height"] = (mips[0][0], mips[0][1]) if mips else (0, 0)
    return result


def check_textures(mod: Path) -> None:
    print("\n[5] 贴图、图集与动画包")
    images = mod / "images"
    xmls = sorted(images.rglob("*.xml")) if images.exists() else []
    pngs = sorted(images.rglob("*.png")) if images.exists() else []
    if not xmls and not pngs:
        info("mod/images 下还没有贴图（使用原版占位图标阶段）")
    for x in xmls:
        rel = x.relative_to(mod).as_posix()
        try:
            root = ET.parse(x).getroot()
        except ET.ParseError as e:
            error(f"{rel}: XML 解析失败 {e}")
            continue
        tex_node = root.find("Texture")
        if root.tag != "Atlas" or tex_node is None:
            error(f"{rel}: 不是合法的图集（需要 <Atlas><Texture filename=.../>）")
            continue
        tex = x.parent / tex_node.get("filename", "")
        if not tex.exists():
            error(f"{rel}: 引用的贴图 {tex.name} 不存在")
            continue
        try:
            tinfo = read_ktex(tex)
        except ValueError as e:
            error(f"{tex.relative_to(mod).as_posix()}: {e}")
            continue
        comp = KTEX_COMPRESSION.get(tinfo["compression"], f"未知({tinfo['compression']})")
        elements = root.findall("Elements/Element")
        if not elements:
            error(f"{rel}: 图集里没有任何 <Element>")
        for el in elements:
            for k in ("u1", "u2", "v1", "v2"):
                try:
                    v = float(el.get(k, "nan"))
                except ValueError:
                    v = float("nan")
                if not 0.0 <= v <= 1.0:
                    error(f"{rel}: Element {el.get('name')} 的 {k}={el.get(k)} 不在 0..1 之间")
        names = [el.get("name") for el in elements]
        ok(f"{rel}: {tex.name} {tinfo['width']}x{tinfo['height']} {comp} mipmaps={tinfo['mipmaps']} elements={names}")
        if "inventoryimages" in rel and len(elements) == 1 and (tinfo["width"], tinfo["height"]) != (64, 64):
            warn(f"{rel}: 物品栏图标通常是 64x64（原版图集每格 64px），当前 {tinfo['width']}x{tinfo['height']}")
    for p in pngs:
        if not p.with_suffix(".tex").exists():
            warn(f"{p.relative_to(mod).as_posix()}: 还没有对应的 .tex（需要用 Mod Tools 或 ktech 转换）")
    check_anim_zips(mod)


# ---------------------------------------------------------------------------
# 动画包（mod/anim/*.zip）
# ---------------------------------------------------------------------------

_anim_cache: dict[Path, dict] = {}


def load_anim_zip(path: Path) -> dict:
    """解析一个动画包，结果缓存。返回 {"build", "anim", "atlases", "error"}。"""
    if path in _anim_cache:
        return _anim_cache[path]
    out = {"build": None, "anim": None, "atlases": {}, "error": None}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "build.bin" not in names and "anim.bin" not in names:
                raise kanim.FormatError("zip 里既没有 build.bin 也没有 anim.bin")
            if "build.bin" in names:
                out["build"] = kanim.read_build(z.read("build.bin"))
                for a in out["build"].atlases:
                    out["atlases"][a] = z.read(a) if a in names else None
            if "anim.bin" in names:
                out["anim"] = kanim.read_anim(z.read("anim.bin"))
    except (zipfile.BadZipFile, kanim.FormatError, OSError) as e:
        out["error"] = str(e)
    _anim_cache[path] = out
    return out


def mod_anim_zips(mod: Path) -> list[Path]:
    d = mod / "anim"
    return sorted(d.glob("*.zip")) if d.exists() else []


def check_anim_zips(mod: Path) -> None:
    for path in mod_anim_zips(mod):
        rel = path.relative_to(mod).as_posix()
        z = load_anim_zip(path)
        if z["error"]:
            error(f"{rel}: 无法解析 -> {z['error']}")
            continue
        build, anim = z["build"], z["anim"]
        problems_before = len(errors)
        parts = []
        if build is not None:
            for atlas, data in z["atlases"].items():
                if data is None:
                    error(f"{rel}: build 引用的贴图 {atlas} 不在 zip 里")
                    continue
                try:
                    tinfo = read_ktex_bytes(data)
                except ValueError as e:
                    error(f"{rel}/{atlas}: {e}")
                    continue
                parts.append(f"{atlas} {tinfo['width']}x{tinfo['height']} "
                             f"{KTEX_COMPRESSION.get(tinfo['compression'], '?')} mipmaps={tinfo['mipmaps']}")
            for sym in build.symbols:
                symname = build.names.get(sym.hash)
                if symname is None:
                    error(f"{rel}: symbol hash {sym.hash:#x} 在名字表里找不到")
                elif kanim.strhash(symname) != sym.hash:
                    error(f"{rel}: symbol {symname!r} 的 hash 与名字不符")
                for f in sym.frames:
                    for x, y, _z, u, v, w in f.verts:
                        if not (-1e-4 <= u <= 1 + 1e-4 and -1e-4 <= v <= 1 + 1e-4):
                            error(f"{rel}: symbol {symname} 第 {f.framenum} 帧的 UV ({u:.4f}, {v:.4f}) 越界")
                            break
                        if int(w) >= len(build.atlases):
                            error(f"{rel}: symbol {symname} 引用了第 {int(w)} 张贴图，但 build 只有 {len(build.atlases)} 张")
                            break
            hashes = [s.hash for s in build.symbols]
            if hashes != sorted(hashes):
                error(f"{rel}: build 里的 symbol 没有按 hash 升序排列（原版都是升序，游戏可能按此查找）")
            parts.insert(0, f"build {build.name!r}（{len(build.symbols)} 个 symbol）")
        if anim is not None:
            build_syms = {s.hash for s in build.symbols} if build is not None else None
            for a in anim.anims:
                if a.bank not in anim.names:
                    error(f"{rel}: 动画 {a.name!r} 的 bank hash 在名字表里找不到")
                if build_syms is not None:
                    missing = {e.symbol for f in a.frames for e in f.elements} - build_syms
                    for h in sorted(missing):
                        warn(f"{rel}: 动画 {a.name!r} 用到的 symbol {anim.names.get(h, hex(h))!r} 不在同一个包的 build 里"
                             f"（如果是故意引用别的 build 可以忽略）")
            banks = sorted({anim.names.get(a.bank, hex(a.bank)) for a in anim.anims})
            parts.append(f"bank {banks} 动画 {[a.name for a in anim.anims][:8]}")
        if len(errors) == problems_before:
            ok(f"{rel}: " + "；".join(parts))


def check_anim_refs(mod: Path, prefab: str, refs: list[tuple[str, str]], anim_assets: list[str]) -> None:
    """prefab 构造函数里写死的 bank / build / 动画名，是否能在 Mod 自己的动画包里找到。"""
    if not refs:
        return
    own_assets = [a for a in anim_assets if (mod / a).exists()]
    vanilla_assets = [a for a in anim_assets if not (mod / a).exists()]
    builds, banks = set(), {}
    for path in [mod / a for a in own_assets]:
        z = load_anim_zip(path)
        if z["error"]:
            return  # 包本身坏了，第 5 步会报错；这里不再重复报一串找不到
        if z["build"] is not None:
            builds.add(z["build"].name.lower())
        if z["anim"] is not None:
            for a in z["anim"].anims:
                banks.setdefault(a.bank, set()).add(a.name)
    # 只有当这个 prefab 的 ANIM 资源全部来自 Mod 时，找不到才算错误；否则可能是原版资源（只能进游戏验证）
    strict = bool(own_assets) and not vanilla_assets
    report = error if strict else info
    bank = None
    for method, value in refs:
        if method == "SetBuild" and value.lower() not in builds:
            report(f"prefab {prefab}: SetBuild({value!r}) 在 Mod 的动画包 {own_assets} 里找不到这个 build")
        elif method == "SetBank":
            bank = kanim.strhash(value)
            if bank not in banks:
                report(f"prefab {prefab}: SetBank({value!r}) 在 Mod 的动画包 {own_assets} 里找不到这个 bank")
        elif method in ("PlayAnimation", "PushAnimation") and bank in banks and value not in banks[bank]:
            error(f"prefab {prefab}: {method}({value!r}) —— bank 里只有动画 {sorted(banks[bank])}")


# ---------------------------------------------------------------------------
# 6. API 核对
# ---------------------------------------------------------------------------

def mod_components(mod: Path) -> dict[str, set[str]]:
    out = {}
    comp_dir = mod / "scripts" / "components"
    if comp_dir.exists():
        for p in comp_dir.glob("*.lua"):
            src = p.read_text(encoding="utf-8", errors="replace")
            out[p.stem] = set(re.findall(r"^function\s+\w+[:.](\w+)\s*\(", src, re.M))
    return out


def check_api(harness, mod: Path, game: GameIndex | None, found: dict) -> None:
    print("\n[6] API 核对（拦截编造的 API）")
    if game is None:
        info("未提供游戏脚本，跳过。用 --game-scripts 或环境变量 DST_SCRIPTS 指向 scripts.zip 以启用")
        return
    errors_before, warnings_before = len(errors), len(warnings)
    own_components = mod_components(mod)
    all_components = {**game.components, **own_components}
    own_prefabs = set(found.get("prefabs", []))

    indexes = sorted(lua_keys(harness.indexes))
    calls = sorted(lua_keys(harness.calls))

    seen_globals: set[str] = set()
    for path in indexes + calls:
        if path.startswith("G:"):
            root = re.split(r"[.(]", path[2:], maxsplit=1)[0]
            if root not in seen_globals:
                seen_globals.add(root)
                if root not in game.globals:
                    error(f"全局名 {root!r} 在原版脚本里不存在（可能是编造的 API 或拼写错误）")
            m = re.match(r"^G:TUNING\.([A-Za-z0-9_]+)$", path)
            if m and m.group(1) not in game.tuning:
                error(f"TUNING.{m.group(1)} 在原版 tuning 中不存在")
        elif path.startswith("ENV:"):
            root = re.split(r"[.(]", path[4:], maxsplit=1)[0]
            if "ENV:" + root not in seen_globals:
                seen_globals.add("ENV:" + root)
                if root not in game.env_fns:
                    error(f"modmain 环境里没有 {root!r}（不是 modutil.lua / mods.lua 提供的函数）")

    for name in sorted(own_prefabs):
        if name in game.prefabs:
            error(f"prefab 名 {name!r} 与原版重名：会覆盖原版内容，且发布后存档里无法改名")
    for comp in own_components:
        if comp in game.components:
            error(f"组件名 {comp!r} 与原版重名：会替换原版组件。Mod 组件请加前缀，如 ht_{comp}")

    for modname in sorted(lua_keys(harness.requires)):
        if f"scripts/{modname}.lua" not in game.files:
            error(f"require({modname!r})：Mod 和原版脚本里都没有这个模块")

    for comp in sorted(lua_keys(harness.components)):
        if comp not in all_components:
            error(f"AddComponent({comp!r})：原版和 Mod 的 scripts/components 里都没有这个组件")

    for path in calls:
        m = re.search(r"\.components\.(\w+)\.(\w+)$", path)
        if m:
            comp, method = m.groups()
            if comp in all_components and method not in all_components[comp]:
                error(f"组件 {comp} 没有方法 {method}()（components/{comp}.lua 中未定义）")
            continue
        m = re.search(r"\.(\w+)$", path)
        if m and m.group(1) not in game.methods:
            warn(f"方法 {m.group(1)}() 在原版脚本里从未出现过：{path}（引擎方法也可能如此，请人工确认）")

    for name, deps in found.get("deps", {}).items():
        for dep in deps:
            if dep not in game.prefabs and dep not in own_prefabs:
                error(f"prefab {name} 的依赖 {dep!r} 在原版和本 Mod 里都找不到（拼写错误？）")

    for target in found.get("postinit_targets", []):
        if target not in game.prefabs and target not in own_prefabs:
            warn(f"AddPrefabPostInit({target!r})：原版和本 Mod 里都没有找到这个 prefab 名（动态生成的名字可能误报）")

    if len(errors) == errors_before and len(warnings) == warnings_before:
        ok(f"执行路径上用到的 {len(seen_globals)} 个全局名、{len(lua_keys(harness.components))} 个组件、"
           f"{len(calls)} 处调用全部能在原版脚本中找到")


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Hollow Tide 静态检查")
    repo = Path(__file__).resolve().parent.parent
    parser.add_argument("--mod", type=Path, default=repo / "mod", help="Mod 目录（默认：仓库里的 mod/）")
    parser.add_argument("--game-scripts", help="DST 的 data/databundles/scripts.zip 或解压后的 scripts 目录")
    args = parser.parse_args()
    mod: Path = args.mod.resolve()
    print(f"检查 Mod 目录: {mod}")

    game = None
    loc = find_game_scripts(args.game_scripts)
    if loc is not None:
        try:
            game = GameIndex.load(loc)
            print(f"游戏脚本: {loc}（{len(game.files)} 个文件）")
        except (FileNotFoundError, zipfile.BadZipFile) as e:
            error(f"无法读取游戏脚本 {loc}: {e}")

    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    harness = lua.execute(LUA_HARNESS)

    sources = check_lua_files(harness, mod)
    modinfo = check_modinfo(lua, harness, mod, sources)
    found = check_modmain_and_prefabs(lua, harness, mod, sources, modinfo)
    check_textures(mod)
    check_api(harness, mod, game, found)

    print(f"\n结果：{len(errors)} 个错误，{len(warnings)} 个警告")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
