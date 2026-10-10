#!/usr/bin/env python3
"""
去掉 AI 图的纯色背景（例如品红 #FF00FF），输出透明 PNG，边缘不留背景色的"彩边"。

为什么不能只把接近背景色的像素设成透明：轮廓和背景交界处的像素是两者的混合色
（黑色墨线 + 品红 = 暗紫色）。只改 alpha 不改颜色，缩小后就会出现一圈紫边。
这里的做法：
  1. 和背景色足够接近（每个通道差值都 <= tolerance）的像素 -> 背景，完全透明
  2. 紧挨着背景的一圈像素（宽 band 像素）-> 按"混合色 = a*前景 + (1-a)*背景色"反解出
     最小的 alpha 和前景色（与 GIMP 的 Color to Alpha 同一算法），去掉混进来的背景色
  3. 其余像素 -> 原样保留、完全不透明（物体内部即使有接近背景的颜色也不会被抠掉）

用法：
  python tools/art/remove_bg.py art/source/tide_crystal/tide_crystal_v2_chatgpt.png
  -> 默认输出到同目录 <原文件名>_nobg.png
之后把 _nobg.png 交给 prepare_icon.py（物品栏图标）或 make_anim.py（地面外观）。
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


def parse_color(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError("颜色格式应为 #RRGGBB")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def auto_key(rgb: np.ndarray) -> tuple[int, int, int]:
    """取图片最外一圈像素的中位数作为背景色（比只看四个角更抗渐变/暗角）。"""
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    return tuple(int(v) for v in np.median(border, axis=0))  # type: ignore[return-value]


def color_to_alpha(rgb: np.ndarray, key: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """把 rgb 看作 a*F + (1-a)*key，求最小的 a 使 F 落在 0..255 内。返回 (alpha 0..1, F)。"""
    c = rgb.astype(np.float32)
    k = key.astype(np.float32)
    up = np.where(c > k, (c - k) / np.maximum(255.0 - k, 1e-6), 0.0)
    down = np.where(c < k, (k - c) / np.maximum(k, 1e-6), 0.0)
    a = np.maximum(up, down).max(axis=-1)
    safe = np.maximum(a, 1e-6)[..., None]
    f = np.where(a[..., None] > 0, (c - k) / safe + k, c)
    return a, f.clip(0, 255)


def key_out(img: Image.Image, key: tuple[int, int, int], tolerance: int = 48, band: int = 3) -> Image.Image:
    rgba = np.asarray(img.convert("RGBA")).astype(np.float32)
    rgb = rgba[..., :3]
    k = np.array(key, dtype=np.float32)
    bg = (np.abs(rgb - k) <= tolerance).all(axis=-1)
    if band > 0:
        grown = Image.fromarray((bg * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * band + 1))
        edge = (np.asarray(grown) > 0) & ~bg
    else:
        edge = np.zeros_like(bg)
    a_edge, f_edge = color_to_alpha(rgb, k)
    out = rgba.copy()
    out[..., 3] = np.where(bg, 0.0, np.where(edge, a_edge * 255.0, rgba[..., 3]))
    out[..., :3] = np.where(edge[..., None], f_edge, rgb)
    out[bg] = 0.0
    return Image.fromarray(out.round().clip(0, 255).astype(np.uint8), "RGBA")


def spill_report(img: Image.Image, key: tuple[int, int, int]) -> int:
    """看得见的半透明边缘里仍然很像背景色的像素数（理想为 0）。"""
    a = np.asarray(img).astype(np.int32)
    semi = (a[..., 3] >= 32) & (a[..., 3] < 255)  # 太透明的像素看不见，不算
    near = (np.abs(a[..., :3] - np.array(key)) <= 64).all(axis=-1)
    return int((semi & near).sum())


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 管道输出（如 AI 助手调用）默认不是 UTF-8
    except AttributeError:  # pragma: no cover
        pass
    ap = argparse.ArgumentParser(description="去掉纯色背景，输出透明 PNG（边缘去色溢出）")
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, help="输出路径（默认：同目录 <名字>_nobg.png）")
    ap.add_argument("--key-color", default="auto", help="#RRGGBB 或 auto（取图片最外一圈的中位色）")
    ap.add_argument("--tolerance", type=int, default=48, help="每个通道与背景色的差值都不超过它就算背景")
    ap.add_argument("--band", type=int, default=3, help="对背景外侧多少像素做反混合")
    args = ap.parse_args()

    img = Image.open(args.input).convert("RGBA")
    rgb = np.asarray(img)[..., :3]
    key = auto_key(rgb) if args.key_color == "auto" else parse_color(args.key_color)
    out_img = key_out(img, key, args.tolerance, args.band)
    out = args.out or args.input.with_name(args.input.stem + "_nobg.png")
    out_img.save(out)

    alpha = np.asarray(out_img)[..., 3]
    print(f"背景色 #{key[0]:02x}{key[1]:02x}{key[2]:02x}，透明 {np.mean(alpha == 0):.1%}，"
          f"半透明边缘 {int(((alpha > 0) & (alpha < 255)).sum())} 像素")
    spill = spill_report(out_img, key)
    print(f"输出: {out}")
    if spill > 20:  # 原图 1000px 级别，零星几个像素缩小后看不出来
        print(f"[WARN] 还有 {spill} 个边缘像素接近背景色，缩小后可能看到彩边；检查预览，或调大 --band")
    else:
        print(f"[OK] 边缘没有明显的背景色残留（{spill} 个零星像素，可忽略）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
