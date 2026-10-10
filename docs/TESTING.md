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
| 1 | `c_spawn("tide_crystal")` | 鼠标位置出现**原创的潮蚀结晶**（一块斜着的青绿色结晶，根部有两个藤壶）；不是原版宝石 |
| 1a | 旁边 `c_spawn("bluegem")`、`c_spawn("flint")` 对比 | 大小和原版掉落物相当；结晶边缘没有白边/黑边/紫边；不悬空、不陷进地里太多。颜色会被季节滤镜改变（秋天偏绿，见「出错了怎么办」），旁边的原版蓝宝石也会一起变色 |
| 1b | 走到海边，鼠标指向海面 `c_spawn("tide_crystal")` | 结晶浮在水面上，有一圈水花特效；不消失、不沉底 |
| 2 | 鼠标悬停 | 显示"潮蚀结晶"（英文环境显示 Tide Crystal） |
| 3 | 捡起；再从物品栏丢到地上 | 进入物品栏，图标是原创的潮蚀结晶图标；丢下后地面外观同第 1 步 |
| 4 | **右键**点物品栏里的结晶（鼠标悬停时提示"检查/Examine"） | 角色说"贴近耳边，能听见很远很远的潮声。"（台词由服务器生成：服务器语言是英文时说 "It hums like a shell held to the ear."，属正常） |
| 5 | `c_give("tide_crystal", 45)` | 分成 40 + 5 两堆（堆叠上限 40） |
| 6 | `c_save()`，等存档完成后 `c_reset()`（或：断开连接 → 完全退出游戏 → 重开读档） | 读档后物品还在，数量不变 |
| 7 | 走下洞穴，再 `c_spawn("tide_crystal")` | 洞穴里同样正常（`caves_server_log.txt` 无报错） |
| 8 | 队友加入你的世界（需要也装了这个 Mod 的本地副本） | 队友看到同样的名字和外观；`master_server_log.txt` 出现 `player joined: <队友>` |

✅ **M1 完成标准**：1–7 全部通过，`client_log.txt` 里没有 `Could not find anim` 之类和动画有关的报错；8 在第 2 天队友到位后补测。

### 潮蚀晶簇（可开采，设计见 `docs/TIDE_CRYSTAL_CLUSTER_DESIGN.md`）

| # | 操作 | 期望 |
|---|---|---|
| C1 | `c_spawn("tide_crystal_cluster")` | 出现一簇长在石块上的青绿色晶体，约有原版巨石一半大；角色走过去会被挡住 |
| C2 | 鼠标悬停 | 显示"潮蚀晶簇"（Tide Crystal Cluster）；没拿镐时没有"开采"选项 |
| C3 | `c_give("pickaxe")`，装备镐后点晶簇 | 出现"开采/Mine"，每一镐有晶体碎屑特效和玻璃声（和挖月岛玻璃一样） |
| C4 | 一直挖，数着下数 | 第 3 下：晶体开裂、顶端断掉（med）；第 5 下：只剩一小簇碎晶和石块（low）；底座位置始终不动；第 6 下碎掉（碎玻璃 + 烟尘）后消失，地上掉 2 或 3 个潮蚀结晶，能捡起、能和已有的结晶堆叠 |
| C5 | 再生成一个，挖 3 下（变成开裂的样子），`c_save()` 后 `c_reset()` | 读档后晶簇**仍是开裂的外观**，再挖 3 下就碎（挖过的次数和外观都被保存） |
| C6 | 检查晶簇（方法同检查世界里的其他物体） | 台词"潮水退去后留下的，还在嗡嗡作响。" |
| C7 | 洞穴里 `c_spawn("tide_crystal_cluster")` 并挖掉 | 和地面上一样（`caves_server_log.txt` 无报错） |

### 深潮祭坛（建筑 + 状态，设计见 `docs/TIDE_ALTAR_DESIGN.md` 第 0 节）

| # | 操作 | 期望 |
|---|---|---|
| T1 | `c_spawn("researchlab")` 放一台科学机器，站在旁边；`c_give("rocks", 10)`、`c_give("tide_crystal", 3)` | 制作栏"建筑"（和"魔法"）里出现深潮祭坛，图标是海螺石柱；鼠标悬停显示名字和"向深海借一次潮水。" |
| T2 | 制作 → 放置 | 放置时有半透明的祭坛预览，离其他建筑太近时变红；放下后海螺石柱立在地上，底座落在点击位置，人走过去会被挡住 |
| T3 | 检查祭坛 | "海螺深处，有什么东西在听。" |
| T4 | 鼠标对着祭坛 | 显示"唤潮"；点击后：换成发光外观，周围亮起青绿色的光并一明一暗地呼吸，底部不停溅水花，有水声 |
| T5 | 唤潮中拿锤子（`c_give("hammer")`）对着祭坛；再检查 | 没有"锤"的选项；台词"潮水在回应它！"；空格键也不会触发唤潮 |
| T6 | 等 30 秒 | 灯光渐暗熄灭，外观变回平时但整体变暗（冷却）；检查台词"它得先喘口气。"；没有"唤潮"选项 |
| T7 | 再等 60 秒 | 颜色恢复，又能"唤潮" |
| T8 | 唤潮中 `c_save()`，然后 `c_reset()` | 读档后祭坛是变暗的冷却状态（不发光），60 秒后恢复 |
| T9 | 冷却中 `c_save()` → `c_reset()` | 读档后仍是冷却，剩余时间接着算 |
| T10 | 平时或冷却中用锤子锤 4 下 | 碎石特效，祭坛消失，掉 5 块石头和 2 个潮蚀结晶（返还一半，向上取整） |
| T11 | 晚上唤潮 | 灯光能照亮周围，祭坛本体看得清 |
| T12 | 带洞穴的世界（你是客户端）重复 T4、T6 | 灯光呼吸平滑、不抖动；`client_log.txt` 无报错 |

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
   - **地上的东西和物品栏图标颜色不一样**：正常。游戏按季节和昼夜给整个世界套颜色滤镜（`components/colourcube.lua`，
     秋天白天是 `day05_cc`），物品栏界面不受影响。秋天白天青色会偏绿，原版蓝宝石会变得接近灰色。
     判断是不是我们的贴图有问题：在旁边放一个原版物品一起看，或者换季节/时间再看。

## 5. 联机测试矩阵（第 7 天用）

| 维度 | 取值 |
|---|---|
| 服务器形态 | 带洞穴（本机）/ 不带洞穴（本机主机）/ 专用服务器（Steam 工具 "Don't Starve Together Dedicated Server"） |
| 玩家数 | 1 / 2 / 4 |
| 位置 | 地上 / 洞穴 / 跨分片移动后 |
| 异常 | 事件中存档读档、事件中掉线、事件中死亡、事件中锤祭坛、禁用 Mod 后加载旧存档 |
| 兼容性 | 与你常用的客户端 Mod 一起开（Combined Status、Minimap HUD、Geometric Placement、Smart Crock Pot） |

每次测试记录：日期、git commit、服务器形态、人数、通过/失败、日志片段。失败项直接开 GitHub Issue。
