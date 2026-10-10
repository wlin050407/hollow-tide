-- modmain/debug_hooks.lua（由 modmain.lua 通过 modimport 载入，运行在 Mod 沙盒）
--
-- 联机自检：每一端在世界加载完成后打印一次"我是谁"，用来确认 Mod 在服务器和客户端都正确加载。
-- 带洞穴的世界：地上(Master)、洞穴(Caves) 是两个独立的服务器进程，你的游戏本身只是客户端，
-- 因此三份日志里应该各有一行 "world ready"。

local _G = GLOBAL
local Log = require("hollowtide/log")

AddSimPostInit(function()
    local world = _G.TheWorld
    if world == nil then
        Log.Warn("SimPostInit fired but TheWorld is nil")
        return
    end

    -- 注意：运行中的世界实体 prefab 名固定是 "world"（prefabs/world.lua: SetPrefabName("world")），
    -- 真正的世界类型（forest / cave）在 world.worldprefab（gamelogic.lua: PopulateWorld）。
    Log.Info("world ready: world=%s ismastersim=%s dedicated=%s",
        world.worldprefab, world.ismastersim, _G.TheNet:IsDedicated())

    if world.ismastersim then
        -- 分片 ID 只在服务器端打印（地上通常是 "1"，洞穴是另一个编号）
        Log.Info("shard id: %s", _G.TheShard:GetShardId())

        -- 服务器端：玩家进出（ms_playerjoined / ms_playerleft 由 player_common.lua 在服务器上推送）
        world:ListenForEvent("ms_playerjoined", function(_, player)
            Log.Info("player joined: %s", player ~= nil and player:GetDisplayName() or nil)
        end)
        world:ListenForEvent("ms_playerleft", function(_, player)
            Log.Info("player left: %s", player ~= nil and player:GetDisplayName() or nil)
        end)
    else
        -- 客户端：本地玩家实体就绪
        world:ListenForEvent("playeractivated", function(_, player)
            Log.Info("local player activated: %s", player ~= nil and player:GetDisplayName() or nil)
        end)
    end
end)
