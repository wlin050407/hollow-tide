-- scripts/hollowtide/log.lua
--
-- 统一日志。所有输出都带 [HollowTide] 前缀和 [server]/[client] 标签，
-- 方便在 client_log.txt / master_server_log.txt / caves_server_log.txt 里搜索。
--
-- 用法（只用 %s 占位符，参数会先 tostring，nil 也不会报错）：
--   local Log = require("hollowtide/log")
--   Log.Info("altar %s started event, players=%s", inst.GUID, #players)
--   Log.Debug(...)   -- 只有在 Mod 设置里打开"调试日志"时才输出
--   Log.Warn(...)

local Log = { debug_enabled = false }

local PREFIX = "[HollowTide]"

local function side()
    -- TheWorld 在世界加载完成前为 nil（例如 modmain 执行时）
    if TheWorld == nil then
        return "boot"
    end
    return TheWorld.ismastersim and "server" or "client"
end

local function format_message(msg, ...)
    local n = select("#", ...)
    if n == 0 then
        return tostring(msg)
    end
    local args = { ... }
    for i = 1, n do
        args[i] = tostring(args[i])
    end
    return string.format(tostring(msg), unpack(args, 1, n))
end

function Log.SetDebug(enabled)
    Log.debug_enabled = enabled == true
end

function Log.Info(msg, ...)
    print(PREFIX .. "[" .. side() .. "] " .. format_message(msg, ...))
end

function Log.Warn(msg, ...)
    print(PREFIX .. "[" .. side() .. "][WARN] " .. format_message(msg, ...))
end

function Log.Debug(msg, ...)
    if Log.debug_enabled then
        print(PREFIX .. "[" .. side() .. "][debug] " .. format_message(msg, ...))
    end
end

return Log
