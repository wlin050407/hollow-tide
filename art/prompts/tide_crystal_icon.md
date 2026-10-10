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

## 记录

| 日期 | 工具 / 模型 | 种子 | 结果文件 | 备注 |
|---|---|---|---|---|
|  |  |  |  |  |
