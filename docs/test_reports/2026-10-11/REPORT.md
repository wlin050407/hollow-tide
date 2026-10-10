# 测试报告：M0 + M1（2026-10-11）

| 项 | 内容 |
|---|---|
| 版本 | Mod 0.0.1（仓库首次提交前的版本），游戏 build 756039 |
| 安装方式 | 复制到 `mods\hollowtide`（未使用 junction） |
| 服务器形态 | 本机带洞穴的世界 "HollowTide Test"（Relaxed，Local Only）：地上、洞穴各一个专用服务器进程，游戏本体为纯客户端 |
| 人数 | 1 |
| 游戏语言 | 英文（Mod 语言设置 = 自动 → en） |
| 执行者 | Claude（远程操作），日志由 Claude 读取核对 |

## M0：加载

| 检查 | 结果 | 证据 |
|---|---|---|
| 模组列表出现 "Hollow Tide 深潮异变 [dev]"，中文正常显示 | ✅ | `m0_mod_list.jpg` |
| 配置菜单有 Language / Debug log 两项，hover 说明正常 | ✅ | 截图核对 |
| client_log：`[boot] modmain loaded`、`[client] world ready: world=forest ismastersim=false dedicated=false`、`local player activated: JOEYLIN` | ✅ | 日志 |
| master_server_log：`[server] world ready: world=forest ismastersim=true dedicated=true`、`shard id: 1`、`player joined: JOEYLIN` | ✅ | 日志 |
| caves_server_log：`[server] world ready: world=cave ismastersim=true dedicated=true`、`shard id: 2012489782` | ✅ | 日志 |
| 三份日志无 `LUA ERROR` / `stack traceback` | ✅ | 日志 |

## M1：占位物品 Tide Crystal

| # | 操作 | 结果 | 证据 |
|---|---|---|---|
| 1 | `c_spawn("tide_crystal")`（控制台默认 Remote） | ✅ 出现在鼠标位置 | `m1_spawn_hover.jpg` |
| 2 | 悬停 | ✅ "Pick up Tide Crystal" | 同上 |
| 3 | 捡起 | ✅ 进入物品栏，占位图标为原版蓝宝石 | 截图 |
| 4 | 右键检查 | ✅ Wilson："It hums like a shell held to the ear." | `m1_examine.jpg` |
| 5 | `c_give("tide_crystal", 45)`（已有 1 个） | ✅ 40 + 6 两堆 | 截图 |
| 6 | `c_save()` → 断开 → **完全退出游戏** → 重开读档 | ✅ 两堆仍为 40 + 6 | 截图 |
| 7 | 带着结晶进入洞穴 | ⏸ 未完成：重开后的游戏窗口按 ` 打不开控制台（Esc 正常），没能执行 `c_migrateto` | — |
| 8 | 第二名玩家加入 | ⏸ 需要队友 | — |

## 发现的问题

1. **角色隐身 + `Could not find anim [...] in bank [wilson]` 刷屏**（第一次进入测试世界时）。
   该游戏进程之前已经加载过另一个存档。完全退出、重开游戏后，同一存档、同样启用本 Mod，问题消失，重开后的日志里没有任何此类报错。
   **结论：与本 Mod 无关**，是同一进程内多次加载世界后的资源状态问题。已写入 TESTING.md 第 4 节。
2. TESTING.md 原写"Alt + 左键检查"有误，PC 上物品栏检查是**右键**。已修正。
3. 第二次启动游戏进程会截断 `client_log.txt`。已写入 TESTING.md。

## 未覆盖

- 中文环境下的名称/台词（游戏为英文；静态检查已确认 zh 字符串存在）
- 洞穴内生成 / 跨分片携带（#7）
- 多人（#8）

## 环境变更记录（便于撤销）

- 新增 `D:\...\Don't Starve Together\mods\hollowtide\`（Mod 副本；删除该文件夹即可完全移除）
- 新增存档槽 "HollowTide Test"（`Cluster_3`），其他 4 个存档未打开、未修改
- 测试前备份：`E:\Game_Dev\save_backup_20261011\`（Cluster_1、Cluster_2 最新快照 + 全部云存档 zip）

## 追加：原创物品栏图标（2026-10-11 01:20 左右，用户实测）

| 检查 | 结果 |
|---|---|
| 物品栏显示新图标（`tide_crystal.tex`，png2tex.py 生成） | ✅ 用户反馈"显示很正常" |
| 拖动、放入箱子、丢到地上再拾取、堆叠 | 未单独记录，下次测试时补 |
| 地面外观 | 仍为原版宝石动画 + 青绿染色（按计划保留） |
