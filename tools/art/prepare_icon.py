#!/usr/bin/env python3
"""
把一张 AI 生成（或手绘）的物品图整理成 DST 物品栏图标用的 64x64 透明 PNG，并生成审查预览图。

做的事情（全部可重复、可脚本化）：
  1. 读入图片；如果没有透明通道，可用 --key-color 抠掉纯色背景（算法在 remove_bg.py；推荐先单独运行它）
  2. 去掉几乎透明的"雾边"（alpha < --alpha-floor）
  3. 按不透明区域裁切，等比缩放到 (size - 2*padding)，居中放到透明画布上
     缩放在"预乘 alpha"空间里做，避免透明边缘出现白边/黑边
  4. 可选：加一圈深色描边（--outline，单位是最终像素），模拟原版图标的粗墨线轮廓
  5. 自检：边缘是否透明、主体占比、浅色光晕像素数量
  6. 输出：
       <out_dir>/<name>.png                    -> 交给 tools/art/png2tex.py 转成 .tex + .xml
       <preview_dir>/<name>_preview.png        -> 深色格子 / 浅色背景 / 放大对比，给人审查

它不做的事：风格判断、构图、和原版美术的一致性 —— 这些必须由人审查预览图后决定。

用法示例：
  python tools/art/prepare_icon.py art/source/tide_crystal/tide_crystal_v3_nobg.png --name tide_crystal
  python tools/art/prepare_icon.py raw.png --name tide_crystal --key-color auto --outline 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:  # pragma: no cover
    print("缺少依赖 Pillow：请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from remove_bg import auto_key, key_out, parse_color  # noqa: E402  去背景（带边缘去色溢出）统一用 remove_bg.py


def fit_to_canvas(img: Image.Image, size: int, padding: int) -> Image.Image:
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        raise SystemExit("图片完全透明：去背景步骤可能把主体也抠掉了")
    obj = img.crop(bbox)
    inner = size - 2 * padding
    scale = min(inner / obj.width, inner / obj.height)
    new_size = (max(1, round(obj.width * scale)), max(1, round(obj.height * scale)))
    # 在预乘 alpha 空间缩放，避免半透明边缘混入背景色
    resized = obj.convert("RGBa").resize(new_size, Image.LANCZOS).convert("RGBA")
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(resized, ((size - new_size[0]) // 2, (size - new_size[1]) // 2))
    return canvas


def add_outline(img: Image.Image, px: int, color: tuple[int, int, int]) -> Image.Image:
    alpha = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    grown = alpha.filter(ImageFilter.MaxFilter(2 * px + 1))
    base = Image.new("RGBA", img.size, color + (0,))
    base.putalpha(grown)
    base.alpha_composite(img)
    return base


def clean_alpha(img: Image.Image, floor: int) -> Image.Image:
    a = img.getchannel("A").point(lambda v: 0 if v < floor else v)
    out = img.copy()
    out.putalpha(a)
    return out


def self_check(img: Image.Image) -> list[str]:
    notes = []
    w, h = img.size
    a = img.getchannel("A")
    edge = [a.getpixel((x, 0)) for x in range(w)] + [a.getpixel((x, h - 1)) for x in range(w)] + \
           [a.getpixel((0, y)) for y in range(h)] + [a.getpixel((w - 1, y)) for y in range(h)]
    if max(edge) > 0:
        notes.append("边缘有不透明像素：图标会贴到格子边上，建议增大 --padding")
    opaque = sum(a.histogram()[128:])
    ratio = opaque / (w * h)
    if ratio < 0.15:
        notes.append(f"主体只占 {ratio:.0%}：在物品栏里会显得太小")
    elif ratio > 0.80:
        notes.append(f"主体占 {ratio:.0%}：几乎填满格子，轮廓可能不清楚")
    px = img.load()
    halo = 0
    for y in range(h):
        for x in range(w):
            r, g, b, al = px[x, y]
            if 0 < al < 160 and min(r, g, b) > 200:
                halo += 1
    if halo > w * h * 0.01:
        notes.append(f"发现 {halo} 个半透明的浅色像素：可能是白底残留的光晕，建议重新去背景")
    return notes


def make_preview(icon: Image.Image, path: Path) -> None:
    pad = 16
    slot = 80
    panels = [((44, 38, 34), "dark"), ((217, 201, 163), "light")]
    scales = [1, 2, 4]
    width = pad + sum((icon.width * s + pad) for s in scales) + slot + pad
    height = pad + len(panels) * (icon.height * max(scales) + pad)
    sheet = Image.new("RGBA", (width, height), (24, 24, 24, 255))
    draw = ImageDraw.Draw(sheet)
    y = pad
    for bg, _ in panels:
        x = pad
        # 模拟物品栏格子
        draw.rectangle([x, y, x + slot, y + slot], fill=bg + (255,), outline=(90, 80, 70, 255), width=3)
        sheet.alpha_composite(icon, (x + (slot - icon.width) // 2, y + (slot - icon.height) // 2))
        x += slot + pad
        for s in scales:
            big = icon.resize((icon.width * s, icon.height * s), Image.NEAREST)
            draw.rectangle([x, y, x + big.width, y + big.height], fill=bg + (255,))
            sheet.alpha_composite(big, (x, y))
            x += big.width + pad
        y += icon.height * max(scales) + pad
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="把 AI 生成图整理成 DST 物品栏图标（64x64 透明 PNG）")
    ap.add_argument("input", type=Path, help="源图（建议 PNG；最好已经去掉背景）")
    ap.add_argument("--name", required=True, help="输出名，必须等于 prefab 名，例如 tide_crystal")
    ap.add_argument("--size", type=int, default=64, help="输出边长，原版物品栏格子为 64")
    ap.add_argument("--padding", type=int, default=3, help="四周留白像素")
    ap.add_argument("--key-color", default=None,
                    help="源图没有透明通道时抠掉的纯色背景：#RRGGBB 或 auto（取图片最外一圈的颜色）。"
                         "推荐先用 remove_bg.py 单独去背景，检查过再用")
    ap.add_argument("--tolerance", type=int, default=48, help="色键容差 (0-255)，见 remove_bg.py")
    ap.add_argument("--band", type=int, default=3, help="对背景外侧多少像素做反混合，见 remove_bg.py")
    ap.add_argument("--alpha-floor", type=int, default=12, help="低于此 alpha 的像素视为完全透明")
    ap.add_argument("--outline", type=int, default=0, help="描边宽度（最终像素，0 = 不加）")
    ap.add_argument("--outline-color", type=parse_color, default=(20, 16, 14), help="描边颜色 #RRGGBB")
    ap.add_argument("--out-dir", type=Path, default=REPO / "art" / "icons")
    ap.add_argument("--preview-dir", type=Path, default=REPO / "art" / "review")
    args = ap.parse_args()

    src = Image.open(args.input)
    img = src.convert("RGBA")
    has_alpha = img.getchannel("A").getextrema()[0] < 255

    if args.key_color:
        import numpy as np
        key = auto_key(np.asarray(img)[..., :3]) if args.key_color == "auto" else parse_color(args.key_color)
        print(f"色键去背景：{'#%02x%02x%02x' % key}")
        img = key_out(img, key, args.tolerance, args.band)
    elif not has_alpha:
        print("[WARN] 源图没有透明区域。请先去背景，或加 --key-color auto")

    img = clean_alpha(img, args.alpha_floor)
    icon = fit_to_canvas(img, args.size, args.padding + args.outline)
    if args.outline > 0:
        icon = add_outline(icon, args.outline, args.outline_color)
    icon = clean_alpha(icon, args.alpha_floor)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_png = args.out_dir / f"{args.name}.png"
    icon.save(out_png)
    preview = args.preview_dir / f"{args.name}_preview.png"
    make_preview(icon, preview)

    print(f"图标:   {out_png}")
    print(f"预览:   {preview}")
    notes = self_check(icon)
    for n in notes:
        print(f"[WARN] {n}")
    if not notes:
        print("[OK] 自检通过（风格与可读性仍需人工审查预览图）")
    print(f"下一步：python tools/art/png2tex.py {out_png}   然后运行 python tools/check_mod.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
