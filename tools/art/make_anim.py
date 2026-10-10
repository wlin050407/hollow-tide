#!/usr/bin/env python3
"""
生成 DST 动画包（anim/<name>.zip），不依赖 Spriter 和 Don't Starve Mod Tools。

每张图 = 一个 symbol 的一帧。item / stages 生成单帧动画；spin 用矩阵变换让同一张图转起来（多帧）。

子命令
  item      PNG -> mod/anim/<name>.zip（bank = build = symbol = <name>，动画 "idle"），并输出审查预览图
  stages    几张对齐的图 -> 同一个包里的几个动画，例如可开采物的 full / med / low 破损阶段
  spin      地面椭圆图案 -> 平躺在地上旋转的动画（pre / loop / pst），做法同原版预警圈
  preview   把任意动画包（自己的或原版的）的某个动画第 0 帧画出来，可以多个并排对比大小
  selftest  读入原版动画包再写出，确认与原文件逐字节相同（证明 kanim.py 的格式理解是对的）

用法示例
  python tools/art/make_anim.py item art/ground/tide_crystal.png --name tide_crystal --height 150 --pivot 0.5,0.75 \\
      --compare "<DST>/data/anim/gems.zip:bluegem_idle" --compare "<DST>/data/anim/flint.zip:idle"
  python tools/art/make_anim.py stages full=art/source/a.png med=art/source/a_med.png low=art/source/a_low.png \\
      --name tide_crystal_cluster --height 300 --pivot 0.5,0.85
  python tools/art/make_anim.py preview mod/anim/tide_crystal.zip:idle "<DST>/data/anim/gems.zip:bluegem_idle" --out x.png
  python tools/art/make_anim.py selftest "<DST>/data/anim/gems.zip" "<DST>/data/anim/flint.zip"

约定（格式细节见 kanim.py 顶部注释）
  * --height：图在游戏里的高度，单位是 build 像素（= atlas 像素）。原版参考：蓝宝石 152x126，燧石堆 223x119。
  * --pivot：实体坐标原点落在图上的位置，按比例（0,0 = 左上角，0.5,1 = 底边中点）。
    掉落物通常在 0.5,0.5（宝石）~ 0.5,0.71（燧石堆）之间；建筑一般用底边附近。
  * 输出的 zip 内容是确定的（同样输入 -> 同样字节），可以放心提交到 git。

依赖：Pillow、numpy、quicktex（编码）、texture2ddecoder（回读与预览）
"""

from __future__ import annotations

import argparse
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kanim  # noqa: E402

try:
    import numpy as np
    from PIL import Image, ImageDraw
    from quicktex.s3tc.bc3 import BC3Encoder
    import png2tex  # noqa: E402
except ImportError as e:  # pragma: no cover
    print(f"缺少依赖：{e}。请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)

REPO = Path(__file__).resolve().parents[2]
EDGE_PAD = 2  # 图四周留的透明像素，避免贴图过滤/mipmap 时边缘被截断


# ---------------------------------------------------------------------------
# 贴图解码（回读 / 预览用）
# ---------------------------------------------------------------------------

def decode_ktex(data: bytes) -> np.ndarray:
    """KTEX(DXT5) -> 正向（第 0 行是图片顶部）、非预乘的 RGBA uint8 数组。"""
    import texture2ddecoder
    word = struct.unpack("<I", data[4:8])[0]
    if (word >> 4) & 0x1F != png2tex.COMPRESSION_DXT5:
        raise ValueError("预览只支持 DXT5 贴图")
    mips = (word >> 13) & 0x1F
    w, h, _pitch, size = struct.unpack("<HHHI", data[8:18])
    off = 8 + 10 * mips
    bgra = texture2ddecoder.decode_bc3(data[off:off + size], w, h)
    rgba = np.frombuffer(bgra, dtype=np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]]
    rgba = np.flipud(rgba).astype(np.float32)
    a = rgba[..., 3:4]
    rgba[..., :3] = np.where(a > 0, rgba[..., :3] * 255.0 / np.maximum(a, 1), 0)
    return rgba.clip(0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# 渲染：把动画某一帧画成图片（支持任意 2D 变换：缩放、翻转、旋转、压扁）
# ---------------------------------------------------------------------------

def load_zip(path: Path) -> tuple[kanim.Build | None, kanim.AnimFile | None, dict[str, np.ndarray]]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        build = kanim.read_build(z.read("build.bin")) if "build.bin" in names else None
        anim = kanim.read_anim(z.read("anim.bin")) if "anim.bin" in names else None
        atlases = {}
        if build is not None:
            for a in build.atlases:
                atlases[a] = decode_ktex(z.read(a))
    return build, anim, atlases


def build_frame_for(sym: kanim.BuildSymbol, frame: int) -> kanim.BuildFrame:
    """动画元素的 build_frame 指向"起始帧号 <= frame 的最后一帧"。"""
    best = sym.frames[0]
    for f in sym.frames:
        if f.framenum <= frame:
            best = f
    return best


def _affine_piece(img: Image.Image, quad: tuple[float, float, float, float],
                  matrix: tuple[float, ...]) -> tuple[float, float, Image.Image]:
    """一般的 2D 变换：x' = a*x + c*y + tx，y' = b*x + d*y + ty（kanim.py 里的约定，已用原版验证）。"""
    a, b, c, d, tx, ty = matrix
    x0, y0, x1, y1 = quad
    M = np.array([[a, c], [b, d]], dtype=np.float64)
    corners = np.array([[x0, y0], [x1, y0], [x0, y1], [x1, y1]]) @ M.T + np.array([tx, ty])
    ox, oy = np.floor(corners.min(axis=0))
    w = int(np.ceil(corners[:, 0].max() - ox)) + 1
    h = int(np.ceil(corners[:, 1].max() - oy)) + 1
    if abs(np.linalg.det(M)) < 1e-9:
        return ox, oy, Image.new("RGBA", (1, 1))
    S = np.diag([img.width / max(x1 - x0, 1e-9), img.height / max(y1 - y0, 1e-9)])
    N = S @ np.linalg.inv(M)  # 输出像素 -> 贴图像素
    off = N @ (np.array([ox, oy]) - np.array([tx, ty])) - S @ np.array([x0, y0])
    out = img.transform((w, h), Image.AFFINE, (N[0, 0], N[0, 1], off[0], N[1, 0], N[1, 1], off[1]),
                        resample=Image.BILINEAR)
    return float(ox), float(oy), out


def render_frame(build: kanim.Build, atlases: dict[str, np.ndarray], frame: kanim.AnimFrame,
                 warn=print) -> tuple[Image.Image, tuple[float, float]]:
    """返回 (RGBA 图片, 原点在图片里的像素坐标)。"""
    syms = {s.hash: s for s in build.symbols}
    atlas_list = [atlases[a] for a in build.atlases]
    pieces = []  # (x0, y0, image)，按从后往前的顺序
    # 原版里排在前面的元素 z 更小、显示在最上层（flint 的 sparkle、moondial 的 lunar_mote 都排第一），
    # 所以倒序绘制
    for el in reversed(frame.elements):
        sym = syms.get(el.symbol)
        if sym is None:
            warn(f"  预览：元素 {build.names.get(el.symbol, hex(el.symbol))} 不在 build {build.name} 里，跳过")
            continue
        a, b, c, d, tx, ty = el.matrix
        rotated = abs(b) > 1e-9 or abs(c) > 1e-9
        bf = build_frame_for(sym, el.build_frame)
        for q in range(0, len(bf.verts), 6):
            quad = bf.verts[q:q + 6]
            xs = [v[0] for v in quad]; ys = [v[1] for v in quad]
            us = [v[3] for v in quad]; vs = [v[4] for v in quad]
            tex = atlas_list[int(quad[0][5])]
            th, tw = tex.shape[:2]
            c0, c1 = round(min(us) * tw), round(max(us) * tw)
            r0, r1 = round((1 - max(vs)) * th), round((1 - min(vs)) * th)  # v 越大越靠上
            if c1 <= c0 or r1 <= r0:
                continue
            img = Image.fromarray(np.ascontiguousarray(tex[r0:r1, c0:c1]), "RGBA")
            if rotated:
                pieces.append(_affine_piece(img, (min(xs), min(ys), max(xs), max(ys)), el.matrix))
                continue
            w = max(1, round((max(xs) - min(xs)) * abs(a)))
            h = max(1, round((max(ys) - min(ys)) * abs(d)))
            img = img.resize((w, h), Image.LANCZOS)
            if a < 0:
                img = img.transpose(Image.FLIP_LEFT_RIGHT)
            if d < 0:
                img = img.transpose(Image.FLIP_TOP_BOTTOM)
            px = sorted((min(xs) * a + tx, max(xs) * a + tx))[0]
            py = sorted((min(ys) * d + ty, max(ys) * d + ty))[0]
            pieces.append((px, py, img))
    if not pieces:
        return Image.new("RGBA", (1, 1)), (0.0, 0.0)
    x0 = min(min(p[0] for p in pieces), 0.0)
    y0 = min(min(p[1] for p in pieces), 0.0)
    x1 = max(max(p[0] + p[2].width for p in pieces), 0.0)
    y1 = max(max(p[1] + p[2].height for p in pieces), 0.0)
    canvas = Image.new("RGBA", (int(round(x1 - x0)) + 1, int(round(y1 - y0)) + 1))
    for px, py, img in pieces:
        layer = Image.new("RGBA", canvas.size)
        layer.paste(img, (int(round(px - x0)), int(round(py - y0))))
        canvas = Image.alpha_composite(canvas, layer)
    return canvas, (-x0, -y0)


def split_ref(ref: str) -> tuple[Path, str]:
    """"path/x.zip:anim" -> (path, anim)；兼容 Windows 盘符（D:\\...\\x.zip:anim）。"""
    head, sep, tail = ref.rpartition(":")
    if sep and head.lower().endswith(".zip") and "/" not in tail and "\\" not in tail:
        return Path(head), tail
    return Path(ref), ""


def render_ref(ref: str) -> tuple[str, Image.Image, tuple[float, float]]:
    """ref = "path/to/x.zip:animname"（省略动画名时取第一个动画）"""
    zpath, animname = split_ref(ref)
    build, anim, atlases = load_zip(zpath)
    if build is None or anim is None:
        raise ValueError(f"{zpath.name} 需要同时包含 build.bin 和 anim.bin 才能预览")
    a = next((x for x in anim.anims if x.name == animname), None) if animname else anim.anims[0]
    if a is None:
        raise ValueError(f"{zpath.name} 里没有动画 {animname!r}（有：{[x.name for x in anim.anims][:20]}）")
    img, origin = render_frame(build, atlases, a.frames[0])
    return f"{zpath.stem}:{a.name}", img, origin


def contact_sheet(items: list[tuple[str, Image.Image, tuple[float, float]]], scale: int = 2) -> Image.Image:
    """把几张渲染结果按"原点对齐在同一条地平线上"并排，放大 scale 倍，画出原点和地平线。"""
    gap = 24
    above = max(o[1] for _, _, o in items)
    below = max(img.height - o[1] for _, img, o in items)
    width = sum(img.width for _, img, _ in items) + gap * (len(items) + 1)
    height = int(above + below) + 40
    sheet = Image.new("RGBA", (width, height), (124, 110, 84, 255))  # 接近原版地面的土色
    draw = ImageDraw.Draw(sheet)
    ground = 20 + above
    draw.line([(0, ground), (width, ground)], fill=(60, 50, 40, 255))
    x = gap
    for label, img, (ox, oy) in items:
        top = int(round(ground - oy))
        sheet.alpha_composite(img, (x, top))
        cx = x + ox
        draw.line([(cx - 4, ground), (cx + 4, ground)], fill=(255, 60, 60, 255))
        draw.line([(cx, ground - 4), (cx, ground + 4)], fill=(255, 60, 60, 255))
        draw.text((x, height - 16), f"{label} {img.width}x{img.height}", fill=(255, 255, 255, 255))
        x += img.width + gap
    return sheet.resize((sheet.width * scale, sheet.height * scale), Image.NEAREST)


# ---------------------------------------------------------------------------
# 生成：一张或几张图 -> 一个 symbol 的几帧 -> 每帧一个单帧动画
#   item   ：一张图，动画 "idle"
#   stages ：几张**同样大小、已对齐**的图（例如完整 / 破损 / 只剩底座），每张一个动画（"full" / "med" / "low"）
#            和原版巨石 rock.zip 的结构一样：同一个 symbol 的第 0/1/2 帧，三个动画各引用一帧
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    anim: str
    sprite: Image.Image            # 已缩放、四周带 EDGE_PAD 透明边
    origin: tuple[float, float]    # 实体原点在 sprite 上的像素位置


def alpha_bbox(img: Image.Image, alpha_floor: int) -> tuple[int, int, int, int]:
    a = np.asarray(img)[..., 3]
    ys, xs = np.nonzero(a > alpha_floor)
    if len(xs) == 0:
        raise ValueError("图片是全透明的")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def prepare_stages(images: list[tuple[str, Image.Image]], height: int, pivot: tuple[float, float],
                   alpha_floor: int) -> list[Stage]:
    """第一张图决定缩放比例（它的不透明部分缩放到 height 高）和原点；其余各张用同样的比例和原点，
    所以只要原图是对齐的，各阶段在游戏里的位置就严丝合缝。每张图各自裁掉透明边，省贴图空间。"""
    imgs = [(n, im.convert("RGBA")) for n, im in images]
    size0 = imgs[0][1].size
    for n, im in imgs[1:]:
        if im.size != size0:
            raise ValueError(f"阶段图 {n!r} 的尺寸 {im.size} 与第一张 {size0} 不同：各阶段必须是同样大小、对齐好的画布")
    rx0, ry0, rx1, ry1 = alpha_bbox(imgs[0][1], alpha_floor)
    ref_w, ref_h = rx1 - rx0, ry1 - ry0
    scale = height / ref_h
    w0 = max(1, round(ref_w * scale))
    ox_ref, oy_ref = pivot[0] * w0, pivot[1] * height   # 原点在第一张（缩放后、不含透明边）图上的位置
    stages = []
    for i, (name, im) in enumerate(imgs):
        x0, y0, x1, y1 = (rx0, ry0, rx1, ry1) if i == 0 else alpha_bbox(im, alpha_floor)
        crop = im.crop((x0, y0, x1, y1))
        w = w0 if i == 0 else max(1, round((x1 - x0) * scale))
        h = height if i == 0 else max(1, round((y1 - y0) * scale))
        crop = crop.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA")
        sprite = Image.new("RGBA", (w + 2 * EDGE_PAD, h + 2 * EDGE_PAD))
        sprite.paste(crop, (EDGE_PAD, EDGE_PAD))
        dx, dy = (x0 - rx0) * scale, (y0 - ry0) * scale   # 这张图相对第一张的偏移（缩放后）
        stages.append(Stage(name, sprite, (EDGE_PAD + ox_ref - dx, EDGE_PAD + oy_ref - dy)))
    return stages


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def pack(sizes: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int, int]:
    """简单的货架排布：按高度从高到低一行行摆；在几种 2 的幂宽度里选总面积最小的。"""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][1])
    best = None
    width = next_pow2(max(w for w, _ in sizes))
    while width <= 4096:
        pos = [(0, 0)] * len(sizes)
        x = y = row_h = 0
        for i in order:
            w, h = sizes[i]
            if x + w > width:
                x, y, row_h = 0, y + row_h, 0
            pos[i] = (x, y)
            x += w
            row_h = max(row_h, h)
        aw, ah = width, next_pow2(y + row_h)
        if best is None or aw * ah < best[1] * best[2]:
            best = (pos, aw, ah)
        width *= 2
    return best


def make_package(stages: list[Stage], name: str, level: int) -> tuple[dict[str, bytes], dict]:
    positions, aw, ah = pack([st.sprite.size for st in stages])
    atlas = Image.new("RGBA", (aw, ah))
    for st, (c, r) in zip(stages, positions):
        atlas.paste(st.sprite, (c, r))  # 正向图片坐标（第 0 行是顶部）
    tex = png2tex.ktex_bytes(png2tex.mip_chain(atlas), BC3Encoder(level))

    sym = kanim.strhash(name)
    frames, anims = [], []
    for i, (st, (c, r)) in enumerate(zip(stages, positions)):
        w, h = st.sprite.size
        px, py = st.origin
        x0, x1 = -px, w - px          # build 坐标：x 向右
        y0, y1 = -py, h - py          # build 坐标：y 向下为正（y0 是上沿）
        u0, u1 = c / aw, (c + w) / aw
        v_top, v_bot = 1.0 - r / ah, 1.0 - (r + h) / ah  # 上沿 v 大（贴图上下翻转存储）
        # 顶点顺序与原版一致：左上、右上、左下、右上、右下、左下
        verts = [(x0, y0, 0.0, u0, v_top, 0.0), (x1, y0, 0.0, u1, v_top, 0.0), (x0, y1, 0.0, u0, v_bot, 0.0),
                 (x1, y0, 0.0, u1, v_top, 0.0), (x1, y1, 0.0, u1, v_bot, 0.0), (x0, y1, 0.0, u0, v_bot, 0.0)]
        bbox = ((x0 + x1) / 2, (y0 + y1) / 2, float(w), float(h))
        frames.append(kanim.BuildFrame(i, 1, bbox, verts))
        element = kanim.AnimElement(symbol=sym, build_frame=i, layer=sym,
                                    matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), z=-5.0)  # 单元素时原版 z=-5
        anims.append(kanim.Animation(st.anim, kanim.FACING_ALL, sym, 30.0, [kanim.AnimFrame(bbox, [], [element])]))

    build = kanim.Build(name=name, atlases=["atlas-0.tex"], symbols=[kanim.BuildSymbol(sym, frames)], names={sym: name})
    anim = kanim.AnimFile(anims=anims, names={sym: name})
    members = {"build.bin": kanim.write_build(build), "anim.bin": kanim.write_anim(anim), "atlas-0.tex": tex}
    return members, {"atlas": (aw, ah)}


def parse_pivot(text: str) -> tuple[float, float] | None:
    try:
        x, y = (float(t) for t in text.split(","))
        return x, y
    except ValueError:
        print("[ERROR] --pivot 格式是 x,y，例如 0.5,0.75")
        return None


def build_and_report(stages: list[Stage], args) -> int:
    members, meta = make_package(stages, args.name, args.level)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.zip"
    kanim.write_zip(out, members)
    print(f"动画包: {out}")
    print(f"  bank = build = symbol = {args.name!r}，atlas {meta['atlas'][0]}x{meta['atlas'][1]}")
    for st in stages:
        print(f"  动画 {st.anim!r}：图 {st.sprite.width}x{st.sprite.height}（含 {EDGE_PAD}px 透明边），"
              f"原点在图上 ({st.origin[0]:.1f}, {st.origin[1]:.1f})")

    # 回读：重新解析 zip，逐个渲染动画，与输入的图比较
    build, anim, atlases = load_zip(out)
    assert kanim.write_build(build) == members["build.bin"] and kanim.write_anim(anim) == members["anim.bin"]
    by_name = {a.name: a for a in anim.anims}
    worst_rgb = worst_a = 0.0
    for st in stages:
        img, (ox, oy) = render_frame(build, atlases, by_name[st.anim].frames[0])
        left, top = round(ox - st.origin[0]), round(oy - st.origin[1])
        ref = np.asarray(st.sprite, dtype=np.float32)
        got = np.asarray(img.crop((left, top, left + st.sprite.width, top + st.sprite.height)), dtype=np.float32)
        mask = ref[..., 3] > 25
        worst_rgb = max(worst_rgb, float(np.abs(got[..., :3] - ref[..., :3])[mask].mean()) if mask.any() else 0.0)
        worst_a = max(worst_a, float(np.abs(got[..., 3] - ref[..., 3]).mean()))
    print(f"[OK] 回读：zip 结构可解析；渲染结果与原图平均误差（最差的一个动画）RGB {worst_rgb:.1f} / Alpha {worst_a:.1f}"
          f"（DXT5 有损，10 左右正常）")
    if worst_rgb > 16 or worst_a > 8:
        print("[WARN] 误差偏大，看一下预览图")

    items = [render_ref(f"{out}:{st.anim}") for st in stages]
    for ref_ in args.compare or []:
        try:
            items.append(render_ref(ref_))
        except (OSError, ValueError, KeyError, kanim.FormatError) as e:
            print(f"[WARN] 对比图 {ref_} 渲染失败：{e}")
    preview = args.preview or (REPO / "art" / "review" / f"{args.name}_ground_preview.png")
    preview.parent.mkdir(parents=True, exist_ok=True)
    contact_sheet(items).save(preview)
    print(f"预览: {preview}（红色十字 = 实体原点，横线 = 地面；放大 2 倍）")
    return 0


def cmd_item(args) -> int:
    pivot = parse_pivot(args.pivot)
    if pivot is None:
        return 1
    stages = prepare_stages([("idle", Image.open(args.input))], args.height, pivot, args.alpha_floor)
    return build_and_report(stages, args)


def cmd_stages(args) -> int:
    pivot = parse_pivot(args.pivot)
    if pivot is None:
        return 1
    images = []
    for spec in args.stages:
        anim, sep, path = spec.partition("=")
        if not sep or not anim or not path:
            print(f"[ERROR] {spec!r} 格式应为 动画名=图片路径，例如 full=art/source/x.png")
            return 1
        images.append((anim, Image.open(path)))
    if len({a for a, _ in images}) != len(images):
        print("[ERROR] 动画名重复")
        return 1
    try:
        stages = prepare_stages(images, args.height, pivot, args.alpha_floor)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1
    return build_and_report(stages, args)


# ---------------------------------------------------------------------------
# spin：地面上旋转的图案（漩涡、法阵……），做法同原版预警圈 warning_shadow.zip
#   贴图是正圆；动画每一帧的矩阵 = 压扁(y × K) × 旋转(θ) × 缩放(s)，看起来就像平躺在地上转
#   K = 0.518 取自原版 warning_shadow（第 0 帧矩阵的 d 值），也就是游戏镜头下地面的透视压缩比例
#   AI 画的是已经压扁的椭圆，所以先拉回正圆（宽高拉成一样）
# ---------------------------------------------------------------------------

GROUND_SQUASH = 0.518


def spin_matrix(theta: float, scale: float, squash: float) -> tuple[float, float, float, float, float, float]:
    import math
    cs, sn = math.cos(theta), math.sin(theta)
    # M = [[a, c], [b, d]] = Sy(K) · R(θ) · s
    return (scale * cs, squash * scale * sn, -scale * sn, squash * scale * cs, 0.0, 0.0)


def drop_islands(img: Image.Image, alpha_floor: int) -> Image.Image:
    """只保留和图中心连在一起的部分，去掉飘在外面的水珠之类（它们会跟着整张图一起转，看着很假）。"""
    from PIL import ImageDraw, ImageFilter
    a = img.getchannel("A")
    mask = a.point(lambda v: 255 if v > alpha_floor else 0)
    cx, cy = img.width // 2, img.height // 2
    if mask.getpixel((cx, cy)) == 0:
        return img  # 中心是空的（例如圆环），不处理
    ImageDraw.floodfill(mask, (cx, cy), 128)
    keep = mask.point(lambda v: 255 if v == 128 else 0).filter(ImageFilter.MaxFilter(5))  # 外扩一点，保留抗锯齿边
    out = img.copy()
    out.putalpha(Image.fromarray(np.minimum(np.asarray(a), np.asarray(keep))))
    return out


def make_spin_package(src: Image.Image, name: str, width: int, period: int, pre: int, pst: int,
                      clockwise: bool, alpha_floor: int, squash: float, level: int,
                      keep_islands: bool = False) -> tuple[dict[str, bytes], dict]:
    import math
    img = src.convert("RGBA")
    if not keep_islands:
        img = drop_islands(img, alpha_floor)
    x0, y0, x1, y1 = alpha_bbox(img, alpha_floor)
    img = img.crop((x0, y0, x1, y1))
    # 拉成正圆（不按原图比例）：贴图不圆的话，转起来轮廓会一胀一缩
    circle_h = width
    img = img.convert("RGBa").resize((width, circle_h), Image.LANCZOS).convert("RGBA")
    sprite = Image.new("RGBA", (width + 2 * EDGE_PAD, circle_h + 2 * EDGE_PAD))
    sprite.paste(img, (EDGE_PAD, EDGE_PAD))
    w, h = sprite.size
    aw, ah = next_pow2(w), next_pow2(h)
    atlas = Image.new("RGBA", (aw, ah))
    atlas.paste(sprite, (0, 0))
    tex = png2tex.ktex_bytes(png2tex.mip_chain(atlas), BC3Encoder(level))

    sym = kanim.strhash(name)
    bx0, bx1, by0, by1 = -w / 2, w / 2, -h / 2, h / 2   # 圆心在原点
    u1, v_bot = w / aw, 1.0 - h / ah
    verts = [(bx0, by0, 0.0, 0.0, 1.0, 0.0), (bx1, by0, 0.0, u1, 1.0, 0.0), (bx0, by1, 0.0, 0.0, v_bot, 0.0),
             (bx1, by0, 0.0, u1, 1.0, 0.0), (bx1, by1, 0.0, u1, v_bot, 0.0), (bx0, by1, 0.0, 0.0, v_bot, 0.0)]
    build = kanim.Build(name=name, atlases=["atlas-0.tex"],
                        symbols=[kanim.BuildSymbol(sym, [kanim.BuildFrame(0, 1, (0.0, 0.0, float(w), float(h)), verts)])],
                        names={sym: name})

    step = (1 if clockwise else -1) * 2 * math.pi / period

    def frame(i: int, scale: float) -> kanim.AnimFrame:
        m = spin_matrix(i * step, scale, squash)
        bbox = (0.0, 0.0, w * scale, h * scale * squash)
        return kanim.AnimFrame(bbox, [], [kanim.AnimElement(sym, 0, sym, m, -5.0)])

    def ease(t: float) -> float:
        return 1 - (1 - t) ** 2

    anims = [
        kanim.Animation("pre", kanim.FACING_ALL, sym, 30.0,
                        [frame(i, max(0.02, ease((i + 1) / pre))) for i in range(pre)]),
        kanim.Animation("loop", kanim.FACING_ALL, sym, 30.0, [frame(i, 1.0) for i in range(period)]),
        kanim.Animation("pst", kanim.FACING_ALL, sym, 30.0,
                        [frame(i, max(0.02, 1 - ease((i + 1) / pst))) for i in range(pst)]),
    ]
    anim = kanim.AnimFile(anims=anims, names={sym: name})
    members = {"build.bin": kanim.write_build(build), "anim.bin": kanim.write_anim(anim), "atlas-0.tex": tex}
    return members, {"texture": (w, h), "atlas": (aw, ah)}


def cmd_spin(args) -> int:
    members, meta = make_spin_package(Image.open(args.input), args.name, args.width, args.period, args.pre,
                                      args.pst, args.clockwise, args.alpha_floor, args.squash, args.level,
                                      keep_islands=args.keep_islands)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.zip"
    kanim.write_zip(out, members)
    print(f"动画包: {out}")
    print(f"  bank = build = symbol = {args.name!r}；动画 pre（{args.pre} 帧，长出来）/ loop（{args.period} 帧 = "
          f"{args.period / 30:.1f} 秒转一圈）/ pst（{args.pst} 帧，缩回去）")
    print(f"  正圆贴图 {meta['texture'][0]}x{meta['texture'][1]}，atlas {meta['atlas'][0]}x{meta['atlas'][1]}；"
          f"地面上看是 {args.width} x {round(args.width * args.squash)} 的椭圆，圆心在实体原点")

    build, anim, atlases = load_zip(out)
    assert kanim.write_build(build) == members["build.bin"] and kanim.write_anim(anim) == members["anim.bin"]
    loop = next(a for a in anim.anims if a.name == "loop")
    frames = [render_frame(build, atlases, loop.frames[i])[0] for i in range(0, len(loop.frames), 2)]
    size = (max(f.width for f in frames), max(f.height for f in frames))
    gif = []
    for f in frames:
        bg = Image.new("RGBA", size, (124, 110, 84, 255))
        bg.alpha_composite(f, ((size[0] - f.width) // 2, (size[1] - f.height) // 2))
        gif.append(bg.convert("RGB"))
    preview = args.preview or (REPO / "art" / "review" / f"{args.name}_spin.gif")
    preview.parent.mkdir(parents=True, exist_ok=True)
    gif[0].save(preview, save_all=True, append_images=gif[1:], duration=66, loop=0)
    print(f"预览: {preview}（loop 动画，每 2 帧取 1 帧）")
    return 0


def cmd_preview(args) -> int:
    items = [render_ref(r) for r in args.refs]
    contact_sheet(items, args.scale).save(args.out)
    print(f"预览: {args.out}")
    return 0


def cmd_selftest(args) -> int:
    failed = 0
    for p in args.zips:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            for member, read, write in (("build.bin", kanim.read_build, kanim.write_build),
                                        ("anim.bin", kanim.read_anim, kanim.write_anim)):
                if member not in names:
                    continue
                data = z.read(member)
                try:
                    same = write(read(data)) == data
                except kanim.FormatError as e:
                    print(f"[FAIL] {Path(p).name}/{member}: {e}")
                    failed += 1
                    continue
                print(f"[{'OK' if same else 'FAIL'}] {Path(p).name}/{member}: {len(data)} 字节，"
                      f"{'读入再写出逐字节相同' if same else '写出结果与原文件不同'}")
                failed += 0 if same else 1
    print("全部通过" if not failed else f"{failed} 项失败")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DST 动画包生成 / 预览 / 格式自检")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("item", help="一张 PNG -> 单帧动画包（地面外观）")
    p.add_argument("input", type=Path)
    p.add_argument("--name", required=True, help="bank / build / symbol 名（通常等于 prefab 名）")
    p.add_argument("--height", type=int, default=150, help="游戏内高度（build 像素），默认 150")
    p.add_argument("--pivot", default="0.5,0.75", help="原点在图上的比例位置 x,y，默认 0.5,0.75")
    p.add_argument("--alpha-floor", type=int, default=8, help="裁切时忽略 alpha 不超过此值的像素")
    p.add_argument("--level", type=int, default=12, help="DXT 编码质量 0-18")
    p.add_argument("--out-dir", type=Path, default=REPO / "mod" / "anim")
    p.add_argument("--preview", type=Path, help="预览图路径（默认 art/review/<name>_ground_preview.png）")
    p.add_argument("--compare", action="append", help="并排对比的动画，格式 zip路径:动画名，可重复")
    p.set_defaults(func=cmd_item)

    p = sub.add_parser("stages", help="几张对齐的图 -> 同一个 symbol 的几帧，每帧一个动画（如巨石的 full/med/low）")
    p.add_argument("stages", nargs="+", help="动画名=图片路径，第一张决定缩放和原点，例如 full=a.png med=b.png low=c.png")
    p.add_argument("--name", required=True, help="bank / build / symbol 名（通常等于 prefab 名）")
    p.add_argument("--height", type=int, default=300, help="第一张图在游戏内的高度（build 像素）")
    p.add_argument("--pivot", default="0.5,0.85", help="原点在第一张图上的比例位置 x,y")
    p.add_argument("--alpha-floor", type=int, default=8, help="裁切时忽略 alpha 不超过此值的像素")
    p.add_argument("--level", type=int, default=12, help="DXT 编码质量 0-18")
    p.add_argument("--out-dir", type=Path, default=REPO / "mod" / "anim")
    p.add_argument("--preview", type=Path, help="预览图路径（默认 art/review/<name>_ground_preview.png）")
    p.add_argument("--compare", action="append", help="并排对比的动画，格式 zip路径:动画名，可重复")
    p.set_defaults(func=cmd_stages)

    p = sub.add_parser("spin", help="AI 画的地面椭圆图案 -> 平躺在地上旋转的动画（pre / loop / pst）")
    p.add_argument("input", type=Path)
    p.add_argument("--name", required=True, help="bank / build / symbol 名")
    p.add_argument("--width", type=int, default=320, help="地面上椭圆的宽度（build 像素）")
    p.add_argument("--period", type=int, default=90, help="转一圈的帧数（30 帧 = 1 秒）")
    p.add_argument("--pre", type=int, default=12, help="出现时长出来的帧数")
    p.add_argument("--pst", type=int, default=12, help="消失时缩回去的帧数")
    p.add_argument("--clockwise", action="store_true", help="顺时针转（默认逆时针）")
    p.add_argument("--keep-islands", action="store_true", help="保留和主体不相连的碎片（默认去掉）")
    p.add_argument("--squash", type=float, default=GROUND_SQUASH, help="地面透视压缩比例（原版 0.518）")
    p.add_argument("--alpha-floor", type=int, default=32, help="裁切时忽略 alpha 不超过此值的像素")
    p.add_argument("--level", type=int, default=12, help="DXT 编码质量 0-18")
    p.add_argument("--out-dir", type=Path, default=REPO / "mod" / "anim")
    p.add_argument("--preview", type=Path, help="预览 GIF 路径（默认 art/review/<name>_spin.gif）")
    p.set_defaults(func=cmd_spin)

    p = sub.add_parser("preview", help="渲染动画第 0 帧，多个并排")
    p.add_argument("refs", nargs="+", help="zip路径:动画名")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--scale", type=int, default=2)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("selftest", help="原版动画包读入再写出，检查逐字节相同")
    p.add_argument("zips", nargs="+")
    p.set_defaults(func=cmd_selftest)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
