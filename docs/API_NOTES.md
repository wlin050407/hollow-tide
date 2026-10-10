# DST API 核实笔记

- 核实基准：DST **build 756039**（`version.txt`），`data/databundles/scripts.zip`，2026-10-10 核对。
- 规则：这里只记录**在游戏源码里亲眼确认过**的事实，并写明出处（文件 + 函数名；行号会随版本漂移，不写）。
- AI 写代码前先查这里；这里没有的 API，先去 `scripts.zip` 里找到出处，再补充进来，再写代码。
- 游戏大版本更新后：重新运行 `python tools/check_mod.py --game-scripts <scripts.zip>`，并抽查本表。

## Mod 加载

| 事实 | 出处 |
|---|---|
| `MOD_API_VERSION = 10` | `mods.lua` 文件开头 |
| `modinfo.lua` 的沙盒里**只有** `folder_name`、`locale`、`ChooseTranslationTable`，没有 `string`/`table` 等标准库 | `modindex.lua` `ModIndex:InitializeModInfo` |
| modinfo 必填：`name`、`description`、`author`、`version`、`api_version`（缺 `dst_compatible` 只会警告） | 同上 |
| `client_only_mod` 与 `all_clients_require_mod` 互斥 | 同上 |
| modmain 环境字段：`pairs, ipairs, print, math, table, type, string, tostring, require, Class, TUNING, GLOBAL, modname, MODROOT, modinfo, env, modimport`，以及 modutil 注入的 `AddXxx`、`Prefab`、`Asset`、`Ingredient`、`GetModConfigData`、`RegisterInventoryItemAtlas` 等 | `mods.lua` `CreateEnvironment`；`modutil.lua` `InsertPostInitFunctions` |
| modmain 环境里**没有** `STRINGS`、`TheWorld`、`TheNet`、`SpawnPrefab`、`TECH`、`ACTIONS`……要写 `GLOBAL.xxx` | 同上 |
| `modimport(path)`：相对 Mod 根目录，自动补 `.lua`，在 Mod 环境中执行 | `mods.lua` `CreateEnvironment` |
| `require` 的搜索路径包含 `mods/<mod>/scripts/?.lua`；被 require 的文件运行在**全局**环境 | `mods.lua` `ModWrangler:LoadMods` |
| Mod 根目录加入 `package.assetpath`，`resolvefilepath` 能找到 Mod 内资源；找不到时 `resolvefilepath` 会 assert 崩溃，`softresolvefilepath` 不会 | `mods.lua`；`util.lua` |
| 本地 Mod 默认不用 manifest，Workshop Mod 默认用（可用 modinfo 的 `forcemanifest` 改） | `mods.lua` `ModWrangler:LoadMods` |
| 语言代码：`zh` 简体、`zht` 繁体、`zhr` WeGame；英文时 `LOC.GetLocaleCode()` 返回 `"en"` | `languages/loc.lua` |
| 语言在 Mod 加载之前就确定；专用服务器的语言来自集群设置 | `main.lua`（`languages/language` 先于 `ModManager:LoadMods`）；`languages/language.lua` `GetCurrentLocale` |
| 加入服务器时，客户端使用服务器下发的 Mod 配置 | `modindex.lua` `GetModConfigurationOptions_Internal`、`SetTempModConfigData` |
| `configuration_options` 每项：`name, label, hover, options = {{description, data, hover?}}, default` | `screens/redux/modconfigurationscreen.lua` |

## 生命周期钩子

| 事实 | 出处 |
|---|---|
| `AddSimPostInit(fn)`：世界加载完成后，服务器和客户端各执行一次 | `gamelogic.lua`（`ModManager:SimPostInit`） |
| 运行中的世界实体：`TheWorld.prefab` 固定是 `"world"`；真正的世界类型在 `TheWorld.worldprefab`（`"forest"` / `"cave"`） | `prefabs/world.lua`（`SetPrefabName("world")`）；`gamelogic.lua` `PopulateWorld` |
| `AddPrefabPostInit(name, fn)` 按 prefab 名匹配，且会同时匹配实体的 prefab 名和生成时用的名字：`"world"` 在所有分片触发，`"forest"` / `"cave"` 只在对应分片触发 | `mainfunctions.lua` `SpawnPrefabFromSim` |
| `TheWorld.ismastersim`、`TheWorld.ismastershard` | `prefabs/world.lua` |
| 服务器端事件 `ms_playerjoined` / `ms_playerleft`（推到 `TheWorld`）；客户端本地玩家就绪事件 `playeractivated` | `prefabs/player_common.lua` |
| `SHARDID.MASTER = "1"` | `constants.lua` |

## Prefab 写法

| 事实 | 出处 |
|---|---|
| 标准结构：`AddNetwork` → 两端共享的声明 → `inst.entity:SetPristine()` → `if not TheWorld.ismastersim then return inst end` → 服务器组件 | `prefabs/gem.lua` 等 |
| netvar 必须在服务器和客户端**以相同方式声明**，否则实体反序列化失败；所以用 netvar 的 Mod 必须所有客户端都装 | `netvars.lua` 注释 |
| netvar 类型：`net_bool`、`net_tinybyte`(0..7)、`net_smallbyte`(0..63)、`net_byte`、`net_shortint`、`net_ushortint`、`net_int`、`net_uint`、`net_float`、`net_hash`、`net_string`、`net_entity`……；一次性触发用 `net_event` | `netvars.lua` |
| 存档读取：组件的 `OnLoad` **先**执行，实体的 `inst.OnLoad` **后**执行 | `entityscript.lua` `EntityScript:SetPersistData` |
| 存档里遇到不存在的 prefab：打印 `Can't find prefab X` 并跳过 → **禁用 Mod 后，存档里的 Mod 实体会消失** | `mainfunctions.lua` `SpawnPrefab`、`SpawnSaveRecord` |
| `MakeInventoryPhysics`、`MakeObstaclePhysics`、`MakeInventoryFloatable(inst, size, offset, scale, ...)`、`MakeHauntableLaunch`、`MakeHauntableWork` | `standardcomponents.lua` |
| `TUNING.STACK_SIZE_SMALLITEM = 40` | `tuning.lua` |

## 物品栏图标

| 事实 | 出处 |
|---|---|
| `inventoryitem.imagename` / `atlasname` 是属性，赋值会同步到 replica（客户端） | `components/inventoryitem.lua` |
| 没设 atlas 时用 `GetInventoryItemAtlas(image)`：先查注册表，再查原版 `inventoryimages1~4.xml`；image 默认是 `<prefab>.tex` | `components/inventoryitem_replica.lua`；`simutil.lua` |
| ⚠️ 设置了 `imagename` 后，客户端 `GetImage()` 返回的是 **hash 数字**（`net_hash`），按字符串注册的图集查不到 → 自定义 imagename 时要同时设置 `atlasname` | `inventoryitem_replica.lua` `SetImage`；`netvars.lua`（net_hash 读取只返回 hash） |
| ⚠️ 原版图集里查不到时会回退到 `inventoryimages4.xml` 并**缓存**这个结果，之后再 `RegisterInventoryItemAtlas` 同名图片会被拒绝 → Mod 图集要在 modmain 顶层注册（早于任何查询） | `simutil.lua` `GetInventoryItemAtlas_Internal`、`RegisterInventoryItemAtlas` |
| 物品栏格子 `Image:SetTexture` 会自己 resolve 路径；但也有直接使用原始路径的地方（如 `minisign.lua` 的 `OverrideSymbol`），所以注册时统一传 **`resolvefilepath` 之后**的路径最稳妥 | `widgets/itemtile.lua`、`widgets/image.lua`；`prefabs/minisign.lua` |
| `RegisterInventoryItemAtlas(atlas, "name.tex")` 在 modmain 环境可用 | `modutil.lua` |
| 配方图标：`Recipe:GetAtlas()` = `resolvefilepath(GetInventoryItemAtlas(image))` | `recipe.lua` |
| `tools/art/png2tex.py` 生成的 64×64 DXT5 图标 + `RegisterInventoryItemAtlas(resolvefilepath(...))` 在游戏物品栏中显示正常 | 2026-10-11 用户游戏内实测 |
| 原版物品栏图标每格 **64×64**（图集 2048×2048、DXT5、带 mipmap、UV 半像素内缩） | 实测 `images/inventoryimages1.tex/.xml` |
| 原版贴图数据**上下翻转存储**、alpha **预乘**（原版图集 99.9% 的半透明像素满足 RGB ≤ A）；图集 UV 的 v 按存储行从上往下计 | 解码原版 `inventoryimages1/3.tex` 实测（火炬、帐篷、背包图标存储时都是倒着的） |
| KTEX 文件头：`"KTEX"` + 32 位字：platform 4 位 / compression 5 位（DXT1=0, DXT3=1, DXT5=2, RGBA=4, RGB=5）/ type 4 位 / mipmap 数 5 位 / flags 2 位 / fill 12 位；之后每级 mipmap：`u16 宽, u16 高, u16 pitch, u32 数据长度` | ktools 源码 `ktex/specs.cpp`、`ktex.cpp` + 原版文件实测 |

## 动画包（地面外观）

| 事实 | 出处 |
|---|---|
| 地面外观的标准写法：prefab assets 里 `Asset("ANIM", "anim/<x>.zip")`；构造函数里 `inst.AnimState:SetBank(bank)`、`SetBuild(build)`、`PlayAnimation(anim)`（单帧不需要 loop） | `prefabs/flint.lua`（bank/build `flint`，anim `idle`） |
| `SetBuild` 用的是 build.bin 里写的 build 名；`SetBank` 用的是 anim.bin 里每个动画记录的 bank（存的是 hash）；和 zip 文件名无关 | 原版 `moondial.zip`（bank `moondial`）+ `moondial_build.zip`（build `moondial_build`），`prefabs/moondial.lua` |
| 动画找不到时游戏不会崩溃：实体**隐形**，日志里只有一行 `Could not find anim [...] in bank [...]` → bank / build / 动画名靠 `check_mod.py` 第 4 步核对 | 本项目早期玩家隐形时 `client_log.txt` 里的同一条日志（见 TESTING.md） |
| `MakeInventoryFloatable` 不传 swap_bank 时，漂浮期间**继续播放当前动画**，只额外加前/后两个水花特效（`float_fx_front/back`，`idle_front_<size>`），位置 = 实体位置 + `vert_offset`，缩放 = scale | `components/floater.lua` `OnLandedClient`、`AttachEffect` |
| 传了 swap_bank 的物品，离开水面时默认切回 bank = **prefab 名**、动画 `"idle"` → 我们的命名（bank = prefab 名，动画 `idle`）与之兼容 | `components/floater.lua` `SwitchToDefaultAnim` |
| `AnimState:SetRayTestOnBB(true)`：鼠标拾取改用包围盒（默认按像素）。少数原版物品用（如 flint、moonrocknugget）；物品太细不好点时再考虑 | `prefabs/flint.lua` 等 60 个 prefab |
| zip 格式：`build.bin` + `anim.bin` + `atlas-N.tex`，deflate 压缩；atlas 与物品栏图标同一套 KTEX 约定（DXT5、预乘 alpha、上下翻转、完整 mipmap），尺寸可以不是正方形（flint 是 512×256） | 原版 gems / flint / moondial / moondial_build 实测 |
| build.bin v6、anim.bin v4 的完整字段布局；动画坐标 y 向下为正（建筑 ty 为负）；1 build 单位 = 1 贴图像素；矩形上沿对应较大的 v；同一帧多个元素时排在前面的显示在上层 | `tools/art/kanim.py` 顶部注释；`make_anim.py selftest` 对四个原版包读入再写出**逐字节相同**；原版宝石/燧石按此渲染方向正确 |

## 可开采物（潮蚀晶簇用）

| 事实 | 出处 |
|---|---|
| 镐开采：`workable:SetWorkAction(ACTIONS.MINE)`、`SetWorkLeft(n)`（同时把 workable 设为 true）、`SetOnWorkCallback(fn(inst, worker, workleft))`；`workleft <= 0` 时自己生成特效、掉落、`inst:Remove()` | `prefabs/rocks.lua` `OnWork`；`prefabs/lunarrift_crystals.lua`；`components/workable.lua` |
| `workable.savestate = true`：存档时保存 `workleft` / `maxwork`（默认不保存，读档后恢复满值） | `components/workable.lua` `OnSave` / `OnLoad`；`lunarrift_crystals.lua` |
| `TUNING.ROCKS_MINE = 6`（原版巨石要挖 6 下） | `tuning.lua` |
| `lootdropper:SetLoot({...})` **会清空**概率掉落和随机掉落 → 先 `SetLoot` 再 `AddChanceLoot(prefab, chance)`；`DropLoot(pt)` 在 pt 处掉落 | `components/lootdropper.lua` |
| `MakeObstaclePhysics(inst, rad, height)`：不可穿过的障碍；原版巨石半径 1，裂隙水晶 0.6 / 1.0 | `standardcomponents.lua`；`rocks.lua`；`lunarrift_crystals.lua` |
| 标签 `crystal`：被镐敲时用 `mining_crystal_fx` 和月岛玻璃的开采声；标签 `moonglass` 用 `mining_moonglass_fx` | `stategraphs/commonstates.lua` `PlayMiningFX` |
| 标签 `boulder`：熊獾冲撞撞碎可开采物时，带 `boulder` / `tree` 标签的会先清空掉落（撞碎不给东西） | `prefabs/bearger.lua` `OnDestroyOther` |
| 碎裂特效 prefab：`mining_moonglass_fx`（在 `fx.lua` 表里定义）、`collapse_small`、`rock_break_fx`（自带 `dontstarve/wilson/rock_break` 声音） | `fx.lua`；`prefabs/rock_break_fx.lua`；`lunarrift_crystals.lua` |
| `Prefab(name, fn, assets, prefabs)` 第 4 个参数是会生成的 prefab 列表，用来提前加载它们的资源 | 原版 prefab 通用写法（如 `rocks.lua`） |
| `inst:GetPosition()` 返回 `Vector3`；`Vector3:Get()` 返回 x, y, z | `entityscript.lua`；`vector3.lua` |
| 破损阶段：原版巨石在 OnWork 里按剩余次数切 `full` / `med` / `low`（`< 1/3` 为 low，`< 2/3` 为 med），用 `AnimState:IsCurrentAnimation(anim)` 避免重复播放 | `prefabs/rocks.lua` `OnWork` |
| 原版巨石的动画包结构：一个 symbol（`rock01`）有 3 帧，`full` / `med` / `low` 三个动画分别引用第 0/1/2 帧，变换相同 | 解析 `anim/rock.zip` 实测 |
| 动画元素矩阵的含义：`x' = a·x + c·y + tx`，`y' = b·x + d·y + ty`（a b c d 按列存） | 原版 `warning_shadow.zip` 的 60 帧按这个约定拆解，每一帧都恰好是"y 压扁 0.518 × 纯旋转 × 缩放"（正交误差 0、行列式 1）；按另一种约定拆不开 |
| 原版地面预警圈 `warningshadow` 的做法：贴图是一张**正圆**的阴影（212×199），动画 `idle` 60 帧、30fps，用矩阵把它压扁成椭圆（y × 0.518）并在"地面上"旋转（每帧约 6°，2 秒一圈），同时略微放大；实体本身是普通朝向 + `AnimState:SetFinalOffset(3)` | 解析 `anim/warning_shadow.zip`；`prefabs/warningshadow.lua` |
| 发光相关：`AnimState:SetBloomEffectHandle("shaders/anim.ksh")`（156 个原版 prefab 在用）、`AnimState:SetLightOverride(x)`、`entity:AddLight()` + `Light:SetRadius/SetIntensity/SetFalloff/SetColour/Enable`；灯光渐变组件 `lighttweener`（`StartTween(light, rad, intensity, falloff, colour, time, callback)`） | `prefabs/moondial.lua`；`components/lighttweener.lua` |
| `workable:SetOnLoadFn(fn)`：读档时 workable 先恢复 `workleft`，再调用 `fn(inst, data)`，可在这里按剩余次数恢复外观 | `components/workable.lua` `OnLoad` |

## 画面颜色

| 事实 | 出处 |
|---|---|
| 游戏按季节和昼夜给**世界画面**套颜色滤镜（colour cube），物品栏等界面不受影响。秋天：白天 `day05_cc`、黄昏 `dusk03_cc`、夜晚 `night03_cc` | `components/colourcube.lua` |
| 滤镜文件 `images/colour_cubes/*.tex`：1024×32 未压缩 RGB 的 32³ 查找表（横向 32 片，每片 32×32；x = 蓝×32 + 红，绿按行、存储上下翻转） | 解码 `identity_colourcube.tex` 实测：按此布局查表与原色最大误差 1 |
| 秋天白天的滤镜会让青色偏绿、蓝色接近灰色（原版蓝宝石也一样）→ 地上物品和图标颜色不同是正常的 | 用 `day05_cc` 处理原版蓝宝石与潮蚀结晶，和 2026-10-11 游戏截图一致 |

## 配方

| 事实 | 出处 |
|---|---|
| `AddRecipe2(name, ingredients, tech, config, filters)`；自动加入 `MODS` 过滤器（`config.nounlock` 时改为加入 `CRAFTING_STATION`）；config 字段：`placer, min_spacing, nounlock, numtogive, builder_tag, atlas, image, testfn, product, build_mode, build_distance` 等 | `modutil.lua`；`recipe.lua` `Recipe2` |
| `TECH.SCIENCE_ONE = { SCIENCE = 1 }` 等 | `constants.lua` |
| 过滤器名：`STRUCTURES`、`MAGIC`、`MODS` 等 | `recipes_filter.lua` `CRAFTING_FILTER_DEFS` |
| `MakePlacer(name, bank, build, anim, onground, snap, metersnap, scale, fixedcameraoffset, facing, postinit_fn, offset, onfailedplacement)`；使用它的 prefab 文件开头要 `require "prefabutil"` | `prefabutil.lua`；原版 `moondial.lua` 等 |
| 配方图标默认是 `<product>.tex`；没有对应图标时要在 config 里给 `image`（占位可用原版 `moondial.tex`，在 `inventoryimages2.xml`） | `recipe.lua` |
| 建筑放置间距：`inst:SetDeploySmartRadius(r)`，原版注释为 recipe `min_spacing` 的一半 | `entityscript.lua`；`prefabs/moondial.lua` |
| 配方的 `no_deconstruction`（布尔或 `function(inst)`）：拆解法杖只看它和 `AllRecipes`，**不看 workable**；函数在客户端也会调用，只能读标签/netvar | `recipe.lua`（`more_data.no_deconstruction`）；`prefabs/staff.lua` `destroystructure`；`componentactions.lua`；原版 `shadow_beef_bell` 配方 |
| 锤掉建筑时 `lootdropper:DropLoot()` 会自动返还配方材料：每种材料 `ceil(数量 × TUNING.HAMMER_LOOT_PERCENT)`（`droprecipeloot` 默认开启） | `components/lootdropper.lua` `GetRecipeLoot`、`GenerateLoot` |

## 交互与事件（Tide Altar 用）

| 事实 | 出处 |
|---|---|
| `activatable`：`inactive` 属性 ↔ 标签 `inactive`；客户端看到标签才显示"激活"动作 | `components/activatable.lua`；`componentactions.lua` |
| `DoActivate` 先把 `inactive` 设为 false 再调用 `OnActivate`；失败时要自己恢复 | `components/activatable.lua` |
| `ACTIONS.ACTIVATE` 在燃烧/闷烧时拒绝；动作文字 = `inst.GetActivateVerb(inst, doer)` 返回 `STRINGS.ACTIONS.ACTIVATE` 的键 | `actions.lua` |
| `timer`：`StartTimer(name, time, paused, initialtime_override)`、`StopTimer`、`TimerExists`、`GetTimeLeft`、`PauseTimer`、`ResumeTimer`；结束推送 `timerdone {name=...}`；自带 `OnSave/OnLoad` | `components/timer.lua` |
| `workable:SetWorkable(bool)`、`SetWorkLeft`、`SetOnWorkCallback`、`SetOnFinishCallback`；⚠️ `SetWorkLeft` 会把 `workable` 重新设为 true | `components/workable.lua` |
| `lootdropper:SpawnLootPrefab(prefab, pt, ...)`、`DropLoot(pt, prefabs)`、`FlingItem(loot, pt)` | `components/lootdropper.lua` |
| `FindPlayersInRange(x, y, z, range, isalive)`、`IsAnyPlayerInRange(...)` | `simutil.lua` |
| `health:DoDelta(amount, overtime, cause, ...)`、`sanity:DoDelta(delta, overtime)`、`moisture:DoDelta(num, no_announce)`、`combat:GetAttacked(attacker, damage, weapon, stimuli, spdamage)` | `components/health.lua`、`sanity.lua`、`moisture.lua`、`combat.lua` |
| 原版参考实现：`boatrace_start.lua`（制作 → 激活 → 限时事件 → 奖励 → 可锤）、`carnivalgame_*.lua` | `prefabs/` |
| ⚠️ 空格键会对带 `inactive` 标签的非物品执行 ACTIVATE；不想被空格触发要设 `activatable.forcenopickupaction = true`（加标签 `activatable_forcenopickup`） | `components/playercontroller.lua`；原版 `winch.lua` |
| `timer` 到时会**先** `StopTimer` 再推送 `timerdone`；`StartTimer` 遇到同名计时器只打印警告、不覆盖 | `components/timer.lua` `OnTimerDone`、`StartTimer` |
| `inspectable.getstatus = fn(inst, viewer)` 返回状态键；`STRINGS.CHARACTERS.GENERIC.DESCRIBE.X` 写成表 `{GENERIC=..., 状态=...}`，返回 nil 时用 GENERIC | `components/inspectable.lua`；`stringutil.lua`；原版 `moondial.lua` |
| 灯光：`Light:Enable` 只在服务器设（会同步）；要在两端各自渐变时加 `Light:EnableClientModulation(true)`，并在两端都加 `lighttweener` 组件 | `prefabs/moondial.lua`；`prefabs/deerclopseyeball_sentryward.lua`；`cavelight.lua` 等 52 个 prefab |
| `inst:AddOrRemoveTag(tag, condition)`；标签会同步到客户端 | `entityscript.lua`；`components/activatable.lua` |
| 本地（不联网）特效：`CreateEntity()` 后不加 `AddNetwork`，`persists = false`，客户端上 `entity:SetCanSleep(false)`，用 `entity:SetParent(inst.entity)` 挂在实体下；只在 `not TheNet:IsDedicated()` 时创建 | `prefabs/deerclopseyeball_sentryward.lua` `CLIENT_CreateEyeball` |
| 画在地面层、被人和建筑盖住的贴地图案：`AnimState:SetLayer(LAYER_BACKGROUND)` + `SetSortOrder(3)`（普通朝向，图本身画成透视椭圆） | `prefabs/damp_trail.lua`；原版海上漩涡 `oceanwhirlportal.lua` 也是背景层 |
| 原版海上漩涡 `whirlportal.zip` 的旋转是 59 帧手绘逐帧（`Swirls` symbol 59 帧），不是矩阵旋转；矩阵旋转的先例是预警圈 `warning_shadow.zip` | 解析两个原版动画包 |
| 动画播完推送 `animover`；`fx:ListenForEvent("animover", fx.Remove)` 是原版常用的"播完就删"写法；实体被删除时会调用 `inst.OnRemoveEntity` | `prefabs/abigail.lua` 等；`prefabs/deerclopseyeball_sentryward.lua` |
| FX `splash`（`fx.lua`，自带 `turnoftides/common/together/water/splash/bird` 声音、`FinalOffset1`）；`splash_ocean` 注释为"旧海洋用"；声音 `dontstarve/common/together/moondial/craft`、`.../water_movement` | `fx.lua`；`stategraphs/SGmoondial.lua` |
| 可作占位的原版资源：月晷 `moondial`（bank `moondial` / build `moondial_build` / anim `idle_new`；灯光在共享部分配置、在服务器上开关）；FX `warningshadow`（循环播放、`persists=false`，需手动 Remove）、`splash_ocean`、`crab_king_waterspout` | `prefabs/moondial.lua`、`prefabs/warningshadow.lua` 等 |

## 控制台与测试

| 事实 | 出处 |
|---|---|
| `c_spawn(prefab, count)`、`c_give(prefab, count)`、`c_giveingredients(recipe)`、`c_save()`、`c_reset()`（回到上一次存档）、`c_rollback(n)`、`c_godmode()` | `consolecommands.lua` |
| 管理员打开控制台时默认"远程执行"（在服务器上执行），按 Ctrl 切换本地/远程 | `screens/consolescreen.lua` |
| 物品栏里"强制查看（组合键）"+ 左键 = 检查物品 | `widgets/invslot.lua`；中文控件名见 `languages/chinese_s.po` |
| 检查物品时角色的台词在**服务器**上生成（`talker:Say` 在服务器执行），所以台词语言跟随服务器 | `actions.lua` `ACTIONS.LOOKAT` |

## 尚未核实（使用前必须验证）

- Don't Starve Mod Tools / ktech（目前作为备用方案，未在本机使用）
- anim.bin 里带**事件**（每帧 events 非空）的情况：格式按 ktools 的布局实现，但手头四个原版包都没有事件，未经往返验证
- `make_anim.py` 生成的动画包：潮蚀结晶第一版在游戏地面上显示正常（2026-10-11 用户截图）；漂浮在海面上未单独确认
- 潮蚀晶簇的开采流程（OnWork 回调里的代码不会被 `check_mod.py` 执行，只能进游戏验证）
- Workshop 上传流程与大小限制（第 4 阶段再查）
