-- scripts/prefabs/tide_altar.lua
--
-- 深潮祭坛（Tide Altar）。设计见 docs/TIDE_ALTAR_DESIGN.md。
-- 现阶段只有"状态"，没有事件玩法（预警、伤害、奖励以后再加）：
--   IDLE      平时：可以"唤潮"，可以锤
--   ACTIVE    唤潮中：渐渐亮起发光外观和灯光（灯光缓慢呼吸）、脚下漩涡旋转、底部溅水花；
--             不能锤，不能再次唤潮；持续 T.ALTAR_ACTIVE_TIME 秒，结束时渐暗
--   COOLDOWN  冷却：外观渐渐变暗；可以锤，不能唤潮；T.ALTAR_COOLDOWN 秒后回到 IDLE
--
-- 网络：状态只在服务器上改，通过 netvar 同步给客户端。
--   * Light:Enable 只在服务器上设置（会自动同步）
--   * 亮度渐变（灯光半径/强度、发光外观的透明度、LightOverride、冷却变暗）在两端各自每帧计算
--     （原版 stalker_bulb.lua 的 OnUpdateFade 写法，配合 Light:EnableClientModulation(true)）
--   * 发光外观是本地叠加层（"active" 画面盖在平时外观上、透明度渐变），本体始终播放 "idle"
--
-- 写法参考：原版 prefabs/moondial.lua（建筑、锤、灯光）、prefabs/stalker_bulb.lua（两端各自渐变灯光）、
-- prefabs/deerclopseyeball_sentryward.lua（netvar 驱动的本地表现、本地叠加层）。

require "prefabutil" -- MakePlacer

local T = require("hollowtide/tuning")
local Log = require("hollowtide/log")

local assets =
{
    Asset("ANIM", "anim/tide_altar.zip"),
    Asset("ANIM", "anim/tide_altar_swirl.zip"), -- 唤潮时脚下旋转的漩涡（本地特效，不是单独的 prefab）
}

local prefabs =
{
    "rock_break_fx",
    "splash",
}

local STATE = { IDLE = 0, ACTIVE = 1, COOLDOWN = 2 }
local STATE_NAME = { [0] = "IDLE", [1] = "ACTIVE", [2] = "COOLDOWN" }

--------------------------------------------------------------------------
-- 两端共用：按当前状态设置本地表现
--------------------------------------------------------------------------

local TWO_PI = 2 * math.pi

local function SmoothStep(x)
    return x * x * (3 - 2 * x)
end

local function Approach(value, target, step)
    if value < target then
        return math.min(value + step, target)
    end
    return math.max(value - step, target)
end

-- 发光外观：本地叠加层，同一个 bank/build 的 "active" 画面盖在本体的 "idle" 上，透明度跟着亮度渐变。
-- （一个 AnimState 不能在两个动画之间渐变，所以分两层。）写法同下面的 CreateSwirl；
-- SetFinalOffset(1) 让它画在本体上面（原版 deerclopseyeball_sentryward.lua 的本地叠加层同样用 SetFinalOffset）。
local function CreateGlowLayer()
    local fx = CreateEntity()

    --[[Non-networked entity]]
    if not TheWorld.ismastersim then
        fx.entity:SetCanSleep(false)
    end
    fx.persists = false

    fx.entity:AddTransform()
    fx.entity:AddAnimState()

    fx:AddTag("FX")
    fx:AddTag("NOCLICK") -- 鼠标仍然指向祭坛本体

    fx.AnimState:SetBank("tide_altar")
    fx.AnimState:SetBuild("tide_altar")
    fx.AnimState:PlayAnimation("active")
    fx.AnimState:SetFinalOffset(1)

    return fx
end

-- 脚下的漩涡：每台机器自己生成的本地特效（不联网、不存档），挂在祭坛下面跟着它。
-- 做法同原版 deerclopseyeball_sentryward.lua 的 CLIENT_CreateEyeball；
-- 画在地面层（LAYER_BACKGROUND + SortOrder 3，同原版 damp_trail.lua），所以人和祭坛都盖在它上面。
-- 旋转是动画数据里做的（make_anim.py spin，原理同原版预警圈 warning_shadow）。
local function CreateSwirl()
    local fx = CreateEntity()

    --[[Non-networked entity]]
    if not TheWorld.ismastersim then
        fx.entity:SetCanSleep(false)
    end
    fx.persists = false

    fx.entity:AddTransform()
    fx.entity:AddAnimState()

    fx:AddTag("FX")
    fx:AddTag("NOCLICK")

    fx.AnimState:SetBank("tide_altar_swirl")
    fx.AnimState:SetBuild("tide_altar_swirl")
    fx.AnimState:SetLayer(LAYER_BACKGROUND)
    fx.AnimState:SetSortOrder(3)
    fx.AnimState:PlayAnimation("pre")
    fx.AnimState:PushAnimation("loop", true)

    return fx
end

local function RemoveSwirl(inst)
    if inst._swirl ~= nil then
        local fx = inst._swirl
        inst._swirl = nil
        if fx:IsValid() then
            fx.AnimState:PlayAnimation("pst") -- 缩回去再消失
            fx:ListenForEvent("animover", fx.Remove)
        end
    end
end

-- 每帧更新亮度（两端各自做，同原版 stalker_bulb.lua 的 OnUpdateFade）：
--   _glow：唤潮亮度 0..1，唤潮时 T.ALTAR_FADE_IN 秒升到 1，结束后 T.ALTAR_FADE_OUT 秒降到 0
--   _dim ：冷却变暗程度 0..1，T.ALTAR_DIM_FADE 秒到位
-- 两者都用 SmoothStep 缓入缓出；全亮时灯光半径按正弦缓慢呼吸。都到位且不在唤潮中时停止更新。
local function UpdateGlow(inst)
    local state = inst._state:value()
    local glow_target = state == STATE.ACTIVE and 1 or 0
    local dim_target = state == STATE.COOLDOWN and 1 or 0
    local fade = glow_target > inst._glow and T.ALTAR_FADE_IN or T.ALTAR_FADE_OUT
    inst._glow = Approach(inst._glow, glow_target, FRAMES / fade)
    inst._dim = Approach(inst._dim, dim_target, FRAMES / T.ALTAR_DIM_FADE)

    local g = SmoothStep(inst._glow)
    local tint = 1 - (1 - T.ALTAR_COOLDOWN_TINT) * SmoothStep(inst._dim)

    local breath = math.sin(GetTime() * TWO_PI / T.ALTAR_LIGHT_BREATH_PERIOD)
    inst.Light:SetRadius((T.ALTAR_LIGHT_RADIUS + T.ALTAR_LIGHT_BREATH * breath) * g)
    inst.Light:SetIntensity(T.ALTAR_LIGHT_INTENSITY * g)
    if TheWorld.ismastersim then
        inst.Light:Enable(inst._glow > 0)
    end

    inst.AnimState:SetMultColour(tint, tint, tint, 1)
    inst.AnimState:SetLightOverride(T.ALTAR_LIGHT_OVERRIDE * g)

    if inst._glow > 0 and inst._glowfx == nil and not TheNet:IsDedicated() then -- 专用服务器没有画面，不需要
        inst._glowfx = CreateGlowLayer()
        inst._glowfx.entity:SetParent(inst.entity)
    end
    if inst._glowfx ~= nil then
        if inst._glow > 0 and inst._glowfx:IsValid() then
            -- 贴图是预乘 alpha，四个分量都乘 g 才是正确的半透明
            -- （原版动画着色器：colour * COLOUR_XFORM，然后 rgb = min(rgb, a)）
            local c = g * tint
            inst._glowfx.AnimState:SetMultColour(c, c, c, g)
            inst._glowfx.AnimState:SetLightOverride(T.ALTAR_LIGHT_OVERRIDE * g)
        else
            if inst._glowfx:IsValid() then
                inst._glowfx:Remove()
            end
            inst._glowfx = nil
        end
    end

    if state ~= STATE.ACTIVE and inst._glow == glow_target and inst._dim == dim_target
        and inst._glow_task ~= nil then
        inst._glow_task:Cancel()
        inst._glow_task = nil
    end
end

-- instant = true：刚进入视野、读档时直接到位，不从头渐变
local function ApplyVisuals(inst, instant)
    local state = inst._state:value()
    if state == STATE.ACTIVE then
        if inst._swirl == nil and not TheNet:IsDedicated() then
            inst._swirl = CreateSwirl()
            inst._swirl.entity:SetParent(inst.entity)
        end
    else
        RemoveSwirl(inst)
    end
    if instant == true then -- 也作为事件回调使用，那时第二个参数是事件数据，所以严格比较
        inst._glow = state == STATE.ACTIVE and 1 or 0
        inst._dim = state == STATE.COOLDOWN and 1 or 0
    end
    if inst._glow_task == nil then
        inst._glow_task = inst:DoPeriodicTask(FRAMES, UpdateGlow)
    end
    UpdateGlow(inst)
end

--------------------------------------------------------------------------
-- 服务器
--------------------------------------------------------------------------

local function SpawnSplash(inst)
    if inst:IsAsleep() then -- 附近没有玩家时不浪费
        return
    end
    local x, y, z = inst.Transform:GetWorldPosition()
    local angle = math.random() * 2 * math.pi
    local dist = math.random() * T.ALTAR_SPLASH_RANGE
    SpawnPrefab("splash").Transform:SetPosition(x + math.cos(angle) * dist, 0, z + math.sin(angle) * dist)
end

-- 唯一修改状态的入口：netvar + 组件开关 + 表现（本体动画始终是 "idle"，发光外观是本地叠加层）
local function SetState(inst, state, instant)
    inst._state:set(state)

    inst.components.workable:SetWorkable(state ~= STATE.ACTIVE)
    inst.components.activatable.inactive = state == STATE.IDLE
    -- 标签会同步到客户端；配方的 no_deconstruction 用它在唤潮中禁止拆解法杖（modmain/recipes.lua）
    inst:AddOrRemoveTag("tide_altar_active", state == STATE.ACTIVE)

    if state == STATE.ACTIVE then
        if inst._splash_task == nil then
            inst._splash_task = inst:DoPeriodicTask(T.ALTAR_SPLASH_INTERVAL, SpawnSplash, 0)
        end
    elseif inst._splash_task ~= nil then
        inst._splash_task:Cancel()
        inst._splash_task = nil
    end

    ApplyVisuals(inst, instant)
    Log.Debug("tide_altar %s -> %s", inst.GUID, STATE_NAME[state])
end

local function StartCooldown(inst, instant)
    inst.components.timer:StopTimer("active")
    if not inst.components.timer:TimerExists("cooldown") then
        inst.components.timer:StartTimer("cooldown", T.ALTAR_COOLDOWN)
    end
    SetState(inst, STATE.COOLDOWN, instant)
end

local function OnActivate(inst, doer)
    inst.components.timer:StartTimer("active", T.ALTAR_ACTIVE_TIME)
    inst.SoundEmitter:PlaySound("dontstarve/common/together/moondial/water_movement")
    SetState(inst, STATE.ACTIVE)
    Log.Info("tide altar activated by %s", doer ~= nil and doer:GetDisplayName() or nil)
    return true
end

local function OnTimerDone(inst, data)
    if data.name == "active" then
        StartCooldown(inst)
    elseif data.name == "cooldown" then
        SetState(inst, STATE.IDLE)
    end
end

local function OnRemoveEntity(inst)
    if inst._swirl ~= nil and inst._swirl:IsValid() then
        inst._swirl:Remove()
    end
    if inst._glowfx ~= nil and inst._glowfx:IsValid() then
        inst._glowfx:Remove()
    end
end

local function OnHammered(inst)
    inst.components.lootdropper:DropLoot() -- 有配方的建筑会按原版规则返还一部分材料
    SpawnPrefab("rock_break_fx").Transform:SetPosition(inst.Transform:GetWorldPosition())
    inst:Remove()
end

local function OnBuilt(inst)
    inst.SoundEmitter:PlaySound("dontstarve/common/together/moondial/craft")
end

local function GetStatus(inst)
    local state = inst._state:value()
    return (state == STATE.ACTIVE and "ACTIVE")
        or (state == STATE.COOLDOWN and "COOLDOWN")
        or nil -- GENERIC
end

local function OnSave(inst, data)
    if inst._state:value() == STATE.ACTIVE then
        data.interrupted = true
    end
end

-- 组件（含 timer）的 OnLoad 先执行，这里后执行（entityscript.lua SetPersistData）
local function OnLoad(inst, data)
    if data ~= nil and data.interrupted then
        StartCooldown(inst, true) -- 唤潮中存档：读档后直接进入冷却（以后有事件玩法时 = 中断、无奖励）
    elseif inst.components.timer:TimerExists("cooldown") then
        SetState(inst, STATE.COOLDOWN, true) -- 冷却剩余时间由 timer 自己恢复
    end
end

--------------------------------------------------------------------------

local function fn()
    local inst = CreateEntity()

    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddSoundEmitter()
    inst.entity:AddLight()
    inst.entity:AddNetwork()

    inst:SetDeploySmartRadius(1) -- 配方 min_spacing 的一半（同原版月晷）
    MakeObstaclePhysics(inst, T.ALTAR_RADIUS)

    inst.AnimState:SetBank("tide_altar")
    inst.AnimState:SetBuild("tide_altar")
    inst.AnimState:PlayAnimation("idle")

    -- 灯光参数在两端都配置，开关只在服务器
    inst.Light:Enable(false)
    inst.Light:SetRadius(0)
    inst.Light:SetIntensity(0)
    inst.Light:SetFalloff(T.ALTAR_LIGHT_FALLOFF)
    inst.Light:SetColour(unpack(T.ALTAR_LIGHT_COLOUR))
    -- 灯光渐变在两端各自做：不加这个，服务器每帧改的半径会同步过来和客户端自己的渐变打架
    -- （原版凡是本地改灯光的都这样设，例如 stalker_bulb.lua、deerclopseyeball_sentryward.lua）
    inst.Light:EnableClientModulation(true)

    inst:AddTag("structure")

    -- "唤潮"：动作文字取 STRINGS.ACTIONS.ACTIVATE.TIDE_ALTAR（actions.lua ACTIVATE.strfn）
    inst.GetActivateVerb = function() return "TIDE_ALTAR" end

    inst._state = net_tinybyte(inst.GUID, "tide_altar._state", "tide_altar_statedirty")
    inst._glow = 0 -- 两端各自的亮度渐变进度（见 UpdateGlow）
    inst._dim = 0
    inst.OnRemoveEntity = OnRemoveEntity -- 两端都要：漩涡和发光叠加层是每台机器自己生成的

    inst.entity:SetPristine()

    if not TheWorld.ismastersim then
        inst:ListenForEvent("tide_altar_statedirty", ApplyVisuals)
        inst:DoTaskInTime(0, ApplyVisuals, true) -- 进入视野时祭坛可能已经在唤潮/冷却中：直接到位
        return inst
    end

    inst:AddComponent("inspectable")
    inst.components.inspectable.getstatus = GetStatus

    inst:AddComponent("lootdropper")
    inst:AddComponent("timer")

    inst:AddComponent("activatable")
    inst.components.activatable.OnActivate = OnActivate
    -- 不让空格键触发唤潮（空格是"捡东西"键，见 playercontroller.lua；原版 winch.lua 同样设置）
    inst.components.activatable.forcenopickupaction = true

    inst:AddComponent("workable")
    inst.components.workable:SetWorkAction(ACTIONS.HAMMER)
    inst.components.workable:SetWorkLeft(T.ALTAR_HAMMER_WORK)
    inst.components.workable:SetOnFinishCallback(OnHammered)

    MakeHauntableWork(inst)

    inst:ListenForEvent("timerdone", OnTimerDone)
    inst:ListenForEvent("onbuilt", OnBuilt)

    inst.OnSave = OnSave
    inst.OnLoad = OnLoad

    return inst
end

return Prefab("tide_altar", fn, assets, prefabs),
    MakePlacer("tide_altar_placer", "tide_altar", "tide_altar", "idle")
