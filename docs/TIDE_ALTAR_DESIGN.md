# Tide Altar（深潮祭坛）交互机制设计

> 状态：设计稿，计划第 3–5 天落地。下面所有 API 都已对照本机游戏脚本（build 756039）核实，出处见 [API_NOTES.md](API_NOTES.md)。
> 代码骨架只用来说明结构，落地时逐段写、逐段进游戏验证，不要一次性整段粘贴。

## 0. 当前实现（2026-10-11）：建筑 + 状态，没有事件玩法

用户决定：玩法（预警、伤害、奖励、怪物）以后再做，先把祭坛作为建筑和它的三个状态做出来。
代码在 `mod/scripts/prefabs/tide_altar.lua`，配方在 `mod/modmain/recipes.lua`，数值在 `tuning.lua`。

| 状态 | 外观 | 能做什么 |
|---|---|---|
| IDLE 平时 | 原创外观 `idle` | 可以"唤潮"，可以锤 |
| ACTIVE 唤潮中（30 秒） | 发光外观 `active` 和青绿色灯光在 2 秒内渐渐亮起（缓入缓出），全亮后灯光半径按正弦缓慢"呼吸"（4 秒一次，±10%）；脚下出现流动的漩涡（长出来 → 中心转得快、往里吸，整体慢转 → 结束时缩回去）；本体不受黑暗影响（LightOverride，也跟着渐变）；底部每 1.5 秒溅一次水花；结束时 2 秒渐暗 | 不能锤、不能拆解法杖、不能再唤潮 |
| COOLDOWN 冷却（60 秒） | `idle` 外观在 1.5 秒内渐渐变暗；冷却结束时同样渐渐恢复 | 可以锤，不能唤潮 |

和下面第 5 节骨架的差别：用了自己的美术（不再借月晷）；亮度两端各自每帧渐变（`DoPeriodicTask(FRAMES)` + `Light:EnableClientModulation(true)`，
同原版 `stalker_bulb.lua`；2026-10-11 反馈"唤潮时一亮一亮太突然"之前用的是 `lighttweener` 在两个半径之间匀速来回）；
发光外观是本地叠加层（`active` 画面盖在本体 `idle` 上、透明度渐变），本体始终播放 `idle`；没有预警和奖励；空格键不会触发唤潮（`forcenopickupaction`）；
唤潮中加标签 `tide_altar_active`，配方的 `no_deconstruction` 用它挡住拆解法杖。
脚下漩涡是每台机器自己生成的本地特效（不联网、不存档），画在地面层；动画由 6 张手绘变体 + 程序生成的中心流动组成
（外圈在变体之间逐帧变形，见 ART_PIPELINE），以后做事件"潮痕预警"时可以复用同一个动画包。
存档规则同第 4.2 节：唤潮中存档 → 读档后直接进入冷却。

## 1. 原版里已经有几乎一样的结构

原版的 **龙舟赛起点 `boatrace_start`** 和 **游乐场小游戏 `carnivalgame_*`** 都是"玩家制作 → 放置 → 激活 → 限时事件 → 发奖励 → 可被锤掉"的建筑，它们用的组件和我们要用的一样（`activatable`、`timer`、`lootdropper`、`workable`）。这说明 Tide Altar 在技术上没有未知风险，遇到问题时可以直接去读这两个文件的写法。

## 2. 玩家视角的流程

```
制作（科学机器一级）→ 放置 → 交互"唤潮"
   → 30 秒异变：每隔几秒，随机一名玩家脚下出现"潮痕"预警，1.5 秒后涨潮
       站在潮痕里：受伤 + 变潮湿；及时走开：无事
   → 结束时祭坛附近还有存活玩家 = 成功 → 掉落潮蚀结晶（参与人数越多越多）
   → 所有人离开或死亡 = 失败 → 无奖励
   → 冷却 N 秒后可再次唤潮
```

设计意图：难度来自"预警 → 躲避"的操作和多人互相走位，不是数值膨胀。潮湿是原版就有的负面状态（降低理智、影响手持物品），和"潮水"主题一致。

## 3. 状态机（只在服务器上运行）

```
          OnActivate                 timer "event" 结束
 IDLE ───────────────▶ ACTIVE ──────────────────────────▶ COOLDOWN ──timer "cooldown"──▶ IDLE
                         │ 范围内没有存活玩家                 ▲
                         └──────────────── 失败 ─────────────┘
```

| 状态 | `activatable.inactive` | `workable` | 客户端能看到的 |
|---|---|---|---|
| IDLE | true（显示"唤潮"动作） | 可锤 | 静止 |
| ACTIVE | false | 不可锤 | 发光、动画、音效 |
| COOLDOWN | false | 可锤 | 暗淡 |

## 4. 关键实现点

### 4.1 交互：`activatable` 组件
- `inactive = true` 时，组件会给实体加 `inactive` 标签；客户端的动作收集器看到这个标签才会显示"激活"动作。标签会自动同步，不需要自己做网络代码。
- 自定义动作文字：在**两端共享部分**设置 `inst.GetActivateVerb = function() return "TIDE_ALTAR" end`，并在字符串表里加 `STRINGS.ACTIONS.ACTIVATE.TIDE_ALTAR = "唤潮"`。
- 注意：`DoActivate` 会**先**把 `inactive` 设为 false 再调用 `OnActivate`。如果 `OnActivate` 判定失败（返回 false），要自己把 `inactive` 改回 true，否则祭坛会卡死在不可交互状态。
- 祭坛是石质建筑，第一版**不加** `burnable`（不会着火）。如果以后加了，原版 `ACTIONS.ACTIVATE` 会在燃烧/闷烧时自动拒绝激活。
- 两个玩家同时点：第一个请求在服务器上把 `inactive` 置 false，第二个请求在 `CanActivate` 里失败。天然防重复触发。

### 4.2 计时与存档：`timer` 组件
- 事件时长和冷却都用 `timer`（`StartTimer` / `StopTimer` / `TimerExists`），结束时收到 `timerdone` 事件。
- `timer` 自带存档：冷却中存档 → 读档后冷却继续，不用自己写。
- **事件进行中存档**的处理（决定）：读档后视为"事件中断"，不发奖励，直接进入冷却。理由：简单、不可能通过读档刷奖励。
- 已核实的加载顺序：组件的 `OnLoad` 先执行，实体的 `inst.OnLoad` 后执行。所以在 `inst.OnLoad` 里可以安全地停掉被恢复的 "event" 计时器。

### 4.3 危险机制
- 每 `ALTAR_HAZARD_INTERVAL` 秒：`FindPlayersInRange(x, y, z, 半径, true)` 找范围内存活玩家；没有人 → 判定失败。
- 随机选一名玩家，在他脚下生成预警（占位用原版 `warningshadow`，它会无限循环播放且 `persists = false`，必须自己 `Remove()`）。
- `ALTAR_HAZARD_WARNING` 秒后在该点结算：范围内玩家 `components.moisture:DoDelta(潮湿值)` + `components.combat:GetAttacked(inst, 伤害)`；播放原版 `splash_ocean` 作为占位水花。
- 延迟结算的任务挂在**预警实体自己身上**（`shadow:DoTaskInTime`），祭坛记录所有存活的预警；事件结束时统一 `Remove()`，
  这样事件结束后不会再有"迟到的"涨潮打到玩家。
- 所有数值放进 `scripts/hollowtide/tuning.lua`，第 5 天调参时只改这个文件。

### 4.4 客户端表现：netvar
- 在 `SetPristine()` **之前**声明：`inst._state = net_tinybyte(inst.GUID, "tide_altar._state", "tide_altar_statedirty")`（0..7 足够放 3 个状态）。
- 服务器通过一个 `SetState(inst, state)` 函数统一改状态：同时 `inst._state:set(...)`、开关灯光、切换动画。
  灯光的参数（半径、强度、颜色）在共享部分配置，**开关只在服务器做**（原版月晷 `moondial.lua` 就是这样）。
- 客户端监听 `tide_altar_statedirty`，只做纯本地的表现（例如音效、UI 提示）。
- 规则：**玩法只在服务器算，客户端只负责好看**。客户端代码里不能出现 `inst.components.xxx`（客户端没有组件）。
- 预警圈、水花这类 FX 第一版直接在服务器 `SpawnPrefab`（联网实体会自动同步给客户端）；以后如果网络流量成为问题，再改成"服务器推 netvar、客户端本地生成不联网的 FX"。

### 4.5 结算与掉落
- 成功：`lootdropper:SpawnLootPrefab("tide_crystal")`，数量 = 基础 + 参与人数加成（参与者 = 结算时在范围内且存活）。
- 事件中锤祭坛：ACTIVE 时 `workable:SetWorkable(false)`；结束时恢复。
  注意 `workable:SetWorkLeft()` 会把 workable 重新设为 true，事件中不要调用它（或调用后再 `SetWorkable(false)`）。
- 掉线：玩家离开服务器后不在 `FindPlayersInRange` 结果里，自然不计入。

## 5. 代码骨架（第 3–4 天按段落地）

```lua
-- scripts/prefabs/tide_altar.lua（骨架，未进游戏验证）
require "prefabutil" -- MakePlacer 定义在这里

local T = require("hollowtide/tuning")
local Log = require("hollowtide/log")

local assets =
{
    Asset("ANIM", "anim/moondial.zip"),       -- 占位：原版月晷
    Asset("ANIM", "anim/moondial_build.zip"), -- 占位
}
local prefabs = { "tide_crystal", "warningshadow", "splash_ocean", "collapse_small" }

local STATE = { IDLE = 0, ACTIVE = 1, COOLDOWN = 2 }

-- 服务器：唯一修改状态的入口（netvar + 灯光 + 动画一起改）
local function SetState(inst, state)
    inst._state:set(state)
    inst.Light:Enable(state == STATE.ACTIVE)
end

-- 服务器：清理所有还没结算的预警
local function ClearHazards(inst)
    if inst._hazard_task ~= nil then
        inst._hazard_task:Cancel()
        inst._hazard_task = nil
    end
    for shadow in pairs(inst._shadows) do
        shadow:Remove() -- 挂在 shadow 上的延迟结算任务随之取消
    end
    inst._shadows = {}
end

local function StrikeAt(inst, shadow)
    local x, y, z = shadow.Transform:GetWorldPosition()
    inst._shadows[shadow] = nil
    shadow:Remove()
    SpawnPrefab("splash_ocean").Transform:SetPosition(x, 0, z)
    for _, player in ipairs(FindPlayersInRange(x, y, z, T.ALTAR_HAZARD_RADIUS, true)) do
        player.components.moisture:DoDelta(T.ALTAR_HAZARD_WETNESS)
        player.components.combat:GetAttacked(inst, T.ALTAR_HAZARD_DAMAGE)
    end
end

local StartCooldown -- 前向声明

local function FinishEvent(inst, players)
    ClearHazards(inst)
    if #players > 0 then
        for i = 1, T.ALTAR_REWARD_BASE + #players - 1 do
            inst.components.lootdropper:SpawnLootPrefab("tide_crystal")
        end
    end
    Log.Info("tide event finished, success=%s players=%s", #players > 0, #players)
    StartCooldown(inst)
end

local function SpawnHazard(inst)
    local x, y, z = inst.Transform:GetWorldPosition()
    local players = FindPlayersInRange(x, y, z, T.ALTAR_EVENT_RADIUS, true)
    if #players == 0 then
        FinishEvent(inst, players) -- 所有人离开或死亡：失败
        return
    end
    local target = players[math.random(#players)]
    local tx, _, tz = target.Transform:GetWorldPosition()
    local shadow = SpawnPrefab("warningshadow")
    shadow.Transform:SetPosition(tx, 0, tz)
    inst._shadows[shadow] = true
    shadow:DoTaskInTime(T.ALTAR_HAZARD_WARNING, function() StrikeAt(inst, shadow) end)
end

StartCooldown = function(inst)
    inst.components.timer:StopTimer("event")
    inst.components.timer:StartTimer("cooldown", T.ALTAR_COOLDOWN)
    inst.components.workable:SetWorkable(true)
    inst.components.activatable.inactive = false
    SetState(inst, STATE.COOLDOWN)
end

local function OnActivate(inst, doer)
    inst.components.workable:SetWorkable(false)
    inst.components.timer:StartTimer("event", T.ALTAR_EVENT_DURATION)
    inst._hazard_task = inst:DoPeriodicTask(T.ALTAR_HAZARD_INTERVAL, SpawnHazard)
    SetState(inst, STATE.ACTIVE)
    Log.Info("tide event started by %s", doer ~= nil and doer:GetDisplayName() or nil)
    return true
end

local function OnTimerDone(inst, data)
    if data.name == "event" then
        local x, y, z = inst.Transform:GetWorldPosition()
        FinishEvent(inst, FindPlayersInRange(x, y, z, T.ALTAR_EVENT_RADIUS, true))
    elseif data.name == "cooldown" then
        SetState(inst, STATE.IDLE)
        inst.components.activatable.inactive = true
    end
end

local function OnSave(inst, data)
    if inst._state:value() == STATE.ACTIVE then
        data.interrupted = true
    end
end

local function OnLoad(inst, data) -- 组件（含 timer）的 OnLoad 已经先执行过
    if data ~= nil and data.interrupted then
        StartCooldown(inst)                    -- 事件中断：不发奖励（会停掉被恢复的 "event" 计时器）
    elseif inst.components.timer:TimerExists("cooldown") then
        inst.components.activatable.inactive = false
        SetState(inst, STATE.COOLDOWN)         -- 冷却由 timer 自动恢复
    end
end

local function fn()
    local inst = CreateEntity()
    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddSoundEmitter()
    inst.entity:AddLight()
    inst.entity:AddNetwork()

    inst:SetDeploySmartRadius(1) -- 配方 min_spacing 的一半
    MakeObstaclePhysics(inst, 0.45)

    inst.AnimState:SetBank("moondial")
    inst.AnimState:SetBuild("moondial_build")
    inst.AnimState:PlayAnimation("idle_new")

    -- 灯光参数在共享部分配置，开关在服务器的 SetState 里
    inst.Light:Enable(false)
    inst.Light:SetRadius(T.ALTAR_LIGHT_RADIUS)
    inst.Light:SetFalloff(0.7)
    inst.Light:SetIntensity(0.6)
    inst.Light:SetColour(15 / 255, 160 / 255, 180 / 255)

    inst:AddTag("structure")
    inst.GetActivateVerb = function() return "TIDE_ALTAR" end

    inst._state = net_tinybyte(inst.GUID, "tide_altar._state", "tide_altar_statedirty")

    inst.entity:SetPristine()
    if not TheWorld.ismastersim then
        -- 客户端：需要纯本地表现时在这里监听 "tide_altar_statedirty"
        return inst
    end

    inst._shadows = {}

    inst:AddComponent("inspectable")
    inst:AddComponent("lootdropper")
    inst:AddComponent("timer")
    inst:AddComponent("activatable")
    inst.components.activatable.OnActivate = OnActivate

    inst:AddComponent("workable")
    inst.components.workable:SetWorkAction(ACTIONS.HAMMER)
    inst.components.workable:SetWorkLeft(4)
    -- SetOnFinishCallback：ClearHazards + 掉落部分材料 + collapse_small 特效 + inst:Remove()（参考 moondial.lua 的 onhammered）

    inst:ListenForEvent("timerdone", OnTimerDone)
    inst.OnSave = OnSave
    inst.OnLoad = OnLoad
    return inst
end

return Prefab("tide_altar", fn, assets, prefabs),
    MakePlacer("tide_altar_placer", "moondial", "moondial_build", "idle_new")
```

配方（`modmain/recipes.lua`，用 `modimport` 载入）：

```lua
AddRecipe2("tide_altar",
    { Ingredient("rocks", 10), Ingredient("bluegem", 1) },  -- 占位配方，第 5 天调整
    GLOBAL.TECH.SCIENCE_ONE,
    { placer = "tide_altar_placer", min_spacing = 2, image = "moondial.tex" }, -- 占位图标：原版月晷
    { "STRUCTURES", "MAGIC" })
```

字符串（`modmain/strings.lua`，中英文都要加）：`STRINGS.NAMES.TIDE_ALTAR`、`STRINGS.RECIPE_DESC.TIDE_ALTAR`、
`STRINGS.CHARACTERS.GENERIC.DESCRIBE.TIDE_ALTAR`、`STRINGS.ACTIONS.ACTIVATE.TIDE_ALTAR`（"唤潮" / "Invoke the Tide"）。

## 6. 验收用例（第 7 天全部通过才算完成）

| # | 场景 | 期望 |
|---|---|---|
| A1 | 科学机器旁制作并放置 | 放置预览正确；落地后可检查，名称中英文正确 |
| A2 | 唤潮后等 30 秒，不躲避 | 事件结束有掉落；期间受到伤害、变潮湿 |
| A3 | 唤潮后全部离开祭坛范围 | 判定失败，无掉落，进入冷却 |
| A4 | 两名玩家同时唤潮 | 只触发一次 |
| A5 | 事件中锤祭坛 | 锤不动；事件结束后可以锤，掉落材料 |
| A6 | 冷却中 `c_save()` → `c_reset()` | 读档后仍在冷却，冷却结束后可再次唤潮 |
| A7 | 事件中 `c_save()` → `c_reset()` | 读档后进入冷却，无奖励，没有残留的预警圈 |
| A8 | 事件中某玩家掉线 / 死亡 | 不报错；结算人数不包括他 |
| A9 | 带洞穴的世界里，客户端玩家视角 | 灯光、预警、水花都能看到；`client_log.txt` 无报错 |
| A10 | 地上与洞穴各放一个祭坛 | 互不影响 |
