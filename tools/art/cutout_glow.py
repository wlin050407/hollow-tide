#!/usr/bin/env python3
"""
把"黑色背景 + 发光效果"的图抠成透明 PNG，借用另一张已经透明、构图相同的图（通常是同一物体的平时状态）的轮廓。

为什么需要：AI 画发光状态时经常给黑背景。黑背景不能直接色键——物体的墨线也是黑的，会被一起抠掉。
这里分两部分处理：
  * 物体本身：直接用参考图（透明背景）的不透明区域，墨线完整保留
  * 物体外面的光晕、水珠：看成"亮光叠在黑底上"，按亮度反推透明度（越暗越透明），颜色除以透明度还原
两张图必须完全对齐（AI 在原图上编辑的结果通常是对齐的；不确定时先用 align_stages.py）。

用法：
  python tools/art/cutout_glow.py art/source/tide_altar/tide_altar_idle_chatgpt.png \\
      art/source/tide_altar/tide_altar_active_chatgpt.png
  -> art/source/tide_altar/tide_altar_active_chatgpt_nobg.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageFilter
except ImportError as e:  # pragma: no cover
    print(f"缺少依赖：{e}。请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)


def cutout(body_ref: Image.Image, glow_img: Image.Image, floor: int = 14, grow: int = 2) -> Image.Image:
    """floor：亮度低于它的背景噪点当作纯黑；grow：参考轮廓外扩几像素，盖住边缘的细小错位。"""
    if body_ref.size != glow_img.size:
        raise ValueError(f"两张图尺寸不同：{body_ref.size} / {glow_img.size}")
    ref_a = body_ref.convert("RGBA").getchannel("A")
    if grow > 0:
        ref_a = ref_a.filter(ImageFilter.MaxFilter(2 * grow + 1))
    body = np.asarray(ref_a).astype(np.float32) / 255.0
    rgb = np.asarray(glow_img.convert("RGB")).astype(np.float32)
    glow = np.clip((rgb.max(axis=-1) - floor) / (255.0 - floor), 0.0, 1.0)
    alpha = np.maximum(body, glow)
    unmult = rgb / np.maximum(glow[..., None], 1e-3)
    out_rgb = np.where(body[..., None] >= glow[..., None], rgb, unmult)
    out = np.dstack([out_rgb.clip(0, 255), alpha * 255.0]).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def main() -> int:
    ap = argparse.ArgumentParser(description="黑背景发光图 -> 透明 PNG（物体轮廓取自参考图）")
    ap.add_argument("reference", type=Path, help="透明背景、构图相同的参考图（如平时状态）")
    ap.add_argument("glow", type=Path, help="黑背景的发光图")
    ap.add_argument("--out", type=Path, help="输出路径（默认：<glow 名字>_nobg.png）")
    ap.add_argument("--floor", type=int, default=14, help="背景噪点阈值 0-255")
    args = ap.parse_args()

    ref, glow = Image.open(args.reference), Image.open(args.glow)
    rgb = np.asarray(glow.convert("RGB")).astype(np.float32)
    outside = np.asarray(ref.convert("RGBA").getchannel("A").filter(ImageFilter.MaxFilter(41))) == 0
    if outside.any() and rgb[outside].mean() > 30:
        print(f"[WARN] 参考轮廓以外的平均亮度 {rgb[outside].mean():.0f}：背景可能不是黑色，结果会发灰")
    out_img = cutout(ref, glow, args.floor)
    out = args.out or args.glow.with_name(args.glow.stem + "_nobg.png")
    out_img.save(out)
    print(f"输出: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
