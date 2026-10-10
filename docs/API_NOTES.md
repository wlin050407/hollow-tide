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
| 原版物品栏图标每格 **64×64**（图集 2048×2048、DXT5、带 mipmap、UV 半像素内缩） | 实测 `images/inventoryimages1.tex/.xml` |
| 原版贴图数据**上下翻转存储**、alpha **预乘**（原版图集 99.9% 的半透明像素满足 RGB ≤ A）；图集 UV 的 v 按存储行从上往下计 | 解码原版 `inventoryimages1/3.tex` 实测（火炬、帐篷、背包图标存储时都是倒着的） |
| KTEX 文件头：`"KTEX"` + 32 位字：platform 4 位 / compression 5 位（DXT1=0, DXT3=1, DXT5=2, RGBA=4, RGB=5）/ type 4 位 / mipmap 数 5 位 / flags 2 位 / fill 12 位；之后每级 mipmap：`u16 宽, u16 高, u16 pitch, u32 数据长度` | ktools 源码 `ktex/specs.cpp`、`ktex.cpp` + 原版文件实测 |

## 配方

| 事实 | 出处 |
|---|---|
| `AddRecipe2(name, ingredients, tech, config, filters)`；自动加入 `MODS` 过滤器（`config.nounlock` 时改为加入 `CRAFTING_STATION`）；config 字段：`placer, min_spacing, nounlock, numtogive, builder_tag, atlas, image, testfn, product, build_mode, build_distance` 等 | `modutil.lua`；`recipe.lua` `Recipe2` |
| `TECH.SCIENCE_ONE = { SCIENCE = 1 }` 等 | `constants.lua` |
| 过滤器名：`STRUCTURES`、`MAGIC`、`MODS` 等 | `recipes_filter.lua` `CRAFTING_FILTER_DEFS` |
| `MakePlacer(name, bank, build, anim, onground, snap, metersnap, scale, fixedcameraoffset, facing, postinit_fn, offset, onfailedplacement)`；使用它的 prefab 文件开头要 `require "prefabutil"` | `prefabutil.lua`；原版 `moondial.lua` 等 |
| 配方图标默认是 `<product>.tex`；没有对应图标时要在 config 里给 `image`（占位可用原版 `moondial.tex`，在 `inventoryimages2.xml`） | `recipe.lua` |
| 建筑放置间距：`inst:SetDeploySmartRadius(r)`，原版注释为 recipe `min_spacing` 的一半 | `entityscript.lua`；`prefabs/moondial.lua` |

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
| 可作占位的原版资源：月晷 `moondial`（bank `moondial` / build `moondial_build` / anim `idle_new`；灯光在共享部分配置、在服务器上开关）；FX `warningshadow`（循环播放、`persists=false`，需手动 Remove）、`splash_ocean`、`crab_king_waterspout` | `prefabs/moondial.lua`、`prefabs/warningshadow.lua` 等 |

## 控制台与测试

| 事实 | 出处 |
|---|---|
| `c_spawn(prefab, count)`、`c_give(prefab, count)`、`c_giveingredients(recipe)`、`c_save()`、`c_reset()`（回到上一次存档）、`c_rollback(n)`、`c_godmode()` | `consolecommands.lua` |
| 管理员打开控制台时默认"远程执行"（在服务器上执行），按 Ctrl 切换本地/远程 | `screens/consolescreen.lua` |
| 物品栏里"强制查看（组合键）"+ 左键 = 检查物品 | `widgets/invslot.lua`；中文控件名见 `languages/chinese_s.po` |
| 检查物品时角色的台词在**服务器**上生成（`talker:Say` 在服务器执行），所以台词语言跟随服务器 | `actions.lua` `ACTIONS.LOOKAT` |

## 尚未核实（使用前必须验证）

- `tools/art/png2tex.py` 生成的贴图在游戏内的显示效果（数据层面已与原版逐像素对照一致，见 ART_PIPELINE.md ⑥）
- Don't Starve Mod Tools / ktech（目前作为备用方案，未在本机使用）
- Workshop 上传流程与大小限制（第 4 阶段再查）
