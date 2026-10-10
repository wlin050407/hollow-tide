#!/usr/bin/env python3
"""
把 AI 画的破损阶段图对齐到完整图上（让底座在每个阶段都落在同一个位置），输出和完整图同样大小的画布。

为什么需要：让 AI "在原图基础上改"时，它常常会把整体挪一点、缩放一点。make_anim.py stages 要求各阶段图
已经对齐，否则挖的时候底座会在原地跳动。

怎么对齐：只看完整图底部那一截（默认底部 25%，也就是石块底座），在一定范围内搜索缩放和平移，
让阶段图的不透明区域和完整图底座重合得最多（IoU 最大）。上面的晶体本来就不一样，不参与比较。

用法：
  python tools/art/align_stages.py art/source/tide_crystal/tide_crystal_v1_chatgpt.png \\
      art/source/tide_crystal/tide_crystal_cluster_med_chatgpt.png art/source/tide_crystal/tide_crystal_cluster_low_chatgpt.png \\
      --out-names tide_crystal_cluster_med.png tide_crystal_cluster_low.png
输出：同目录下的对齐后图片 + art/review/<完整图名>_onion.png（重叠对比：红色 = 完整图轮廓，阶段图半透明叠在上面）
对齐结果不满意时可以用 --scale / --dx / --dy 手动指定（单位：原图像素）。
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

REPO = Path(__file__).resolve().parents[2]
DOWN = 4  # 搜索时缩小 4 倍，速度快，精度 4 像素


def alpha_mask(img: Image.Image, floor: int = 128) -> np.ndarray:
    return np.asarray(img.getchannel("A")) > floor


def place(img: Image.Image, size: tuple[int, int], scale: float, dx: float, dy: float,
          pivot: tuple[float, float]) -> Image.Image:
    """以 pivot（原图坐标）为中心缩放 scale，再平移 (dx, dy)，放到 size 大小的透明画布上。"""
    w, h = img.size
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    scaled = img.convert("RGBa").resize((nw, nh), Image.LANCZOS).convert("RGBA") if scale != 1.0 else img
    ox = pivot[0] - pivot[0] * scale + dx
    oy = pivot[1] - pivot[1] * scale + dy
    canvas = Image.new("RGBA", size)
    canvas.paste(scaled, (round(ox), round(oy)))
    return canvas


def search(ref: Image.Image, stage: Image.Image, band: float, scales: np.ndarray, max_shift: int):
    rm = alpha_mask(ref)
    ys, xs = np.nonzero(rm)
    y_top_band = int(ys.max() - (ys.max() - ys.min()) * band)
    pivot = ((xs.min() + xs.max()) / 2, float(ys.max()))  # 以底边中点为缩放中心
    small = (ref.width // DOWN, ref.height // DOWN)
    ref_s = np.asarray(Image.fromarray(rm.astype(np.uint8) * 255).resize(small, Image.BILINEAR)) > 127
    band_rows = slice(y_top_band // DOWN, ref_s.shape[0])
    ref_band = ref_s[band_rows]
    best = (-1.0, 1.0, 0, 0)
    r = max_shift // DOWN
    for s in scales:
        moved = place(stage, ref.size, float(s), 0, 0, pivot)
        m = np.asarray(moved.getchannel("A").resize(small, Image.BILINEAR)) > 127
        mys, mxs = np.nonzero(m)
        # 初始猜测：底边对齐、水平中心对齐，再在附近搜索
        gx = round(pivot[0] / DOWN - (mxs.min() + mxs.max()) / 2)
        gy = round(pivot[1] / DOWN - mys.max())
        for ddy in range(-r, r + 1):
            for ddx in range(-r, r + 1):
                tx, ty = gx + ddx, gy + ddy
                shifted = np.zeros_like(m)
                src = m[max(0, -ty):m.shape[0] - max(0, ty), max(0, -tx):m.shape[1] - max(0, tx)]
                shifted[max(0, ty):max(0, ty) + src.shape[0], max(0, tx):max(0, tx) + src.shape[1]] = src
                sb = shifted[band_rows]
                inter = np.logical_and(sb, ref_band).sum()
                union = np.logical_or(sb, ref_band).sum()
                iou = inter / union if union else 0.0
                if iou > best[0]:
                    best = (iou, float(s), tx * DOWN, ty * DOWN)
    return best, pivot, y_top_band


def onion(ref: Image.Image, aligned: list[Image.Image], path: Path) -> None:
    """完整图轮廓（红线）+ 各阶段半透明叠放，并排输出。"""
    rm = alpha_mask(ref)
    edge = Image.fromarray((rm * 255).astype(np.uint8)).filter(ImageFilter.FIND_EDGES)
    edge = np.asarray(edge.filter(ImageFilter.MaxFilter(5))) > 0
    tiles = []
    for im in [ref] + aligned:
        bg = Image.new("RGBA", ref.size, (124, 110, 84, 255))
        bg.alpha_composite(im)
        a = np.asarray(bg).copy()
        a[edge] = (255, 40, 40, 255)
        tiles.append(Image.fromarray(a).resize((ref.width // 3, ref.height // 3), Image.LANCZOS))
    sheet = Image.new("RGBA", (sum(t.width for t in tiles), tiles[0].height))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows 管道输出（如 AI 助手调用）默认不是 UTF-8
    except AttributeError:  # pragma: no cover
        pass
    ap = argparse.ArgumentParser(description="把破损阶段图的底座对齐到完整图")
    ap.add_argument("ref", type=Path, help="完整图（基准）")
    ap.add_argument("stages", type=Path, nargs="+", help="要对齐的阶段图")
    ap.add_argument("--out-names", nargs="+", help="输出文件名（和 stages 一一对应，放在各自同目录）；默认 <名字>_aligned.png")
    ap.add_argument("--band", type=float, default=0.25, help="用完整图底部多少比例的高度来对齐（默认 0.25）")
    ap.add_argument("--scale-range", default="0.85,1.15", help="缩放搜索范围")
    ap.add_argument("--max-shift", type=int, default=80, help="在初始猜测（底边、中心对齐）附近搜索的最大平移（像素）")
    ap.add_argument("--scale", type=float, help="手动指定缩放（跳过搜索；需同时给 --dx --dy）")
    ap.add_argument("--dx", type=float, default=0.0)
    ap.add_argument("--dy", type=float, default=0.0)
    args = ap.parse_args()

    if args.out_names and len(args.out_names) != len(args.stages):
        print("[ERROR] --out-names 的数量要和阶段图一样多")
        return 1
    ref = Image.open(args.ref).convert("RGBA")
    lo, hi = (float(t) for t in args.scale_range.split(","))
    scales = np.round(np.arange(lo, hi + 1e-9, 0.025), 3)
    aligned = []
    for i, path in enumerate(args.stages):
        stage = Image.open(path).convert("RGBA")
        if args.scale is not None:
            rm = alpha_mask(ref)
            ys, xs = np.nonzero(rm)
            pivot = ((xs.min() + xs.max()) / 2, float(ys.max()))
            s, dx, dy, iou = args.scale, args.dx, args.dy, float("nan")
        else:
            (iou, s, dx, dy), pivot, _ = search(ref, stage, args.band, scales, args.max_shift)
        out_img = place(stage, ref.size, s, dx, dy, pivot)
        name = args.out_names[i] if args.out_names else f"{path.stem}_aligned.png"
        out = path.with_name(name)
        out_img.save(out)
        aligned.append(out_img)
        edge_note = "  [WARN] 落在搜索范围边上，可以放大 --scale-range / --max-shift 再试" if (
            s in (scales[0], scales[-1]) and args.scale is None) else ""
        print(f"{path.name}: 缩放 {s:.3f}，平移 ({dx:+.0f}, {dy:+.0f}) 像素，底座重合度 IoU {iou:.3f} -> {out}{edge_note}")
    preview = REPO / "art" / "review" / f"{args.ref.stem}_onion.png"
    onion(ref, aligned, preview)
    print(f"重叠对比: {preview}（红线 = 完整图轮廓；检查各阶段的石块底座是否落在红线底部）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
