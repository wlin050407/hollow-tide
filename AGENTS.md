# AI 编程助手规则（Codex / Cursor / Copilot / Claude 等通用）

本仓库是《饥荒联机版》（Don't Starve Together, DST）Mod "Hollow Tide 深潮异变"。
DST 没有官方 API 文档，AI 很容易编造不存在的函数。以下规则必须遵守。

## 写代码之前

0. 先读 `docs/STATUS.md`：当前进度、本机路径、用户已经定下的决定和偏好（不要重复问已经定了的事）。
1. **不要凭记忆写 DST API。** 先查 `docs/API_NOTES.md`；那里没有的，在游戏脚本
   （`<DST安装目录>/data/databundles/scripts.zip`）里找到出处，补进 `API_NOTES.md`，再写代码。
2. 先读 `docs/ARCHITECTURE.md`：两种运行环境（Mod 环境 vs 全局环境）、服务器/客户端规则、命名规则。
3. 功能设计看 `docs/` 下对应的设计文档；没有设计文档的功能先写半页设计再动手。

## 写代码时

- `modmain.lua` 只做声明和分发；逻辑放 `modmain/*.lua`（modimport）或 `scripts/hollowtide/*.lua`（require）。
- modmain 环境里访问游戏全局要写 `GLOBAL.xxx`。
- prefab：两端共有的声明（含 netvar、标签）写在 `inst.entity:SetPristine()` 之前；组件写在 `if not TheWorld.ismastersim then return inst end` 之后。
- 客户端代码不能访问 `inst.components`。
- 数值只写在 `scripts/hollowtide/tuning.lua`；玩家可见文字只写在 `modmain/strings.lua`，中英文都要有。
- 日志用 `require("hollowtide/log")`，不要裸 `print`。
- 自定义组件文件名加 `ht_` 前缀；prefab 名不能和原版重名。
- 文件保存为 UTF-8 **无 BOM**。
- 不要引入新的第三方依赖；不要复制其他 Mod 的代码或素材。
- 一次只做一个可以进游戏验证的小步，不要一次生成大量无法测试的代码。

## 写完之后

1. 运行：`python tools/check_mod.py --game-scripts "<scripts.zip 路径>"`（或设置环境变量 `DST_SCRIPTS`），必须 0 ERROR。
   改了祭坛（`tide_altar`）的逻辑或数值时，再跑 `python tools/sim_altar.py`，必须全部通过（check_mod 不执行回调）。
2. 给出**进游戏的测试步骤**（控制台命令 + 期望结果 + 要看哪份日志），格式参考 `docs/TESTING.md`。
3. 明确列出：本次新用到的 API 及其在游戏脚本中的出处；哪些地方没有验证过。
4. 更新 `docs/STATUS.md`（做了什么、用户反馈、待验证什么）。
