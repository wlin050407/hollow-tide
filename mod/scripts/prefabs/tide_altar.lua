-- scripts/prefabs/tide_altar.lua
--
-- 深潮祭坛（Tide Altar）。设计见 docs/TIDE_ALTAR_DESIGN.md。
-- 现阶段只有"状态"，没有事件玩法（预警、伤害、奖励以后再加）：
--   IDLE      平时：可以"唤潮"，可以锤
--   ACTIVE    唤潮中：换发光外观、脚下漩涡旋转、灯光呼吸、底部溅水花；不能锤，不能再次唤潮；持续 T.ALTAR_ACTIVE_TIME 秒
--   COOLDOWN  冷却：外观变暗；可以锤，不能唤潮；T.ALTAR_COOLDOWN 秒后回到 IDLE
--
-- 网络：状态只在服务器上改，通过 netvar 同步给客户端。
--   * 动画、Light:Enable 只在服务器上设置（会自动同步，原版月晷就是这样）
--   * 灯光渐变、颜色、LightOverride 在两端各自设置（原版 deerclopseyeball_sentryward.lua 的做法）
--     所以 lighttweener 组件在两端都添加——这是唯一允许客户端访问的组件，它本来就是纯本地的表现组件。
--
-- 写法参考：原版 prefabs/moondial.lua（建筑、锤、灯光）、prefabs/deerclopseyeball_sentryward.lua（netvar 驱动的灯光渐变）。

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

local function PulseLight(inst)
    inst._pulse_high = not inst._pulse_high
    local radius = inst._pulse_high and T.ALTAR_LIGHT_RADIUS_HIGH or T.ALTAR_LIGHT_RADIUS_LOW
    inst.components.lighttweener:StartTween(inst.Light, radius, T.ALTAR_LIGHT_INTENSITY, T.ALTAR_LIGHT_FALLOFF,
        T.ALTAR_LIGHT_COLOUR, T.ALTAR_LIGHT_PULSE)
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

local function TurnLightOff(inst)
    if TheWorld.ismastersim then
        inst.Light:Enable(false)
    end
end

local function ApplyVisuals(inst)
    local state = inst._state:value()
    if state == STATE.ACTIVE then
        if TheWorld.ismastersim then
            inst.Light:Enable(true)
        end
        inst.AnimState:SetMultColour(1, 1, 1, 1)
        inst.AnimState:SetLightOverride(T.ALTAR_LIGHT_OVERRIDE)
        if inst._swirl == nil and not TheNet:IsDedicated() then -- 专用服务器没有画面，不需要
            inst._swirl = CreateSwirl()
            inst._swirl.entity:SetParent(inst.entity)
        end
        if inst._pulse_task == nil then
            inst._pulse_high = false
            PulseLight(inst)
            inst._pulse_task = inst:DoPeriodicTask(T.ALTAR_LIGHT_PULSE, PulseLight)
        end
    else
        RemoveSwirl(inst)
        if inst._pulse_task ~= nil then
            inst._pulse_task:Cancel()
            inst._pulse_task = nil
            -- 渐暗到 0 再关灯
            inst.components.lighttweener:StartTween(inst.Light, 0, 0, T.ALTAR_LIGHT_FALLOFF,
                T.ALTAR_LIGHT_COLOUR, 1, TurnLightOff)
        end
        inst.AnimState:SetLightOverride(0)
        local tint = state == STATE.COOLDOWN and T.ALTAR_COOLDOWN_TINT or 1
        inst.AnimState:SetMultColour(tint, tint, tint, 1)
    end
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

-- 唯一修改状态的入口：netvar + 动画 + 组件开关 + 表现
local function SetState(inst, state)
    inst._state:set(state)

    inst.AnimState:PlayAnimation(state == STATE.ACTIVE and "active" or "idle")
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

    ApplyVisuals(inst)
    Log.Debug("tide_altar %s -> %s", inst.GUID, STATE_NAME[state])
end

local function StartCooldown(inst)
    inst.components.timer:StopTimer("active")
    if not inst.components.timer:TimerExists("cooldown") then
        inst.components.timer:StartTimer("cooldown", T.ALTAR_COOLDOWN)
    end
    SetState(inst, STATE.COOLDOWN)
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
        StartCooldown(inst) -- 唤潮中存档：读档后直接进入冷却（以后有事件玩法时 = 中断、无奖励）
    elseif inst.components.timer:TimerExists("cooldown") then
        SetState(inst, STATE.COOLDOWN) -- 冷却剩余时间由 timer 自己恢复
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
    inst.Light:SetIntensity(T.ALTAR_LIGHT_INTENSITY)
    inst.Light:SetFalloff(T.ALTAR_LIGHT_FALLOFF)
    inst.Light:SetColour(unpack(T.ALTAR_LIGHT_COLOUR))
    -- 灯光渐变在两端各自做：不加这个，服务器每帧改的半径会同步过来和客户端自己的渐变打架
    -- （原版凡是本地改灯光的都这样设，例如 deerclopseyeball_sentryward.lua、cavelight.lua）
    inst.Light:EnableClientModulation(true)

    inst:AddTag("structure")

    -- "唤潮"：动作文字取 STRINGS.ACTIONS.ACTIVATE.TIDE_ALTAR（actions.lua ACTIVATE.strfn）
    inst.GetActivateVerb = function() return "TIDE_ALTAR" end

    inst:AddComponent("lighttweener") -- 两端都要（见文件头）

    inst._state = net_tinybyte(inst.GUID, "tide_altar._state", "tide_altar_statedirty")
    inst.OnRemoveEntity = OnRemoveEntity -- 两端都要：漩涡特效是每台机器自己生成的

    inst.entity:SetPristine()

    if not TheWorld.ismastersim then
        inst:ListenForEvent("tide_altar_statedirty", ApplyVisuals)
        inst:DoTaskInTime(0, ApplyVisuals) -- 进入视野时祭坛可能已经在唤潮/冷却中
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
