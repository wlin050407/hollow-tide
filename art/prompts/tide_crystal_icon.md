# Prompt：潮蚀结晶 Tide Crystal（物品栏图标）

版本：v1（2026-10-10）
目标：64×64 物品栏图标的候选原图。生成 1024×1024，再用 `tools/art/prepare_icon.py` 缩小。

## 正向 prompt（英文效果通常更稳定）

```
single inventory item icon, a jagged sea-glass crystal shard grown from barnacles and a small
spiral shell, teal and pale aqua translucent crystal with a faint inner glow, dark ink outline,
thick wobbly hand-drawn line art, slightly crooked whimsical gothic storybook illustration,
muted desaturated palette, subtle paper texture, light from top left, centered, three-quarter view,
generous empty margin around the object, flat solid magenta background (#FF00FF),
no text, no ground shadow, no frame
```

## 反向 prompt（如果工具支持）

```
photorealistic, 3d render, glossy, smooth gradient, text, watermark, signature, frame, border,
multiple objects, cropped, cut off, background scenery, drop shadow, blurry edges
```

## 设计要点（写给筛选的人）

- 和原版蓝宝石区分：不是规整的切面宝石，而是**不规则、带藤壶/贝壳的海玻璃碎片**
- 64px 下的识别点：青绿色 + 螺旋小贝壳的剪影
- 世界观：被"深潮"侵蚀后结晶化的海洋残骸

## v2（2026-10-11）：单块结晶

v1 生成的是"一簇晶体长在石头上"，作为物品不像一块结晶，改作可开采的潮蚀晶簇（`tide_crystal_cluster`）。
v2 去掉石块底座，只要一两块结晶。Claude 建议的 prompt（**实际使用的版本待补**）：

```
single inventory item icon, one loose jagged sea-glass crystal shard (or two small shards fused
together), lying at a slight tilt, a few tiny barnacles clinging to its base, teal and pale aqua
translucent crystal with faint glowing specks inside, dark ink outline, thick wobbly hand-drawn
line art, slightly crooked whimsical gothic storybook illustration, muted desaturated palette,
subtle paper texture, light from top left, centered, three-quarter view, simple bold silhouette
readable at small size, generous empty margin, flat solid magenta background (#FF00FF),
no rocks, no seaweed, no ground, no text, no ground shadow, no frame
```

## 记录

| 日期 | 工具 / 模型 | 种子 | 结果文件 | 备注 |
|---|---|---|---|---|
| 2026-10-11 | ChatGPT（模型待补） | n/a | `art/source/tide_crystal/tide_crystal_v1_chatgpt.png` | 晶簇造型；先做物品，后改作可开采晶簇 |
| 2026-10-11 | ChatGPT（模型待补） | n/a | `art/source/tide_crystal/tide_crystal_v2_chatgpt.png` | 单块结晶 + 藤壶，品红背景；现在的物品图标和地面外观 |
| 2026-10-11 | ChatGPT（模型待补，prompt 待补） | n/a | `art/source/tide_crystal/tide_crystal_cluster_med_chatgpt.png` | 在 v1 晶簇图基础上编辑：开裂、顶端断掉（晶簇 med 阶段），透明背景 |
| 2026-10-11 | ChatGPT（模型待补，prompt 待补） | n/a | `art/source/tide_crystal/tide_crystal_cluster_low_chatgpt.png` | 在 v1 晶簇图基础上编辑：只剩一小簇碎晶（晶簇 low 阶段），透明背景 |
