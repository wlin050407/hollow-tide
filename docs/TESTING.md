# 安装、加载与测试

适用于本机环境：DST 安装在 `D:\Applications\Steam\steamapps\common\Don't Starve Together`，
日志在 `C:\Users\ROG\Documents\Klei\DoNotStarveTogether\`。其他成员把路径换成自己的即可。

## 0. 一次性准备

1. **Git**：双击 `tools\setup_git.bat`。它会：把 `_github` 改名为 `.github` → `git init -b main` → 第一次提交
   →（可选）用 GitHub CLI 创建**私有**仓库 `hollow-tide` 并推送（会先问你 Y/N，未登录时会打开浏览器登录）。
   重复运行是安全的，已完成的步骤会自动跳过。
2. **Python 依赖**（静态检查和美术脚本用）：
   ```bat
   pip install -r tools\requirements.txt
   ```
3. **把 Mod 挂进游戏**：双击 `tools\link_mod.bat`。
   它在 `...\Don't Starve Together\mods\hollowtide` 建一个目录联接（junction）指向仓库里的 `mod\`，
   以后改仓库里的文件就是改游戏加载的文件，不需要复制。不需要管理员权限。成功后窗口 5 秒自动关闭，出错时会停住等你看信息。
   - 已在本机完成（2026-10-11）：`mods\hollowtide` → `E:\Game_Dev\hollow-tide\mod`
   - 撤销联接：在命令行运行 `rmdir "D:\Applications\Steam\steamapps\common\Don't Starve Together\mods\hollowtide"`
     （`rmdir` 不加 `/s` 只删除联接本身，不会动仓库里的文件）
   - 如果游戏里看不到这个 Mod：删掉 `mods\hollowtide`，改为把 `mod\` 文件夹整个复制过去，命名为 `hollowtide`。

## 1. 每次改完代码先跑静态检查（10 秒）

```bat
python tools\check_mod.py --game-scripts "D:\Applications\Steam\steamapps\common\Don't Starve Together\data\databundles\scripts.zip"
```

也可以设置一次环境变量，以后直接 `python tools\check_mod.py`：

```bat
setx DST_SCRIPTS "D:\Applications\Steam\steamapps\common\Don't Starve Together\data\databundles\scripts.zip"
```

必须 **0 个 ERROR** 才进游戏。它能抓到：语法错误、BOM、modinfo 写错、缺中英文名字、资源文件缺失、
以及**原版脚本里不存在的函数 / TUNING 键 / 组件方法**（AI 编造 API 的典型症状）。它不能代替进游戏测试。

## 2. M0：Mod 能被游戏加载

1. 启动 DST → 主菜单 **模组** → **服务器模组** 列表里应出现 **Hollow Tide 深潮异变 [dev]**。
   - 本地 Mod 会有"本地模组"提示，正常。
   - 点 **配置模组**：应看到"语言""调试日志"两项。
2. **开始游戏 → 创建世界**：保持**洞穴开启**（你平时就是这么开的，这正好是最好的测试环境，见下面的说明）。
   → **模组** 标签页启用 Hollow Tide → 配置里把 **调试日志** 设为开启 → 生成世界。
3. 进入游戏后，打开日志确认（用记事本或 VS Code 打开，搜索 `[HollowTide]`）：

| 日志文件 | 应该看到 |
|---|---|
| `client_log.txt` | `[HollowTide][boot] modmain loaded: version=0.0.1 folder=hollowtide` 和 `[HollowTide][client] world ready: world=forest ismastersim=false dedicated=false` |
| `master_server_log.txt` | `[HollowTide][server] world ready: world=forest ismastersim=true dedicated=true`、`shard id: 1`、`player joined: <你的名字>` |
| `caves_server_log.txt` | `[HollowTide][server] world ready: world=cave ismastersim=true dedicated=true` |

> **为什么开洞穴最好**：带洞穴的世界里，地上和洞穴是两个独立的服务器进程（`master_server_log.txt`、`caves_server_log.txt`），
> 你的游戏只是一个客户端（`ismastersim=false`）。所以你自己一个人就能测出"服务器有、客户端没有"这类联机 bug。
> 不开洞穴时，你的游戏同时是服务器和客户端，很多联机 bug 会被掩盖。

✅ **M0 完成标准**：三份日志里都有 `[HollowTide]` 行，且没有 `[HollowTide]...[WARN]` 或 Lua 报错。

## 3. M1：占位物品 Tide Crystal

在游戏里按 **`** 键（数字 1 左边）打开控制台。管理员身份下标题会显示远程执行（命令在服务器上运行），按 Ctrl 可切换。

| # | 操作 | 期望 |
|---|---|---|
| 1 | `c_spawn("tide_crystal")` | 鼠标位置出现一颗**偏青绿色**的宝石 |
| 2 | 鼠标悬停 | 显示"潮蚀结晶"（英文环境显示 Tide Crystal） |
| 3 | 捡起 | 进入物品栏；图标暂时是原版蓝宝石图标（占位，正常） |
| 4 | **右键**点物品栏里的结晶（鼠标悬停时提示"检查/Examine"） | 角色说"贴近耳边，能听见很远很远的潮声。"（台词由服务器生成：服务器语言是英文时说 "It hums like a shell held to the ear."，属正常） |
| 5 | `c_give("tide_crystal", 45)` | 分成 40 + 5 两堆（堆叠上限 40） |
| 6 | `c_save()`，等存档完成后 `c_reset()`（或：断开连接 → 完全退出游戏 → 重开读档） | 读档后物品还在，数量不变 |
| 7 | 走下洞穴，再 `c_spawn("tide_crystal")` | 洞穴里同样正常（`caves_server_log.txt` 无报错） |
| 8 | 队友加入你的世界（需要也装了这个 Mod 的本地副本） | 队友看到同样的名字和外观；`master_server_log.txt` 出现 `player joined: <队友>` |

✅ **M1 完成标准**：1–7 全部通过；8 在第 2 天队友到位后补测。

## 4. 出错了怎么办

1. **先看日志**，搜 `[HollowTide]` 和 `LUA ERROR` / `stack traceback`。
   - Mod 代码在服务器上出错 → `master_server_log.txt` / `caves_server_log.txt`
   - 客户端（显示、UI）出错 → `client_log.txt`
2. 游戏崩溃后可能会自动禁用 Mod，需要回到模组菜单重新启用。
3. 可选的开发辅助（编辑 `...\Don't Starve Together\mods\modsettings.lua`）：
   - `ForceEnableMod("hollowtide")`：每次启动都强制启用本 Mod，省去手动勾选
   - `EnableModError()`：对不规范的 Mod 写法直接报错，开发期建议开启
   - 正式游玩前记得注释掉
4. 把出错日志交给 AI 分析时，附上：出错前做了什么、相关日志片段（从第一条 `[HollowTide]` 到报错结束）、当前 git commit。
5. **已遇到过的现象（与本 Mod 无关）**
   - 同一次游戏进程里先玩过别的存档、再回主菜单开测试世界：角色隐身，`client_log.txt` 刷屏
     `Could not find anim [idle_loop] in bank [wilson]`。**完全退出游戏再重开**后，同一存档、同样启用本 Mod，一切正常。
     结论：测试前最好重启一次游戏。
   - 重开游戏后按 ` 打不开控制台（Esc 正常）。可能是输入法处于中文状态，先切到英文输入法再试；不行就重启游戏。
   - 不要在游戏运行时再次双击启动游戏：第二个进程会立刻退出，但会把 `client_log.txt` 截断，导致前面的日志丢失。

## 5. 联机测试矩阵（第 7 天用）

| 维度 | 取值 |
|---|---|
| 服务器形态 | 带洞穴（本机）/ 不带洞穴（本机主机）/ 专用服务器（Steam 工具 "Don't Starve Together Dedicated Server"） |
| 玩家数 | 1 / 2 / 4 |
| 位置 | 地上 / 洞穴 / 跨分片移动后 |
| 异常 | 事件中存档读档、事件中掉线、事件中死亡、事件中锤祭坛、禁用 Mod 后加载旧存档 |
| 兼容性 | 与你常用的客户端 Mod 一起开（Combined Status、Minimap HUD、Geometric Placement、Smart Crock Pot） |

每次测试记录：日期、git commit、服务器形态、人数、通过/失败、日志片段。失败项直接开 GitHub Issue。
