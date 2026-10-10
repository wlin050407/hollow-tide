# 潮蚀晶簇（Tide Crystal Cluster）—— 半页设计

状态：v0（2026-10-11），只能用控制台生成；在世界里从哪来还没定（见最后）。

## 是什么

长在礁石上的一簇潮蚀结晶。用**镐**开采，挖碎后掉落潮蚀结晶。
外观用的是第一版 ChatGPT 结晶图（带石块底座的那张）；潮蚀结晶物品本身换成了第二版的单块结晶图。
挖的过程中有三档外观（同原版巨石）：`full` 完整 → `med` 中间最高的晶体断成残桩 → `low` 只剩短桩和石块。
`med` / `low` 目前是**占位图**：由 `art/source/tide_crystal/placeholder_stages.py` 从完整图上切出来，正式美术到了直接替换。

## 规则（数值都在 `scripts/hollowtide/tuning.lua`）

| 项 | 值 | 参考 |
|---|---|---|
| 开采工具 | 镐（`ACTIONS.MINE`） | 原版巨石、月岛裂隙水晶都是镐；锤子是拆玩家建筑的，铲子是挖植物的 |
| 需要挖几下 | 6（= `TUNING.ROCKS_MINE`） | 原版巨石 |
| 掉落 | 必定 2 个结晶 + 50% 再多 1 个 | 先定一个能测的数，平衡以后调 |
| 挖了一半存档 | 剩余次数会保存（`workable.savestate = true`） | 原版 `lunarrift_crystals.lua` |
| 挖碎时 | 晶体碎裂特效 `mining_moonglass_fx` + 烟尘 `collapse_small`，然后消失，不会再生 | 原版 `lunarrift_crystals.lua` |
| 每一镐的特效和声音 | 晶体版（标签 `crystal`） | `commonstates.lua` `PlayMiningFX` |
| 标签 `boulder` | 按原版巨石对待：熊獾冲撞撞碎时**不掉落**（任何可开采物都会被撞碎，带这个标签的不给掉落，和原版巨石、树一致） | `bearger.lua` `OnDestroyOther` |
| 碰撞半径 | 0.45（按美术底座宽度估的） | 原版巨石 1，裂隙水晶 0.6 |
| 破损外观 | 剩余次数 ≥ 2/3 总数：`full`；≥ 1/3：`med`；更少：`low`（挖 6 下时：第 3 下变 med，第 5 下变 low）；读档时按剩余次数恢复 | `rocks.lua` `OnWork`；`workable.lua` `SetOnLoadFn` |

## 这一版不做

- 正式的破损阶段美术（现在是脚本切出来的占位图）
- 世界生成、小地图图标、再生、冬季积雪
- 被挖时的额外效果（比如溅水、吸引怪物）

## 待决定：晶簇从哪里来

1. **祭坛事件成功后在祭坛周围长出晶簇**（替代"直接掉结晶"）：奖励变成"挖出来"，画面反馈更强，也让晶簇和祭坛玩法绑在一起
2. **世界生成时分布在海边**：结晶多了一个和祭坛无关的来源，祭坛的奖励需要另外设计
3. 两者都有

在决定之前，晶簇只能用 `c_spawn("tide_crystal_cluster")` 生成。

## 测试

见 `docs/TESTING.md`「潮蚀晶簇」。
