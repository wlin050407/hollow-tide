-- modmain.lua —— Mod 入口
--
-- 运行环境：这是 Mod 的沙盒环境（env），不是全局 _G。
--   * 能直接用：PrefabFiles / Assets / modimport / GetModConfigData / AddPrefabPostInit / AddRecipe2 /
--     AddSimPostInit / Asset / Prefab / Ingredient / TUNING / require / print / pairs ... （见 mods.lua: CreateEnvironment
--     与 modutil.lua: InsertPostInitFunctions）
--   * 其余全局对象（STRINGS、TheWorld、TheNet、SpawnPrefab ...）必须通过 GLOBAL 访问。
--
-- 约定：本文件只做"声明 + 分发"。具体逻辑放在：
--   modmain/*.lua            用 modimport 载入，运行在 Mod 沙盒（能用 AddXxx 系列函数）
--   scripts/hollowtide/*.lua  用 require 载入，运行在全局环境（prefab 和 component 也能 require）
--   scripts/prefabs/*.lua     游戏按 PrefabFiles 载入
--   scripts/components/*.lua  游戏在 AddComponent 时按名字载入

local Log = require("hollowtide/log")
Log.SetDebug(GetModConfigData("debug_log") == true)

PrefabFiles =
{
    "tide_crystal",
    "tide_crystal_cluster",
}

-- Mod 自己的贴图/动画资源在这里声明（prefab 专用的资源写在各自 prefab 文件里）。
-- 物品栏图标：tools/art/png2tex.py 生成，见 docs/ART_PIPELINE.md。
Assets =
{
    Asset("ATLAS", "images/inventoryimages/tide_crystal.xml"),
    Asset("IMAGE", "images/inventoryimages/tide_crystal.tex"),
}

-- 在顶层注册（早于任何图标查询），并传 resolve 之后的路径（见 docs/API_NOTES.md「物品栏图标」）。
-- 注册后，prefab 不需要设置 imagename / atlasname：默认图片名就是 "<prefab>.tex"。
RegisterInventoryItemAtlas(GLOBAL.resolvefilepath("images/inventoryimages/tide_crystal.xml"), "tide_crystal.tex")

modimport("modmain/strings")
modimport("modmain/debug_hooks")

Log.Info("modmain loaded: version=%s folder=%s", modinfo.version, modname)
