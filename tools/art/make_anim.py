#!/usr/bin/env python3
"""
生成 DST 动画包（anim/<name>.zip），不依赖 Spriter 和 Don't Starve Mod Tools。

每张图 = 一个 symbol 的一帧。item / stages 生成单帧动画；spin 用矩阵变换让同一张图转起来（多帧）。

子命令
  item      PNG -> mod/anim/<name>.zip（bank = build = symbol = <name>，动画 "idle"），并输出审查预览图
  stages    几张对齐的图 -> 同一个包里的几个动画，例如可开采物的 full / med / low 破损阶段
  spin      地面椭圆图案 -> 平躺在地上旋转的动画（pre / loop / pst），做法同原版预警圈；
            加 --flow N 时先生成 N 张逐帧流动的图（中心转得快、往里吸），像原版海上漩涡那样逐帧播放；
            给多张同一图案的变体时，中心照样流动，外圈在相邻两张之间逐帧变形（白沫连续地长大、缩小、变形）
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


MAX_ATLAS = 2048  # 原版动画包里见过的最大贴图是 2048（moondial_build）；不超过它最稳妥（更大是否可用没验证）


def pack(sizes: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int, int]:
    """简单的货架排布：按高度从高到低一行行摆；在几种 2 的幂宽度里选总面积最小、其次最接近正方形的，
    边长不超过 MAX_ATLAS（放不下时报错——需要拆成多张贴图，目前还没实现）。"""
    order = sorted(range(len(sizes)), key=lambda i: -sizes[i][1])
    best = None
    width = next_pow2(max(w for w, _ in sizes))
    while width <= MAX_ATLAS:
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
        if ah <= MAX_ATLAS:
            key = (aw * ah, max(aw, ah))
            if best is None or key < best[0]:
                best = (key, pos, aw, ah)
        width *= 2
    if best is None:
        raise ValueError(f"图太多/太大，一张 {MAX_ATLAS}x{MAX_ATLAS} 的贴图放不下（需要拆成多张 atlas，还没实现）")
    return best[1], best[2], best[3]


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


def _polar(n: int):
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    c = (n - 1) / 2
    dx, dy = xx - c, yy - c
    return c, np.sqrt(dx * dx + dy * dy) / (n / 2), np.arctan2(dy, dx)


def _flow(img: np.ndarray, count: int, swirl: float, drain: float) -> list[np.ndarray]:
    """flow map 交叉淡化（见 flow_frames）。img：预乘 alpha 的 float32 数组（0–255），返回 count 个同格式数组。"""
    n = img.shape[0]
    c, r, ang = _polar(n)
    k = np.clip(1 - r / 0.85, 0, 1) ** 2

    def sample(sx, sy):
        sx = np.clip(sx, 0, n - 1.001)
        sy = np.clip(sy, 0, n - 1.001)
        x0 = np.floor(sx).astype(int)
        y0 = np.floor(sy).astype(int)
        fx = (sx - x0)[..., None]
        fy = (sy - y0)[..., None]
        top = img[y0, x0] * (1 - fx) + img[y0, x0 + 1] * fx
        bot = img[y0 + 1, x0] * (1 - fx) + img[y0 + 1, x0 + 1] * fx
        return top * (1 - fy) + bot * fy

    def warp(phase):
        theta = ang + swirl * k * phase
        rr = (r + drain * k * phase) * (n / 2)
        return sample(c + rr * np.cos(theta), c + rr * np.sin(theta))

    out = []
    for i in range(count):
        p1 = i / count
        p2 = (p1 + 0.5) % 1.0
        w = abs(2 * p1 - 1)  # p1 刚回卷时它的权重是 0，所以看不到跳变
        out.append(warp(p1) * (1 - w) + warp(p2) * w)
    return out


def flow_frames(circle: Image.Image, count: int, swirl: float, drain: float) -> list[Image.Image]:
    """把一张正圆的漩涡图"画"成 count 帧会流动的循环动画（逐帧不同的图，不只是整体转）。

    做法（游戏里做水面常用的 flow map 交叉淡化）：
      * 越靠近中心转得越多（差速旋转），并稍微往中心"吸"一点；外圈 15% 不动，边缘的白沫保持清晰
      * 两份相位差半个周期的变形叠在一起交替淡入淡出，所以能无缝循环、不会跳
    count 帧正好是一个周期；第 count 帧和第 0 帧一样。
    """
    img = np.asarray(circle.convert("RGBa")).astype(np.float32)  # 预乘 alpha，插值不出黑边
    out = []
    for f in _flow(img, count, swirl, drain):
        a = f[..., 3:4]
        rgb = np.where(a > 0.5, f[..., :3] * 255.0 / np.maximum(a, 1e-3), 0)
        out.append(Image.fromarray(np.dstack([rgb, a]).clip(0, 255).round().astype(np.uint8), "RGBA"))
    return out


# ---------------------------------------------------------------------------
# 多张变体：外圈逐帧变形（morph）
#
# 同一个漩涡的几张手绘变体，外圈白沫各不相同。直接轮流换图会一跳一跳（2026-10-11 反馈"很不连贯"），
# 直接交叉淡化会出现两圈半透明的重影。这里把每张图拆成"形状"和"颜色"分别过渡：
#   * 形状：外轮廓、白沫区域各算一张有向距离场（SDF），两张图的距离场线性插值再取 0 等值线
#     —— 轮廓始终是实心的一条线，白沫块会连续地长大、缩小、分开、合并，不会出现两条半透明的边
#   * 颜色：白沫色、水色各自填满整张图后再交叉淡化（同类颜色混合，不会把白沫和深水混成灰色）
#   * 外轮廓墨线：按插值后的轮廓重新描（粗细量自原图），不会断线
# 中心不参与变形，用第一张变体做 flow 流动（同单张图的做法），按轮廓深度和外圈平滑衔接。
# ---------------------------------------------------------------------------

LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
FOAM_LUM = 150 / 255  # 亮度高于它算白沫（这套漩涡图：白沫约 230，水约 60–150，墨线 < 50）
INK_LUM = 50 / 255    # 低于它算墨线
RIM_BLEND = (0.095, 0.145)  # 离轮廓多深（按半径比例）从"外圈变形"过渡到"中心流动"


def _edt(feature: np.ndarray) -> np.ndarray:
    """每个像素到最近 True 像素的欧氏距离（精确值：先逐列求竖直距离 g，再逐行取 min((x-x')² + g²)）。"""
    h, w = feature.shape
    inf = float(h + w)
    g = np.empty((h, w), np.float32)
    g[0] = np.where(feature[0], 0, inf)
    for y in range(1, h):
        g[y] = np.where(feature[y], 0, g[y - 1] + 1)
    for y in range(h - 2, -1, -1):
        g[y] = np.minimum(g[y], g[y + 1] + 1)
    xs = np.arange(w, dtype=np.float32)
    dx2 = (xs[:, None] - xs[None, :]) ** 2
    g2 = g * g
    out = np.empty((h, w), np.float32)
    for y in range(h):
        out[y] = (dx2 + g2[y][None, :]).min(axis=1)
    return np.sqrt(out)


def _sdf(mask: np.ndarray) -> np.ndarray:
    """有向距离：区域内为正、区域外为负，0 是边界。"""
    return np.where(mask, _edt(~mask) - 0.5, -(_edt(mask) - 0.5)).astype(np.float32)


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    pad = [(r + 1, r), (r + 1, r)] + [(0, 0)] * (a.ndim - 2)
    s = np.pad(a, pad).cumsum(0).cumsum(1)
    n = 2 * r + 1
    h, w = a.shape[:2]
    return (s[n:n + h, n:n + w] - s[0:h, n:n + w] - s[n:n + h, 0:w] + s[0:h, 0:w]) / (n * n)


def _fill(col: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """mask 内保留原色，mask 外用附近 mask 内像素的平均色填满（半径逐级加倍的归一化盒式模糊）。"""
    out = np.where(mask[..., None], col, 0).astype(np.float32)
    have = mask.copy()
    m = mask.astype(np.float32)
    r = 1
    while not have.all() and r <= 2 * max(mask.shape):
        den = _box_blur(m, r)
        ok = ~have & (den > 1e-4)
        out[ok] = _box_blur(col * m[..., None], r)[ok] / den[ok][..., None]
        have |= ok
        r *= 2
    return out


def _local_max(a: np.ndarray, r: int) -> np.ndarray:
    """(2r+1) x (2r+1) 方窗内的最大值。"""
    out = a
    for axis in (0, 1):
        n = out.shape[axis]
        p = np.pad(out, [(r, r) if i == axis else (0, 0) for i in range(2)], mode="edge")
        out = np.max([np.take(p, range(j, j + n), axis=axis) for j in range(2 * r + 1)], axis=0)
    return out


def _thickness(sd: np.ndarray, ink_w: float) -> np.ndarray:
    """附近（2·ink_w 范围内）离轮廓最深的距离 ≈ 当地厚度的一半。主体边缘约 2·ink_w，细水柱、小水珠小得多。"""
    return _local_max(np.maximum(sd, 0), int(2 * ink_w) + 1)


def _ink_px(sd: np.ndarray, ink_w: float) -> np.ndarray:
    """每个像素处外轮廓墨线的粗细：一般是 ink_w，但不超过当地厚度的一半
    （否则细的水柱、正在缩小消失的小水珠会整块变黑）。"""
    return np.minimum(ink_w, 0.5 * _thickness(sd, ink_w))


class _RimLayers:
    """一张变体拆成：外轮廓 SDF、白沫 SDF、白沫色、水色、墨线色和墨线粗细（像素）。"""

    def __init__(self, im: Image.Image):
        img = np.asarray(im.convert("RGBa")).astype(np.float32) / 255.0
        a = img[..., 3]
        col = img[..., :3] / np.maximum(a[..., None], 1e-3)
        lum = col @ LUMA
        self.sd = _sdf(a > 0.5)
        inside = self.sd > 0
        dark = inside & (lum < INK_LUM)
        self.ink_w = 1.0  # 外轮廓墨线粗细：从边缘往里，深色像素占比第一次低于一半的深度
        for depth in np.arange(0.5, 20.0, 0.5):
            band = (self.sd >= depth - 0.5) & (self.sd < depth)
            if band.any() and dark[band].mean() < 0.5:
                self.ink_w = float(depth)
                break
        ink_px = _ink_px(self.sd, self.ink_w)  # 细的水柱、小水珠里墨线变细，里面的浅色才算得上白沫
        foam = inside & (lum > FOAM_LUM) & (self.sd > ink_px)
        self.fd = _sdf(foam)
        self.foam_col = _fill(col, foam)
        self.water_col = _fill(col, inside & ~foam & (self.sd > ink_px + 1))
        ink = dark & (self.sd < ink_px)
        self.ink_col = col[ink].mean(axis=0) if ink.any() else np.zeros(3, np.float32)


def _rim_morph(a: _RimLayers, b: _RimLayers, t: float) -> tuple[np.ndarray, np.ndarray]:
    """a -> b 的第 t（0–1）处。返回（预乘 alpha 的 RGBA float 数组 0–1，插值后的轮廓 SDF）。"""
    d = (1 - t) * a.sd + t * b.sd
    fd = (1 - t) * a.fd + t * b.fd
    ink_w = (1 - t) * a.ink_w + t * b.ink_w
    thick = _thickness(d, ink_w)
    ink_px = np.minimum(ink_w, 0.5 * thick)
    alpha = np.clip(d + 0.5, 0, 1)
    # 细的水柱、小水珠在原图里都是浅色：两张图的水柱位置不重合时，白沫的距离场插值到中途会先消失，
    # 这时按白沫上色，免得变成一截深色的水
    thin = np.clip((2 * ink_w - thick) / ink_w, 0, 1)
    wf = (np.maximum(np.clip(fd + 0.5, 0, 1), thin) * np.clip(d - ink_px + 0.5, 0, 1))[..., None]
    base = wf * ((1 - t) * a.foam_col + t * b.foam_col) + (1 - wf) * ((1 - t) * a.water_col + t * b.water_col)
    wi = np.clip(ink_px - d + 0.5, 0, 1)[..., None]
    col = wi * ((1 - t) * a.ink_col + t * b.ink_col) + (1 - wi) * base
    return np.dstack([col * alpha[..., None], alpha]), d


def align_variants(circles: list[Image.Image]) -> tuple[list[Image.Image], list[float]]:
    """把每张变体绕圆心转到外圈轮廓和第一张最重合的角度（2° 一档），变形时要走的距离最短。
    不做镜像：镜像会把螺旋方向和光照方向一起反过来。"""
    small = [c.resize((128, 128), Image.BILINEAR) for c in circles]
    _, r, _ = _polar(128)
    rim = r > 0.55
    ref = np.asarray(small[0])[..., 3][rim] > 128
    out, angles = [circles[0]], [0.0]
    for im, sm in zip(circles[1:], small[1:]):
        best = (2.0, 0.0)
        for deg in np.arange(0.0, 360.0, 2.0):
            m = np.asarray(sm.rotate(float(deg), resample=Image.BILINEAR))[..., 3][rim] > 128
            diff = float((m != ref).mean())
            if diff < best[0]:
                best = (diff, float(deg))
        angles.append(best[1])
        out.append(im.rotate(best[1], resample=Image.BICUBIC))
    return out, angles


def order_variants(circles: list[Image.Image]) -> list[int]:
    """排一个首尾相接的播放顺序，让相邻两张的外圈轮廓尽量接近（变形幅度小）。变体不多，直接穷举。"""
    import itertools
    n = circles[0].width
    _, r, _ = _polar(n)
    rim = r > 0.6
    masks = [(np.asarray(im.convert("RGBA"))[..., 3] > 128)[rim] for im in circles]
    k = len(circles)
    diff = [[float((masks[i] != masks[j]).mean()) for j in range(k)] for i in range(k)]
    best = None
    for perm in itertools.permutations(range(1, k)):
        order = (0,) + perm
        cost = sum(diff[order[i]][order[(i + 1) % k]] for i in range(k))
        if best is None or cost < best[0]:
            best = (cost, list(order))
    return best[1]


def boil_frames(circles: list[Image.Image], steps: int, flow: int, swirl: float, drain: float) -> list[Image.Image]:
    """几张已对齐、已排好顺序的变体（2 倍分辨率）-> 循环动画帧（1 倍分辨率）。

    外圈：相邻两张之间用 steps 帧逐帧变形，最后一张变回第一张，首尾相接；
    中心：第一张做 flow 帧一个周期的流动；两部分按轮廓深度平滑衔接。
    总帧数 = lcm(张数 × steps, flow)，第 0 帧正好是第一张变体。"""
    import math
    layers = [_RimLayers(c) for c in circles]
    k = len(layers)
    n = circles[0].width
    centre = [f / 255.0 for f in _flow(np.asarray(circles[0].convert("RGBa")).astype(np.float32), flow, swirl, drain)]
    d0, d1 = RIM_BLEND[0] * n / 2, RIM_BLEND[1] * n / 2
    total = math.lcm(k * steps, flow)
    out = []
    for i in range(total):
        j, s = divmod(i % (k * steps), steps)
        rim, d = _rim_morph(layers[j], layers[(j + 1) % k], s / steps)
        mid = centre[i % flow]
        w = np.clip((d - d0) / (d1 - d0), 0, 1)
        w = (w * w * (3 - 2 * w))[..., None] * mid[..., 3:4]
        f = w * mid + (1 - w) * rim
        f = f.reshape(n // 2, 2, n // 2, 2, 4).mean(axis=(1, 3))  # 预乘状态下 2x2 平均缩小，边缘不发黑
        a = f[..., 3:4]
        rgb = np.where(a > 0.5 / 255, f[..., :3] / np.maximum(a, 1e-6), 0)
        out.append(Image.fromarray((np.dstack([rgb, a]) * 255).clip(0, 255).round().astype(np.uint8), "RGBA"))
    return out


def load_circle(src: Image.Image, size: int, alpha_floor: int, keep_islands: bool) -> Image.Image:
    """AI 画的椭圆 -> 正圆贴图：去掉不相连的碎片、按不透明区域裁切、拉成 size x size。"""
    img = src.convert("RGBA")
    if not keep_islands:
        img = drop_islands(img, alpha_floor)
    x0, y0, x1, y1 = alpha_bbox(img, alpha_floor)
    # 拉成正圆（不按原图比例）：贴图不圆的话，转起来轮廓会一胀一缩
    return img.crop((x0, y0, x1, y1)).convert("RGBa").resize((size, size), Image.LANCZOS).convert("RGBA")


def make_spin_package(srcs: list[Image.Image], name: str, width: int, period: int, pre: int, pst: int,
                      clockwise: bool, alpha_floor: int, squash: float, level: int,
                      keep_islands: bool = False, flow: int = 0, flow_size: int = 248,
                      flow_swirl: float = 2.2, flow_drain: float = 0.12,
                      boil_steps: int = 10) -> tuple[dict[str, bytes], dict]:
    """flow = 0：一张图整体旋转（同原版预警圈）。
    flow = N：先用 flow_frames 生成 N 张逐帧不同的流动图（同原版海上漩涡那样逐帧播放），再叠加整体慢慢旋转。
    srcs 有多张时（同一个漩涡的几个手绘变体）：中心用第一张做 N 帧一个周期的流动，外圈在相邻两张之间
    每 boil_steps 帧变形过去（boil_frames），总帧数 = lcm(张数 × boil_steps, N)。"""
    import math
    if len(srcs) > 1 and not flow:
        raise ValueError("多张变体需要配合 --flow 使用（中心流动一个周期的帧数）")
    tex_size = flow_size if flow else width
    pictures_n = math.lcm(len(srcs) * boil_steps, flow) if len(srcs) > 1 else flow
    if flow and period % pictures_n:
        raise ValueError(f"--period（{period}）必须是逐帧图张数（{pictures_n}）的整数倍，否则循环接不上")
    info: dict = {}
    if len(srcs) > 1:
        circles = [load_circle(sv, 2 * tex_size, alpha_floor, keep_islands) for sv in srcs]  # 2 倍分辨率做变形
        circles, angles = align_variants(circles)
        order = order_variants(circles)
        circles = [circles[i] for i in order]
        info = {"order": order, "angles": angles}
        pictures = boil_frames(circles, boil_steps, flow, flow_swirl, flow_drain)
    else:
        circles = [load_circle(srcs[0], tex_size, alpha_floor, keep_islands)]
        pictures = flow_frames(circles[0], flow, flow_swirl, flow_drain) if flow else circles

    sprites = []
    for pic in pictures:
        sp = Image.new("RGBA", (tex_size + 2 * EDGE_PAD, tex_size + 2 * EDGE_PAD))
        sp.paste(pic, (EDGE_PAD, EDGE_PAD))
        sprites.append(sp)
    positions, aw, ah = pack([sp.size for sp in sprites])
    atlas = Image.new("RGBA", (aw, ah))
    for sp, pos in zip(sprites, positions):
        atlas.paste(sp, pos)
    tex = png2tex.ktex_bytes(png2tex.mip_chain(atlas), BC3Encoder(level))

    sym = kanim.strhash(name)
    w = h = tex_size + 2 * EDGE_PAD
    bx0, bx1, by0, by1 = -w / 2, w / 2, -h / 2, h / 2   # 圆心在原点
    frames = []
    for i, (c0, r0) in enumerate(positions):
        u0, u1 = c0 / aw, (c0 + w) / aw
        v_top, v_bot = 1.0 - r0 / ah, 1.0 - (r0 + h) / ah
        verts = [(bx0, by0, 0.0, u0, v_top, 0.0), (bx1, by0, 0.0, u1, v_top, 0.0), (bx0, by1, 0.0, u0, v_bot, 0.0),
                 (bx1, by0, 0.0, u1, v_top, 0.0), (bx1, by1, 0.0, u1, v_bot, 0.0), (bx0, by1, 0.0, u0, v_bot, 0.0)]
        frames.append(kanim.BuildFrame(i, 1, (0.0, 0.0, float(w), float(h)), verts))
    build = kanim.Build(name=name, atlases=["atlas-0.tex"], symbols=[kanim.BuildSymbol(sym, frames)], names={sym: name})

    base_scale = width / tex_size   # 贴图分辨率和地面上大小可以不同
    step = (1 if clockwise else -1) * 2 * math.pi / period
    npic = len(pictures)

    def frame(i: int, scale: float) -> kanim.AnimFrame:
        m = spin_matrix(i * step, scale * base_scale, squash)
        bbox = (0.0, 0.0, w * scale * base_scale, h * scale * base_scale * squash)
        return kanim.AnimFrame(bbox, [], [kanim.AnimElement(sym, i % npic, sym, m, -5.0)])

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
    return members, {"texture": (w, h), "atlas": (aw, ah), "pictures": npic, "variants": len(srcs), **info}


def cmd_spin(args) -> int:
    try:
        members, meta = make_spin_package([Image.open(pth) for pth in args.inputs], args.name, args.width,
                                          args.period, args.pre,
                                          args.pst, args.clockwise, args.alpha_floor, args.squash, args.level,
                                          keep_islands=args.keep_islands, flow=args.flow, flow_size=args.flow_size,
                                          flow_swirl=args.flow_swirl, flow_drain=args.flow_drain,
                                          boil_steps=args.boil_steps)
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.zip"
    kanim.write_zip(out, members)
    print(f"动画包: {out}")
    print(f"  bank = build = symbol = {args.name!r}；动画 pre（{args.pre} 帧，长出来）/ loop（{args.period} 帧 = "
          f"{args.period / 30:.1f} 秒转一圈）/ pst（{args.pst} 帧，缩回去）")
    if meta["pictures"] > 1:
        print(f"  流动：{meta['pictures']} 张逐帧不同的图循环（{meta['pictures'] / 30:.2f} 秒一个周期），叠加整体旋转")
    if meta["variants"] > 1:
        names = [args.inputs[i].name for i in meta["order"]]
        print(f"  中心：第一张变体流动，{args.flow} 帧一个周期；外圈：{meta['variants']} 张变体之间逐帧变形，"
              f"每 {args.boil_steps} 帧变成下一张（{args.boil_steps / 30:.2f} 秒）")
        print(f"  播放顺序 {names}")
        print(f"  各变体为对齐外圈轮廓转过的角度（度）：{[round(a, 1) for a in meta['angles']]}")
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
    p.add_argument("inputs", type=Path, nargs="+",
                   help="一张图；或同一个图案的几张变体（外圈在变体之间逐帧变形，需要配合 --flow）")
    p.add_argument("--name", required=True, help="bank / build / symbol 名")
    p.add_argument("--width", type=int, default=320, help="地面上椭圆的宽度（build 像素）")
    p.add_argument("--period", type=int, default=90, help="转一圈的帧数（30 帧 = 1 秒）")
    p.add_argument("--pre", type=int, default=12, help="出现时长出来的帧数")
    p.add_argument("--pst", type=int, default=12, help="消失时缩回去的帧数")
    p.add_argument("--clockwise", action="store_true", help="顺时针转（默认逆时针）")
    p.add_argument("--keep-islands", action="store_true", help="保留和主体不相连的碎片（默认去掉）")
    p.add_argument("--flow", type=int, default=0,
                   help="中心流动一个周期的帧数（0 = 只整体旋转）；--period 必须是逐帧图总张数的整数倍")
    p.add_argument("--boil-steps", type=int, default=10,
                   help="多张变体时，外圈从一张变形到下一张用多少帧（逐帧图总张数 = lcm(张数 × 它, --flow)）")
    p.add_argument("--flow-size", type=int, default=248, help="流动帧的贴图边长（像素），地面上的大小仍由 --width 决定")
    p.add_argument("--flow-swirl", type=float, default=2.2, help="一个周期里中心比外圈多转的角度（弧度）")
    p.add_argument("--flow-drain", type=float, default=0.12, help="一个周期里往中心吸进去的程度（半径比例）")
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
