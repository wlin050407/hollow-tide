-- scripts/hollowtide/tuning.lua
--
-- 所有可调数值集中在这里：调平衡只改这个文件，不要把数字散落在 prefab 里。
-- 这是普通 Lua 模块（全局环境），可以直接读取原版 TUNING。
-- 只放"已经在用"的数值；新功能落地时再加，不预先堆参数。

local T = {}

-- 潮蚀结晶
T.TIDE_CRYSTAL_STACK_SIZE = TUNING.STACK_SIZE_SMALLITEM -- 原版小物品堆叠上限（build 756039 为 40）

-- 潮蚀晶簇（可用镐开采，见 docs/TIDE_CRYSTAL_CLUSTER_DESIGN.md）
T.TIDE_CRYSTAL_CLUSTER_MINE = TUNING.ROCKS_MINE      -- 要挖几下：同原版巨石（build 756039 为 6）
T.TIDE_CRYSTAL_CLUSTER_LOOT = 2                      -- 必定掉落的结晶数
T.TIDE_CRYSTAL_CLUSTER_BONUS_CHANCE = 0.5            -- 再多掉 1 个结晶的概率
T.TIDE_CRYSTAL_CLUSTER_RADIUS = 0.45                 -- 碰撞半径，对应美术底座宽度（原版巨石 1）

-- 深潮祭坛（见 docs/TIDE_ALTAR_DESIGN.md；现阶段只有状态切换，没有事件玩法）
T.ALTAR_RECIPE_ROCKS = 10                -- 配方：石头（占位数值）
T.ALTAR_RECIPE_CRYSTALS = 3              -- 配方：潮蚀结晶（占位数值）
T.ALTAR_HAMMER_WORK = 4                  -- 锤几下拆掉：同原版月晷
T.ALTAR_RADIUS = 0.5                     -- 碰撞半径，对应美术底座宽度（月晷 0.45）
T.ALTAR_ACTIVE_TIME = 30                 -- "唤潮"状态持续秒数（以后事件玩法也用它）
T.ALTAR_COOLDOWN = 60                    -- 冷却秒数
T.ALTAR_LIGHT_RADIUS = 3                 -- 唤潮时灯光半径（呼吸的中间值）
T.ALTAR_LIGHT_BREATH = 0.3               -- 呼吸时半径上下浮动多少（正弦，±）
T.ALTAR_LIGHT_BREATH_PERIOD = 4          -- 呼吸一次（亮 -> 暗 -> 亮）的秒数
T.ALTAR_FADE_IN = 2                      -- 唤潮时从暗到全亮的秒数（灯光、发光外观一起渐变）
T.ALTAR_FADE_OUT = 2                     -- 唤潮结束时从全亮到熄灭的秒数
T.ALTAR_DIM_FADE = 1.5                   -- 冷却变暗、冷却结束恢复的渐变秒数
T.ALTAR_LIGHT_INTENSITY = 0.7
T.ALTAR_LIGHT_FALLOFF = 0.7
T.ALTAR_LIGHT_COLOUR = { 40 / 255, 200 / 255, 200 / 255 }
T.ALTAR_LIGHT_OVERRIDE = 0.3             -- 唤潮时祭坛本身不受黑暗影响的程度（0..1）
T.ALTAR_SPLASH_INTERVAL = 1.5            -- 唤潮时底部溅水花的间隔秒数
T.ALTAR_SPLASH_RANGE = 0.8               -- 水花离祭坛中心的最大距离
T.ALTAR_COOLDOWN_TINT = 0.6              -- 冷却时变暗的程度（颜色乘以它）

return T
