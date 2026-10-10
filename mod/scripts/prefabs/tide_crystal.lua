-- scripts/prefabs/tide_crystal.lua
--
-- 潮蚀结晶（Tide Crystal）
-- 物品栏图标：原创（images/inventoryimages/tide_crystal.tex，在 modmain.lua 注册图集）。
-- 地面外观：暂时借用原版宝石动画（anim/gems.zip）并染成青绿色，之后再做原创地面动画。
--
-- 结构遵循原版 prefab 的标准写法（参考原版 prefabs/gem.lua）：
--   1) 两端共有部分：Transform / AnimState / Network / 物理 / 标签
--   2) entity:SetPristine() —— 之前声明的内容服务器和客户端必须完全一致
--   3) 仅服务器部分：组件（inspectable / inventoryitem / stackable ...）
--      客户端拿不到 inst.components.xxx，只能通过 replica、标签和 netvar 读取状态。

local T = require("hollowtide/tuning")

local assets =
{
    Asset("ANIM", "anim/gems.zip"), -- 原版资源，仅作占位
}

local function fn()
    local inst = CreateEntity()

    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddSoundEmitter()
    inst.entity:AddNetwork()

    MakeInventoryPhysics(inst)

    inst.AnimState:SetBank("gems")
    inst.AnimState:SetBuild("gems")
    inst.AnimState:PlayAnimation("bluegem_idle", true)
    -- 占位染色：偏青绿的"潮水"色，和原版蓝宝石区分开
    inst.AnimState:SetMultColour(0.55, 1, 0.9, 1)

    inst.pickupsound = "gem"

    MakeInventoryFloatable(inst, "small", 0.10, 0.80)

    inst.entity:SetPristine()

    if not TheWorld.ismastersim then
        return inst
    end

    inst:AddComponent("inspectable")

    inst:AddComponent("inventoryitem")
    -- 不设置 imagename / atlasname：默认图片名 "tide_crystal.tex"，图集已在 modmain.lua 注册

    inst:AddComponent("stackable")
    inst.components.stackable.maxsize = T.TIDE_CRYSTAL_STACK_SIZE

    MakeHauntableLaunch(inst)

    return inst
end

return Prefab("tide_crystal", fn, assets)
