-- scripts/prefabs/tide_crystal.lua
--
-- 潮蚀结晶（Tide Crystal）
-- 物品栏图标：原创（images/inventoryimages/tide_crystal.tex，在 modmain.lua 注册图集）。
-- 地面外观：原创动画包 anim/tide_crystal.zip（tools/art/make_anim.py 生成，见 docs/ART_PIPELINE.md）。
--   bank = build = "tide_crystal"，只有一个单帧动画 "idle"。
--
-- 结构遵循原版 prefab 的标准写法（参考原版 prefabs/gem.lua）：
--   1) 两端共有部分：Transform / AnimState / Network / 物理 / 标签
--   2) entity:SetPristine() —— 之前声明的内容服务器和客户端必须完全一致
--   3) 仅服务器部分：组件（inspectable / inventoryitem / stackable ...）
--      客户端拿不到 inst.components.xxx，只能通过 replica、标签和 netvar 读取状态。

local T = require("hollowtide/tuning")

local assets =
{
    Asset("ANIM", "anim/tide_crystal.zip"),
}

local function fn()
    local inst = CreateEntity()

    inst.entity:AddTransform()
    inst.entity:AddAnimState()
    inst.entity:AddSoundEmitter()
    inst.entity:AddNetwork()

    MakeInventoryPhysics(inst)

    inst.AnimState:SetBank("tide_crystal")
    inst.AnimState:SetBuild("tide_crystal")
    inst.AnimState:PlayAnimation("idle")

    inst.pickupsound = "gem"

    -- 参数沿用原版宝石（prefabs/gem.lua）；漂浮时水花特效的位置/大小需要进游戏看一眼
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
