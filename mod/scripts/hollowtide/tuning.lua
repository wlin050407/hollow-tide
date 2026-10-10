-- scripts/hollowtide/tuning.lua
--
-- 所有可调数值集中在这里：调平衡只改这个文件，不要把数字散落在 prefab 里。
-- 这是普通 Lua 模块（全局环境），可以直接读取原版 TUNING。
-- 只放"已经在用"的数值；新功能落地时再加，不预先堆参数。

local T = {}

-- 潮蚀结晶
T.TIDE_CRYSTAL_STACK_SIZE = TUNING.STACK_SIZE_SMALLITEM -- 原版小物品堆叠上限（build 756039 为 40）

return T
