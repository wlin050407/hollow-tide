# Hollow Tide 深潮异变

Hollow Lantern Studio 的第一个项目：《饥荒联机版》(Don't Starve Together) 内容扩展 Mod。
当前阶段：**第一阶段 · 第 1 周** —— 最简 Mod（M0）+ 占位物品潮蚀结晶（M1）。

## 快速开始

```bat
:: 1. 把 mod\ 挂进游戏（目录联接，不需要管理员权限）
tools\link_mod.bat

:: 2. 静态检查（需要 Python 3）
pip install -r tools\requirements.txt
python tools\check_mod.py --game-scripts "D:\Applications\Steam\steamapps\common\Don't Starve Together\data\databundles\scripts.zip"
```

3. 启动游戏 → 创建世界（保持洞穴开启）→ 模组里启用 **Hollow Tide 深潮异变 [dev]**
4. 进游戏后按 **`** 打开控制台：`c_spawn("tide_crystal")`

完整步骤和每一步的期望结果见 [docs/TESTING.md](docs/TESTING.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [PHASE1_PLAN.md](docs/PHASE1_PLAN.md) | 可行性评估、三大风险、第一周逐日计划 |
| [TESTING.md](docs/TESTING.md) | 安装、加载、测试步骤，日志怎么看，联机测试矩阵 |
| [TIDE_ALTAR_DESIGN.md](docs/TIDE_ALTAR_DESIGN.md) | 深潮祭坛的交互机制、状态机、同步与存档、验收用例 |
| [ART_PIPELINE.md](docs/ART_PIPELINE.md) | AI 图标从生成到进游戏的完整管线 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 目录结构、运行环境、服务器/客户端规则、命名、分支与评审 |
| [API_NOTES.md](docs/API_NOTES.md) | 已对照游戏源码核实的 DST API（附出处） |
| [AGENTS.md](AGENTS.md) | AI 编程助手必须遵守的规则 |

## 目录速览

```
mod/        游戏加载的 Mod 本体（上传 Workshop 时只传这个目录）
tools/      静态检查、挂载脚本、美术脚本
art/        美术源文件、prompt、来源登记
docs/       文档
```

## 版权

代码与原创美术 © Hollow Lantern Studio。本 Mod 运行时使用《饥荒联机版》的游戏资源，这些资源归 Klei Entertainment 所有，不包含在本仓库中。
