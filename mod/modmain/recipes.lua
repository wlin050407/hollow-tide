-- modmain/recipes.lua（由 modmain.lua 通过 modimport 载入，运行在 Mod 沙盒）
--
-- 配方。AddRecipe2(名字, 材料, 科技, 配置, 过滤器)：见 modutil.lua / recipe.lua（docs/API_NOTES.md「配方」）。
-- 配方图标默认是 "<prefab>.tex"，图集已在 modmain.lua 里注册，所以配置里不用写 atlas / image。
-- 材料数量在 scripts/hollowtide/tuning.lua。

local _G = GLOBAL
local T = require("hollowtide/tuning")

AddRecipe2("tide_altar",
    {
        Ingredient("rocks", T.ALTAR_RECIPE_ROCKS),
        Ingredient("tide_crystal", T.ALTAR_RECIPE_CRYSTALS),
    },
    _G.TECH.SCIENCE_ONE,             -- 需要靠近科学机器
    {
        placer = "tide_altar_placer",
        min_spacing = 2,               -- 和 prefab 里 SetDeploySmartRadius(1) 对应（原版：半径 = min_spacing / 2）
        -- 唤潮中不能用拆解法杖拆（法杖不看 workable，只看这个；原版 shadow_beef_bell 同样写法）
        no_deconstruction = function(inst) return inst:HasTag("tide_altar_active") end,
    },
    { "STRUCTURES", "MAGIC" })
