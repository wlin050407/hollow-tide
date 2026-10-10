-- scripts/prefabs/tide_crystal_cluster.lua
--
-- 潮蚀晶簇（Tide Crystal Cluster）：用镐开采，挖碎后掉落潮蚀结晶。设计见 docs/TIDE_CRYSTAL_CLUSTER_DESIGN.md
-- 外观：原创动画包 anim/tide_crystal_cluster.zip（make_anim.py stages 生成），三个破损阶段 "full" / "med" / "low"。
-- 写法参考原版 prefabs/rocks.lua（巨石）和 prefabs/lunarrift_crystals.lua（月岛裂隙水晶）。

local T = require("hollowtide/tuning")

local assets =
{
    Asset("ANIM", "anim/tide_crystal_cluster.zip"),
}

-- 会生成的 prefab：声明后游戏会提前加载它们的资源
local prefabs =
{
    "tide_crystal",
    "mining_moonglass_fx",
    "collapse_small",
}

-- 破损阶段：把总次数平均分成三段，和原版巨石的规则一样（rocks.lua OnWork）。
-- 挖 6 下时：剩 6、5、4 次 = full，剩 3、2 次 = med，剩 1 次 = low
local function UpdateStage(inst, workleft)
    local total = T.TIDE_CRYSTAL_CLUSTER_MINE
    local anim = (workleft < total / 3 and "low")
        or (workleft < total * 2 / 3 and "med")
        or "full"
    if not inst.AnimState:IsCurrentAnimation(anim) then
        inst.AnimState:PlayAnimation(anim)
    end
end

local function OnWork(inst, worker, workleft)
    if workleft <= 0 then
        local pt = inst:GetPosition()
        SpawnPrefab("mining_moonglass_fx").Transform:SetPosition(pt:Get())
        SpawnPrefab("collapse_small").Transform:SetPosition(pt:Get())
        inst.components.lootdropper:DropLoot(pt)
        inst:Remove()
    else
        UpdateStage(inst, workleft)
    end
end

-- 读档时 workable 先恢复剩余次数，再调用这里，把外观对上（workable.lua OnLoad -> onloadfn）
local function OnWorkableLoad(inst)
    UpdateStage(inst, inst.components.workable:GetWorkLeft())
end

local function fn()
    local inst = CreateEntity()

    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddSoundEmitter()
    inst.entity:AddNetwork()

    MakeObstaclePhysics(inst, T.TIDE_CRYSTAL_CLUSTER_RADIUS)

    inst.AnimState:SetBank("tide_crystal_cluster")
    inst.AnimState:SetBuild("tide_crystal_cluster")
    inst.AnimState:PlayAnimation("full")

    inst:AddTag("boulder")  -- 按原版巨石对待（熊獾撞碎时不掉落等）
    inst:AddTag("crystal")  -- 每一镐用晶体的特效和声音（commonstates.lua PlayMiningFX）

    inst.entity:SetPristine()

    if not TheWorld.ismastersim then
        return inst
    end

    inst:AddComponent("inspectable")

    inst:AddComponent("lootdropper")
    local loot = {}
    for i = 1, T.TIDE_CRYSTAL_CLUSTER_LOOT do
        loot[i] = "tide_crystal"
    end
    inst.components.lootdropper:SetLoot(loot) -- 注意：SetLoot 会清空概率掉落，所以要先调用
    inst.components.lootdropper:AddChanceLoot("tide_crystal", T.TIDE_CRYSTAL_CLUSTER_BONUS_CHANCE)

    local workable = inst:AddComponent("workable")
    workable:SetWorkAction(ACTIONS.MINE)
    workable:SetWorkLeft(T.TIDE_CRYSTAL_CLUSTER_MINE)
    workable:SetOnWorkCallback(OnWork)
    workable.savestate = true -- 挖了一半存档，读档后剩余次数不变
    workable:SetOnLoadFn(OnWorkableLoad)

    MakeHauntableWork(inst)

    return inst
end

return Prefab("tide_crystal_cluster", fn, assets, prefabs)
