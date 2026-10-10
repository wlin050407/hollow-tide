# 工程结构与约定

目标：3 个人 + 多个 AI 助手同时改代码，仍然保持"主分支随时能进游戏"。

## 目录

```
hollow-tide/                       Git 仓库根目录
├─ mod/                            ★ 游戏实际加载的 Mod（通过 junction 挂到 DST mods/hollowtide）
│  ├─ modinfo.lua                  Mod 元信息与配置项（极小沙盒，见 API_NOTES）
│  ├─ modmain.lua                  入口：只做声明和分发
│  ├─ modmain/                     用 modimport 载入，运行在 Mod 环境（能用 AddXxx 系列函数）
│  │  ├─ strings.lua               所有玩家可见文本（中英文并排）
│  │  ├─ debug_hooks.lua           联机自检日志
│  │  └─ recipes.lua               （第 3 天）配方
│  ├─ scripts/
│  │  ├─ hollowtide/               本 Mod 的共享模块（require("hollowtide/xxx")，全局环境）
│  │  │  ├─ log.lua                统一日志
│  │  │  └─ tuning.lua             所有数值
│  │  ├─ prefabs/                  实体定义（游戏按 PrefabFiles 载入）
│  │  └─ components/               （需要时）自定义组件，文件名加 ht_ 前缀
│  ├─ images/                      编译后的贴图 .tex/.xml（由 tools/art/png2tex.py 生成）
│  ├─ anim/                        动画包 .zip（地面外观等；由 tools/art/make_anim.py 生成）
│  └─ exported/                    （需要时）Spriter 源工程，Mod Tools 从这里编译到 anim/
├─ art/
│  ├─ STYLE.md                     （第 1 周）视觉风格基准
│  ├─ prompts/                     每个资产的 prompt 与生成记录
│  ├─ source/                      选中的原图 / 分层源文件（大文件建议 Git LFS）
│  ├─ icons/                       规格化后的 64×64 图标 PNG（prepare_icon.py 输出）
│  ├─ provenance/asset_log.csv     资产来源与授权登记
│  ├─ _inbox/                      批量生成的原始图（不进 Git）
│  └─ review/                      脚本生成的审查预览（不进 Git）
├─ tools/
│  ├─ check_mod.py                 静态检查（语法 / modinfo / 字符串 / 资源 / API 核对）
│  ├─ link_mod.bat                 把 mod/ 挂进游戏
│  ├─ art/remove_bg.py             去纯色背景（边缘去色溢出）→ 透明 PNG
│  ├─ art/prepare_icon.py          AI 图 → 64×64 图标 + 预览
│  ├─ art/png2tex.py               PNG → DST 贴图 .tex + 图集 .xml（格式已对照原版验证）
│  ├─ art/align_stages.py          把 AI 画的破损阶段图的底座对齐到完整图
│  ├─ art/make_anim.py             PNG → 动画包 anim/*.zip（地面外观、破损阶段）+ 预览 + 原版格式自检
│  └─ art/kanim.py                 动画包 build.bin / anim.bin 读写库（make_anim 与 check_mod 共用）
├─ docs/                           设计与流程文档
├─ AGENTS.md / CLAUDE.md           AI 编程助手必须遵守的规则
└─ .github/                        CI（每次 push 自动跑 check_mod.py）+ PR 模板
```

为什么 Mod 放在 `mod/` 子目录而不是仓库根目录：上传 Workshop 时只上传 `mod/`，
文档、工具、美术源文件不会混进玩家下载的包里。

## 两种运行环境（最容易写错的地方）

| 位置 | 怎么载入 | 运行环境 | 能直接用 |
|---|---|---|---|
| `modmain.lua`、`modmain/*.lua` | 游戏 / `modimport` | **Mod 环境** | `AddRecipe2`、`AddPrefabPostInit`、`GetModConfigData`、`TUNING`……其他全局要写 `GLOBAL.xxx` |
| `scripts/**/*.lua` | `require` / PrefabFiles / AddComponent | **全局环境** | 所有游戏全局（`TheWorld`、`SpawnPrefab`……）；**不能**用 `AddXxx`、`GetModConfigData` |

需要把 Mod 配置传给 `scripts/` 里的代码时：在 modmain 里读配置，再写进共享模块（参考 `Log.SetDebug`）。

## 服务器 / 客户端规则

1. 玩法逻辑只在服务器运行：组件只在 `SetPristine()` + `ismastersim` 判断**之后**添加。
2. 客户端拿不到 `inst.components.xxx`。客户端需要知道的状态，用标签、replica 或 netvar 传。
3. netvar、标签、`GetActivateVerb` 这类两端都要有的东西，写在 `SetPristine()` **之前**。
4. 视觉表现（灯光、动画、音效）可以两端都做，但不能影响玩法结果。
5. 任何新功能都必须在**带洞穴的世界**里测过（你的游戏是纯客户端），见 TESTING.md。

## 命名

| 对象 | 规则 | 原因 |
|---|---|---|
| prefab | 小写下划线，如 `tide_crystal`；`check_mod.py` 会检查不和原版重名 | prefab 名写进玩家存档，**发布后不能改** |
| 组件 | `ht_` 前缀，如 `ht_tideevent` | 组件名是全局的，不加前缀容易和原版/其他 Mod 冲突 |
| require 模块 | 放在 `scripts/hollowtide/` 下 | 同上，`require` 的缓存是全局共享的 |
| netvar 名 | `"<prefab>.<字段>"`，如 `"tide_altar._state"` | 原版惯例 |
| 字符串键 | `STRINGS.NAMES.<PREFAB 大写>` | 原版惯例 |
| 日志 | 一律用 `hollowtide/log`，不要裸 `print` | 方便在三份日志里搜索 |

## 存档兼容（发布后才严格执行，但现在就要有意识）

- 已发布的 prefab 名、组件存档字段名不能改；必须改时写迁移代码。
- `OnSave` 只存必要状态；能从别的状态推出来的不存。
- 每个有存档的功能都要有"存档 → `c_reset()` → 验证"的测试用例。

## 分支与评审

- `main`：任何时候都能通过 `check_mod.py` 并进游戏加载。
- 每个功能一个分支：`feat/tide-altar`、`art/tide-crystal-icon`、`fix/...`。
- 合并前（PR 模板会提示）：
  1. `check_mod.py` 0 ERROR（本地带 `--game-scripts` 跑）
  2. 写明进游戏测试了什么、在什么服务器形态下、结果如何（附日志片段或截图）
  3. AI 生成的代码必须有一名成员读过并理解；新用到的 API 已补进 `docs/API_NOTES.md`
- 版本号：开发期 `0.x.y`，每次给外部测试者发版时 +1，并更新 `modinfo.lua` 的 `version`。

## 依赖

- 游戏内：不依赖任何其他 Mod，不复制其他 Mod 的代码或素材（即使开源，也要先看许可证）。
- 工具：Python 3 + `tools/requirements.txt`（lupa、Pillow、numpy、quicktex、texture2ddecoder），不引入其他依赖。

## 新增一个功能的步骤（模板）

1. 在 `docs/` 写半页设计：玩家视角流程、状态、服务器/客户端分工、存档、验收用例
2. 用到的新 API → 先在 `scripts.zip` 里找到出处 → 补进 `API_NOTES.md`
3. 数值进 `tuning.lua`，文本进 `strings.lua`（中英文）
4. 写代码 → `check_mod.py` → 进游戏（带洞穴）→ 按验收用例逐条测
5. PR → 另一名成员评审 → 合并
