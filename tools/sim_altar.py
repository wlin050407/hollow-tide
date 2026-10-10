#!/usr/bin/env python3
"""
深潮祭坛行为模拟：在一个最小的假游戏环境里**真正运行** mod/scripts/prefabs/tide_altar.lua，
把"唤潮 → 冷却 → 恢复"走一遍，检查状态机和每帧亮度渐变。

为什么需要：check_mod.py 只执行 prefab 构造函数，状态切换、计时器、每帧更新这些回调它跑不到；
这里补上这一块，改了祭坛逻辑或 tuning.lua 里的祭坛数值后跑一下，不用每次都进游戏才发现 Lua 报错。

模拟的范围（只有 tide_altar 用到的部分，不是游戏）：
  实体 / AnimState / Light（记录最后一次调用）、按帧推进的调度器（DoPeriodicTask / DoTaskInTime）、
  timer / activatable / workable 组件、net_tinybyte、TheWorld.ismastersim、TheNet:IsDedicated()。
所以它不能代替进游戏：画面、绘制顺序、联机同步都要进游戏看。

检查的场景（期望值从 tuning.lua 读，改数值不用改这里）：
  1. 主机（服务器 + 画面）：渐亮单调、按时全亮、呼吸范围、结束后渐暗熄灭、叠加层删除、冷却变暗、每帧更新会停
  2. 客户端在唤潮中途走近：直接全亮；服务器改成冷却后渐暗
  3. 专用服务器：不生成漩涡和发光叠加层，但灯光照常
  4. 读档进入冷却：直接是变暗状态

用法：python tools/sim_altar.py        （依赖 lupa，见 tools/requirements.txt）
退出码：0 = 全部通过，1 = 有检查没通过
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from lupa import lua51
except ImportError:  # pragma: no cover
    print("缺少依赖 lupa：请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)

MOD = Path(__file__).resolve().parents[1] / "mod"
DT = 1 / 30

FAKE_GAME = r"""
local sim = { t = 0, tasks = {}, dedicated = false }
FRAMES = 1/30
function GetTime() return sim.t end
LAYER_BACKGROUND = 1
ACTIONS = { HAMMER = "HAMMER" }
TUNING = setmetatable({}, { __index = function() return 1 end })
TheNet = { IsDedicated = function() return sim.dedicated end }
TheWorld = { ismastersim = true }

local function schedule(inst, period, fn, delay, limit, ...)
    local task = { inst = inst, period = period, fn = fn, next = sim.t + (delay or period), limit = limit, args = { ... } }
    function task:Cancel() self.cancelled = true end
    table.insert(sim.tasks, task)
    return task
end

-- 记录"最后一次调用的参数"的假对象
local function make_recorder()
    local r = { calls = {} }
    return setmetatable(r, { __index = function(t, k)
        local f = function(self, ...) t.calls[k] = { ... } end
        rawset(t, k, f)
        return f
    end })
end

function CreateEntity()
    local inst = { GUID = #sim.tasks + 1000, components = {}, tags = {}, listeners = {}, valid = true }
    inst.entity = {
        AddTransform = function()
            inst.Transform = make_recorder()
            inst.Transform.GetWorldPosition = function() return 0, 0, 0 end
        end,
        AddAnimState = function() inst.AnimState = make_recorder() end,
        AddSoundEmitter = function() inst.SoundEmitter = make_recorder() end,
        AddLight = function()
            inst.Light = make_recorder()
            inst.Light.enabled = false
            inst.Light.Enable = function(self, v) self.enabled = v end
            inst.Light.SetRadius = function(self, v) self.radius = v end
            inst.Light.SetIntensity = function(self, v) self.intensity = v end
        end,
        AddNetwork = function() end,
        SetPristine = function() end,
        SetCanSleep = function() end,
        SetParent = function(self, p) inst.parent = p end,
    }
    function inst:AddTag(t) self.tags[t] = true end
    function inst:RemoveTag(t) self.tags[t] = nil end
    function inst:HasTag(t) return self.tags[t] == true end
    function inst:AddOrRemoveTag(t, c) if c then self:AddTag(t) else self:RemoveTag(t) end end
    function inst:ListenForEvent(ev, fn) self.listeners[ev] = self.listeners[ev] or {}; table.insert(self.listeners[ev], fn) end
    function inst:PushEvent(ev, data) for _, fn in ipairs(self.listeners[ev] or {}) do fn(self, data) end end
    function inst:DoPeriodicTask(p, fn, delay, ...) return schedule(self, p, fn, delay, nil, ...) end
    function inst:DoTaskInTime(t, fn, ...) return schedule(self, t, fn, t, 1, ...) end
    function inst:IsValid() return self.valid end
    function inst:IsAsleep() return false end
    function inst:Remove() self.valid = false; if self.OnRemoveEntity then self:OnRemoveEntity() end end
    function inst:SetDeploySmartRadius() end
    function inst:GetDisplayName() return "tester" end
    function inst:AddComponent(name)
        local c = {}
        if name == "timer" then
            c.timers = {}
            function c:StartTimer(n, t)
                self.timers[n] = schedule(inst, t, function() self.timers[n] = nil; inst:PushEvent("timerdone", { name = n }) end, t, 1)
            end
            function c:StopTimer(n) if self.timers[n] then self.timers[n]:Cancel(); self.timers[n] = nil end end
            function c:TimerExists(n) return self.timers[n] ~= nil end
        elseif name == "workable" then
            function c:SetWorkable(v) self.workable = v end
        end
        setmetatable(c, { __index = function() return function() end end })
        self.components[name] = c
    end
    return inst
end

function net_tinybyte(guid, name, event)
    local nv = { v = 0 }
    function nv:value() return self.v end
    function nv:set(v) self.v = v end
    return nv
end

function SpawnPrefab(name) local e = CreateEntity(); e.entity.AddTransform(); return e end
function MakeObstaclePhysics() end
function MakeHauntableWork() end
function MakePlacer() return {} end
function Asset() return {} end
function Prefab(name, fn) return { name = name, fn = fn } end

function sim.reset(ismastersim, dedicated)
    sim.t = 0
    sim.tasks = {}
    sim.dedicated = dedicated
    TheWorld.ismastersim = ismastersim
end

function sim.step()
    sim.t = sim.t + FRAMES
    local due = {}
    for _, task in ipairs(sim.tasks) do
        if not task.cancelled and task.next <= sim.t + 1e-9 then table.insert(due, task) end
    end
    for _, task in ipairs(due) do
        if not task.cancelled then
            task.fn(task.inst, unpack(task.args))
            if task.limit == 1 then task.cancelled = true else task.next = task.next + task.period end
        end
    end
end

function sim.active_tasks(inst)
    local n = 0
    for _, task in ipairs(sim.tasks) do if not task.cancelled and task.inst == inst then n = n + 1 end end
    return n
end

return sim
"""


class Checker:
    def __init__(self):
        self.failed = 0

    def check(self, cond: bool, msg: str, detail=None) -> None:
        if cond:
            print(f"  [OK]    {msg}")
        else:
            self.failed += 1
            print(f"  [ERROR] {msg}" + (f"：{detail}" if detail is not None else ""))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 管道输出时默认不是 UTF-8
    except AttributeError:  # pragma: no cover
        pass

    lua = lua51.LuaRuntime(unpack_returned_tuples=True)
    sim = lua.execute(FAKE_GAME)
    scripts = (MOD / "scripts").as_posix()
    lua.execute(f'package.path = "{scripts}/?.lua;" .. package.path')
    lua.execute('package.preload["prefabutil"] = function() return {} end')
    lua.execute('package.preload["hollowtide/log"] = function() '
                'local L = {}; L.Debug = function() end; L.Info = function() end; L.Warn = function() end; return L end')
    T = lua.eval('require("hollowtide/tuning")')
    prefab = lua.execute((MOD / "scripts/prefabs/tide_altar.lua").read_text(encoding="utf-8"))
    prefab = prefab[0] if isinstance(prefab, tuple) else prefab
    c = Checker()

    def spawn(ismastersim: bool, dedicated: bool):
        sim.reset(ismastersim, dedicated)
        return prefab.fn()

    def sample(inst) -> dict:
        calls = inst.AnimState.calls
        mult = calls["SetMultColour"]
        glow = inst._glowfx
        return {
            "t": sim.t, "glow": inst._glow, "dim": inst._dim,
            "light": bool(inst.Light.enabled), "radius": inst.Light.radius or 0, "intensity": inst.Light.intensity or 0,
            "tint": mult[1] if mult else 1.0,
            "overlay": None if glow is None else glow.AnimState.calls["SetMultColour"][4],
            "swirl": inst._swirl is not None, "tasks": sim.active_tasks(inst),
        }

    def run(inst, seconds: float) -> list[dict]:
        rows = []
        for _ in range(int(round(seconds / DT))):
            sim.step()
            rows.append(sample(inst))
        return rows

    def at(rows: list[dict], t: float) -> dict:
        return min(rows, key=lambda r: abs(r["t"] - t))

    fade_in, fade_out, dim_fade = T.ALTAR_FADE_IN, T.ALTAR_FADE_OUT, T.ALTAR_DIM_FADE
    active, cooldown = T.ALTAR_ACTIVE_TIME, T.ALTAR_COOLDOWN
    r_lo = T.ALTAR_LIGHT_RADIUS - T.ALTAR_LIGHT_BREATH
    r_hi = T.ALTAR_LIGHT_RADIUS + T.ALTAR_LIGHT_BREATH

    # 1. 主机
    print(f"[1] 主机：唤潮 {active} 秒（渐亮 {fade_in} 秒、渐暗 {fade_out} 秒）→ 冷却 {cooldown} 秒（变暗 {dim_fade} 秒）")
    inst = spawn(True, False)
    inst.components.activatable.OnActivate(inst, None)
    rows = run(inst, active + cooldown + max(fade_out, dim_fade) + 2)
    rising = [r["glow"] for r in rows if r["t"] <= fade_in + DT]
    c.check(all(b >= a for a, b in zip(rising, rising[1:])), "渐亮过程单调")
    c.check(at(rows, fade_in / 2)["glow"] < 0.9 and at(rows, fade_in + 2 * DT)["glow"] == 1,
            f"约 {fade_in} 秒后全亮，中途是半亮", (at(rows, fade_in / 2)["glow"], at(rows, fade_in + 2 * DT)["glow"]))
    breathing = [r for r in rows if fade_in + 0.1 <= r["t"] <= active - 0.1]
    radii = [r["radius"] for r in breathing]
    c.check(min(radii) >= r_lo - 1e-6 and max(radii) <= r_hi + 1e-6 and max(radii) - min(radii) > 0.5 * (r_hi - r_lo),
            f"呼吸时半径在 {r_lo:g}–{r_hi:g} 之间", (round(min(radii), 3), round(max(radii), 3)))
    jumps = max(abs(b["radius"] - a["radius"]) for a, b in zip(breathing, breathing[1:]))
    c.check(jumps < 0.05, "呼吸平滑（每帧半径变化 < 0.05）", round(jumps, 4))
    c.check(all(r["overlay"] == 1 and r["swirl"] for r in breathing), "全亮时发光叠加层不透明、漩涡在")
    end = active + fade_out + 0.2
    r_end = at(rows, end)
    c.check(not r_end["light"] and r_end["overlay"] is None and not r_end["swirl"],
            f"结束后 {fade_out} 秒内渐暗熄灭，叠加层和漩涡已删除", r_end)
    c.check(abs(at(rows, active + dim_fade + 0.2)["tint"] - T.ALTAR_COOLDOWN_TINT) < 1e-6,
            f"冷却变暗到 {T.ALTAR_COOLDOWN_TINT}")
    c.check(at(rows, end + 0.5)["tasks"] == 1, "冷却中只剩冷却计时器（每帧更新已停止）", at(rows, end + 0.5)["tasks"])
    last = rows[-1]
    c.check(abs(last["tint"] - 1) < 1e-6 and last["tasks"] == 0, "冷却结束后恢复原色、没有残留任务", last)

    # 2. 客户端中途走近
    print("[2] 客户端在唤潮中途走近，然后服务器切到冷却")
    inst = spawn(False, False)
    inst._state.v = 1  # 客户端收到的 netvar 已经是 ACTIVE
    sim.step()
    r = sample(inst)
    c.check(r["glow"] == 1 and r["overlay"] == 1 and r["swirl"], "进入视野时直接全亮（不从头渐变）", r)
    inst._state.v = 2
    inst.PushEvent(inst, "tide_altar_statedirty", None)
    rows = run(inst, max(fade_out, dim_fade) + 1)
    c.check(0 < at(rows, fade_out / 2)["glow"] < 1, "收到冷却后渐暗")
    c.check(rows[-1]["glow"] == 0 and rows[-1]["overlay"] is None and rows[-1]["tasks"] == 0,
            "渐暗结束：叠加层删除、每帧更新停止", rows[-1])

    # 3. 专用服务器
    print("[3] 专用服务器")
    inst = spawn(True, True)
    inst.components.activatable.OnActivate(inst, None)
    r = run(inst, fade_in + 1)[-1]
    c.check(r["overlay"] is None and not r["swirl"] and r["light"] and r["glow"] == 1,
            "不生成漩涡和发光叠加层，灯光照常开", r)

    # 4. 读档进入冷却
    print("[4] 读档时冷却计时器还在")
    inst = spawn(True, False)
    inst.components.timer.StartTimer(inst.components.timer, "cooldown", 20)
    inst.OnLoad(inst, None)
    r = sample(inst)
    c.check(r["dim"] == 1 and abs(r["tint"] - T.ALTAR_COOLDOWN_TINT) < 1e-6, "直接是变暗状态（不从头渐变）", r)

    print()
    print("全部通过" if c.failed == 0 else f"{c.failed} 项没通过")
    return 0 if c.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
