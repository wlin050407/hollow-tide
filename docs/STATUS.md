# 项目状态（交接用）

更新：2026-10-11 07:00（第一阶段 · 第 1 周 · 第 1 天）。**每完成一个可验证的小步就更新这里**——新会话 / 新工具只靠这份文件和仓库里的其他文档接手。
（2026-10-11 之前的进度也记在 claude.ai Project "Game_Dev" 的 `claude/hollow-tide-status.md`，从现在起以本文件为准。）

## 本机环境

| 项 | 位置 |
|---|---|
| 仓库 | `E:\Game_Dev\hollow-tide`（GitHub 私有仓库 `wlin050407/hollow-tide`，分支 `main`，push 后 GitHub Actions 跑 `check.yml`） |
| 游戏 | `D:\Applications\Steam\steamapps\common\Don't Starve Together`，build 756039 |
| 原版脚本（API 核对用） | `D:\Applications\Steam\steamapps\common\Don't Starve Together\data\databundles\scripts.zip`；着色器 `...\data\databundles\shaders.zip`；原版动画包 `...\data\anim\*.zip` |
| Mod 挂载 | 目录联接 `...\Don't Starve Together\mods\hollowtide` → `E:\Game_Dev\hollow-tide\mod`：改仓库里的文件就是改游戏加载的文件，**完全重启游戏**后生效 |
| 日志 | `C:\Users\ROG\Documents\Klei\DoNotStarveTogether\`：`client_log.txt`、`master_server_log.txt`、`caves_server_log.txt`（崩溃时还有 `.dmp`） |
| 测试世界 | 存档槽 "HollowTide Test"（Cluster_3，Relaxed，Local Only，带洞穴——你在游戏里是客户端）；存档备份 `E:\Game_Dev\save_backup_20261011\` |
| 同时启用的其他本地 Mod | `mods\lightlab`（LightLab 光影实验台，另一个项目，**不要改它**）：0.3.0 版进世界会崩溃，见"已知现象" |

## 工作方式（2026-10-11 起在本机用 Claude Code）

1. 规则见 `AGENTS.md`（`CLAUDE.md` 指向它）。用户偏好：**用中文回复，代码和标识符用英文**；一次一个能进游戏验证的小步；不要凭记忆写 DST API。
2. 改完必须：
   - `python tools\check_mod.py --game-scripts "<上面的 scripts.zip>"` → 0 个 ERROR
   - 改了祭坛逻辑或祭坛数值：`python tools\sim_altar.py` → 全部通过
   - 改了美术工具：`python tools\art\make_anim.py selftest "<游戏>\data\anim\gems.zip" ...` 和重新生成的包逐字节对比
3. commit → push；然后给用户：进游戏测试步骤（控制台命令 + 期望 + 看哪份日志）、新用到的 API 及出处、没验证的地方。
4. 用户测完后直接读上面的日志排查，不用再让用户拷贝。
5. 美术：用户用 ChatGPT 生图，PNG 放进 `art/source/<物体>/`；处理流程和命令见 `docs/ART_PIPELINE.md`。AI 生图的 prompt **不用记录**，不要向用户要 prompt 或模型名。

## 已完成

- M0/M1：加载、日志、生成、悬停名称、拾取、右键检查、堆叠 40、存档→重启→读档
- 潮蚀结晶 `tide_crystal`（单块结晶）、潮蚀晶簇 `tide_crystal_cluster`（镐挖 6 下、三档破损外观、存档进度）——用户确认没问题
- **深潮祭坛** `tide_altar`（设计 `docs/TIDE_ALTAR_DESIGN.md`）：制作（石头 10 + 结晶 3，科学一级，占位数值）、摆放、碰撞、锤 4 下返还一半材料；
  "唤潮" → ACTIVE 30 秒 → COOLDOWN 60 秒（变暗）→ IDLE；唤潮中存档读档进冷却；台词随状态变化；空格不触发唤潮；唤潮中拆解法杖无效
- 祭坛脚下漩涡 `tide_altar_swirl`（本地不联网子特效、地面层），迭代过程：
  - 整体矩阵旋转 → 用户："太粗糙"
  - `8d61862` 一张图程序生成 32 帧流动（中心差速旋转 + 往里吸）→ "中心不错，但边缘全都一样"
  - `fb53f50` 用户给了 6 张外圈不同的变体，外圈硬切换图 → "很不连贯"（换图那帧相邻帧差 46–56，平时约 4）
  - `2f18334` 外圈在变体之间按有向距离场逐帧变形（轮廓始终实心、无重影），中心单图流动 → "感觉不错，但外圈旋转方向的样子跟真实物理反了"
  - `60a53be` `--mirror-rim`：外圈用镜像变体（AI 画的外圈浪头朝向和中心螺旋相反；实测运动都是逆时针）→ 06:28 "还不错"
  - 当前：60 张逐帧（2 秒一循环）、整体 6 秒一圈、atlas 2048×2048、zip 2.3 MB；命令见 `docs/ART_PIPELINE.md`
- `c8a5ce3` 唤潮亮度渐变（06:28 反馈"一亮一亮太突然"）：两端每帧更新（原版 `stalker_bulb.lua` 写法）——2 秒缓入缓出渐亮，
  全亮后半径 3±0.3 正弦呼吸（4 秒一次），结束 2 秒渐暗，冷却变暗/恢复各 1.5 秒；发光外观改为本地叠加层
  （`active` 盖在始终 `idle` 的本体上，`SetFinalOffset(1)`）；不再用 `lighttweener`。**待游戏内验证**
- 工具：`tools/check_mod.py`（静态检查 + 原版 API 核对）、`tools/sim_altar.py`（祭坛行为模拟，CI 也跑）、
  `tools/art/`（`remove_bg` / `cutout_glow` / `align_stages` / `prepare_icon` / `png2tex` / `make_anim` / `kanim`）

## 核实基准（细节和出处在 `docs/API_NOTES.md`）

- DST build 756039，MOD_API_VERSION = 10
- 动画坐标 y 向下为正；1 build 单位 = 1 贴图像素；同帧多元素排前面的在上层；元素矩阵 x' = a·x + c·y + tx，y' = b·x + d·y + ty
- 贴地图案：普通朝向 + `LAYER_BACKGROUND` + `SortOrder(3)`；本地特效写法见原版 `deerclopseyeball_sentryward.lua`
- 灯光：`Enable` 只在服务器；两端各自渐变要 `EnableClientModulation(true)`，再用 `lighttweener` 或每帧 `DoPeriodicTask(FRAMES)`
- 动画着色器 `colour * COLOUR_XFORM` 后 `rgb = min(rgb, a)`，贴图预乘 alpha → 半透明渐变用 `SetMultColour(a, a, a, a)`
- 世界画面有季节/昼夜颜色滤镜，UI 不受影响
- 尺寸参考（build 像素）：蓝宝石 152×126，巨石 605×413，月晷 328×292，人物约 336 高，祭坛 440 高

## 待验证 / 未完成

- **马上要测**：`c8a5ce3` 的渐亮 / 呼吸 / 渐暗；发光叠加层是否确实画在祭坛本体上面（如果本体的发光没出来、只有外圈光晕，就是叠加层被画到了下面）
- 漩涡：外圈变形速度是否合适（`--boil-steps`；更慢需要 > 64 张，要先实现多张 atlas 或降低 `--flow-size`）；漩涡 `pre` 只有 0.4 秒，比灯光渐亮快，用户觉得不协调时可以加长
- T12：带洞穴世界里作为客户端看灯光 / 漩涡
- M1 #7 带结晶进洞穴；M1 #8 第二名玩家加入；中文环境下的名称和台词
- 以后的事件玩法（用户说不急）：潮痕预警（可复用 `tide_altar_swirl`）、涨潮伤害/潮湿、结算奖励、怪物
- 发布前：核对 OpenAI 图片使用条款

## 已知现象（与本 Mod 无关）

- **LightLab 0.3.0 进世界崩溃**（2026-10-11 05:29）：`Shader uniform is undefined` / `Assert failure 'src_data != NULL' at ...HWEffect.cpp(467)`，
  紧跟在 `[LightLab] active (bloom pass -> lightlab_mark ...)` 之后。疑点：新加的 `lightlab_wetmark.ksh`（bloom 阶段）声明了
  `FLOAT_PARAMS` / `OCEAN_*` 引擎参数，原版 bloom 着色器没有。测 Hollow Tide 时先在模组菜单里关掉 LightLab
- 同一游戏进程内先玩别的存档再开测试世界 → 角色隐身 + `Could not find anim [...] in bank [wilson]`；完全重启游戏即消失
- 游戏运行时再次启动 exe 会截断 `client_log.txt`
- 游戏崩溃后重启，可能自动禁用所有 Mod，进世界前确认 Hollow Tide 还开着

## 关键决定

- 默认测试环境：带洞穴的世界；测试前完全重启一次游戏
- 事件中途存档 → 读档视为中断、无奖励、进入冷却
- 图标和动画包都用自研工具（`tools/art/`），Mod Tools / ktech / Spriter 为备用
- AI 出多阶段 / 多状态美术：让 AI 在完整图上编辑，再用工具对齐 / 抠图，不手工处理
- 静止的美术里不要悬空的水珠 / 碎片
- 用户对动态效果要求高：优先做逐帧流动感，不要简单变换；明暗变化要渐变，不要突变
- 漩涡外圈浪头的朝向必须和中心螺旋的转向一致（用户对"物理方向"敏感）
- 潮蚀晶簇用镐；晶簇来源以后在新地图世界生成里做，**现在不做，不要再追问**
- 祭坛先做建筑和状态，事件玩法和怪物以后再做
- Klei Player Creation Guidelines（2022-10-17）不允许商业使用、未提及捐赠 → 拿到 Klei 书面答复前不开捐赠；视频广告明确允许

## 下一步

- 用户进游戏看唤潮渐亮 / 呼吸 / 渐暗，按反馈调 `tuning.lua` 里的 `ALTAR_FADE_IN` / `ALTAR_FADE_OUT` / `ALTAR_LIGHT_BREATH` / `ALTAR_LIGHT_BREATH_PERIOD`
