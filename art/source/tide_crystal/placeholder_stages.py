#!/usr/bin/env python3
"""
一次性脚本（不是工具链的一部分）：从 tide_crystal_v1_chatgpt.png 切出潮蚀晶簇的两个破损阶段**占位图**。

  tide_crystal_cluster_med.png   中间那根最高的晶体断成参差的残桩
  tide_crystal_cluster_low.png   所有晶体都只剩短桩，只剩石块底座

做法：按黑色墨线把图分成一块块区域，把指定晶体的上半部分（参差不齐的断口）连同它的墨线一起抠掉，
再在断口描一圈墨线、断面提亮一点。因为是在原图上直接删，三个阶段的底座位置完全一致。
区域编号是 scipy 对这张图的标号结果，换图要重新挑；所以它只对这张图有效。

需要 scipy（不在 tools/requirements.txt 里，只有重新生成占位图时才需要）：
  pip install scipy
  python art/source/tide_crystal/placeholder_stages.py
正式美术到位后，用新的阶段图替换这两张 PNG 即可，脚本可以删掉。
"""

import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

HERE = Path(__file__).resolve().parent
SRC = HERE / "tide_crystal_v1_chatgpt.png"
INK = (20, 17, 15)
FACE = np.array([180, 245, 235], dtype=np.float32)

im = Image.open(SRC).convert("RGBA")
a = np.asarray(im).astype(np.float32)
al = a[..., 3]
luma = a[..., :3] @ np.array([0.299, 0.587, 0.114])
ink = (al > 128) & (luma < 45)
fill = (al > 128) & ~ink
lab, n = ndi.label(fill)
sizes = ndi.sum(np.ones_like(lab), lab, index=np.arange(1, n + 1))
BIG = set((np.nonzero(sizes > 1500)[0] + 1).tolist())
H, W = al.shape

# 这张图里的晶体区域（scipy 标号）
C_BIG = [1]                              # 中间最高的晶体
C_LEFT = [213]                           # 左边第二高
C_FARLEFT = [429, 304, 564, 582, 500]    # 最左边一根
C_RIGHT = [303, 252, 427, 520]           # 右边两根
C_FRONT = [465]                          # 前面中间
C_FRONTR = [629]                         # 前面右边
C_VINE_R = [298]                         # 右边往上爬的水草


def dil(m, r):
    return np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * r + 1))) > 0


def above_jagged(x0, x1, ytop, amp, rng, tilt):
    pts, x = [], x0 - 60
    while x < x1 + 60:
        pts.append((x, ytop + tilt * (x - (x0 + x1) / 2) + rng.uniform(-amp, amp)))
        x += rng.uniform(12, 30)
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon([(x0 - 60, -10), (x1 + 60, -10)] + list(reversed(pts)), fill=255)
    return np.asarray(m) > 0


def keep_main_piece(out):
    lab2, n2 = ndi.label(out[..., 3] > 0)
    if n2 > 1:
        s2 = ndi.sum(np.ones_like(lab2), lab2, index=np.arange(1, n2 + 1))
        out[(lab2 != np.argmax(s2) + 1) & (lab2 > 0)] = 0


def stage(breaks, seed, open_r=0, ink_w=6, face_w=8, grow=24):
    """breaks: [(区域编号, 保留的高度比例, 断口倾斜)]"""
    rng = random.Random(seed)
    removed = np.zeros_like(fill)
    for comps, keep, tilt in breaks:
        m = np.isin(lab, comps)
        ys, xs = np.nonzero(m)
        ycut = ys.max() - (ys.max() - ys.min()) * keep
        others = np.isin(lab, list(BIG - set(comps)))
        removed |= dil(m, grow) & ~others & above_jagged(xs.min(), xs.max(), ycut, 14, rng, tilt) & (al > 0)
    out = a.copy()
    out[removed] = 0
    if open_r:  # 去掉断口留下的细碎尖刺
        m = out[..., 3] > 0
        opened = dil(~dil(~m, open_r), open_r) & m
        out[~opened] = 0
    keep_main_piece(out)
    kept = out[..., 3] > 0
    gone = (al > 0) & ~kept                     # 相对原图被删掉的部分
    gone_d = dil(gone, ink_w)
    edge = kept & gone_d & fill                 # 断口：描墨线
    face = kept & dil(gone, ink_w + face_w) & ~gone_d & fill  # 断面：提亮
    out[edge, :3] = INK
    out[edge, 3] = 255
    out[face, :3] = out[face, :3] * 0.45 + FACE * 0.55
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")


if __name__ == "__main__":
    med = stage([(C_BIG, 0.40, 0.3)], seed=3)
    low = stage([(C_BIG, 0.10, 0.15), (C_LEFT, 0.35, -0.25), (C_FARLEFT, 0.55, 0.15), (C_RIGHT, 0.45, 0.2),
                 (C_FRONT, 0.6, -0.15), (C_FRONTR, 0.65, 0.25), (C_VINE_R, 0.2, 0.0)], seed=5, open_r=7)
    med.save(HERE / "tide_crystal_cluster_med.png")
    low.save(HERE / "tide_crystal_cluster_low.png")
    print("written:", HERE / "tide_crystal_cluster_med.png", HERE / "tide_crystal_cluster_low.png")
