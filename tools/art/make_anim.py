#!/usr/bin/env python3
"""
生成 DST 动画包（anim/<name>.zip），不依赖 Spriter 和 Don't Starve Mod Tools。

现在只做最简单、也是最常用的一种：**一张图 = 一个 symbol 的一帧 = 一个单帧动画 "idle"**。
用于物品掉在地上的样子；以后建筑/多帧动画需要时再扩展（格式读写在 kanim.py 里已经是通用的）。

子命令
  item      PNG -> mod/anim/<name>.zip（bank = build = symbol = <name>，动画 "idle"），并输出审查预览图
  preview   把任意动画包（自己的或原版的）的某个动画第 0 帧画出来，可以多个并排对比大小
  selftest  读入原版动画包再写出，确认与原文件逐字节相同（证明 kanim.py 的格式理解是对的）

用法示例
  python tools/art/make_anim.py item art/ground/tide_crystal.png --name tide_crystal --height 150 --pivot 0.5,0.75 \
      --compare "<DST>/data/anim/gems.zip:bluegem_idle" --compare "<DST>/data/anim/flint.zip:idle"
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
# 渲染：把动画某一帧画成图片（只支持缩放/翻转，不支持旋转——预览够用）
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
        if abs(b) > 1e-6 or abs(c) > 1e-6:
            warn("  预览：有旋转的元素按未旋转绘制（只影响预览）")
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
# item：一张图 -> 单帧动画包
# ---------------------------------------------------------------------------

def prepare_sprite(src: Image.Image, height: int, alpha_floor: int) -> Image.Image:
    """按不透明区域裁切，在预乘空间里缩放到指定高度，四周加透明边。"""
    img = src.convert("RGBA")
    a = np.asarray(img)[..., 3]
    ys, xs = np.nonzero(a > alpha_floor)
    if len(xs) == 0:
        raise ValueError("图片是全透明的")
    img = img.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))
    w = max(1, round(img.width * height / img.height))
    img = img.convert("RGBa").resize((w, height), Image.LANCZOS).convert("RGBA")
    out = Image.new("RGBA", (w + 2 * EDGE_PAD, height + 2 * EDGE_PAD))
    out.paste(img, (EDGE_PAD, EDGE_PAD))
    return out


def next_pow2(n: int) -> int:
    p = 1
    while p < n:
        p *= 2
    return p


def make_item(sprite: Image.Image, name: str, pivot: tuple[float, float], level: int) -> tuple[dict[str, bytes], dict]:
    w, h = sprite.size
    aw, ah = next_pow2(w), next_pow2(h)
    atlas = Image.new("RGBA", (aw, ah))
    atlas.paste(sprite, (0, 0))  # 放在左上角（正向图片坐标）
    tex = png2tex.ktex_bytes(png2tex.mip_chain(atlas), BC3Encoder(level))

    # 原点在图上的像素位置（含透明边）
    px = EDGE_PAD + pivot[0] * (w - 2 * EDGE_PAD)
    py = EDGE_PAD + pivot[1] * (h - 2 * EDGE_PAD)
    x0, x1 = -px, w - px          # build 坐标：x 向右
    y0, y1 = -py, h - py          # build 坐标：y 向下为正（y0 是上沿）
    u0, u1 = 0.0, w / aw
    v_top, v_bot = 1.0, 1.0 - h / ah  # 上沿 v 大（贴图上下翻转存储）
    # 顶点顺序与原版一致：左上、右上、左下、右上、右下、左下
    verts = [(x0, y0, 0.0, u0, v_top, 0.0), (x1, y0, 0.0, u1, v_top, 0.0), (x0, y1, 0.0, u0, v_bot, 0.0),
             (x1, y0, 0.0, u1, v_top, 0.0), (x1, y1, 0.0, u1, v_bot, 0.0), (x0, y1, 0.0, u0, v_bot, 0.0)]
    bbox = ((x0 + x1) / 2, (y0 + y1) / 2, float(w), float(h))

    sym = kanim.strhash(name)
    build = kanim.Build(
        name=name,
        atlases=["atlas-0.tex"],
        symbols=[kanim.BuildSymbol(sym, [kanim.BuildFrame(0, 1, bbox, verts)])],
        names={sym: name},
    )
    element = kanim.AnimElement(symbol=sym, build_frame=0, layer=sym,
                                matrix=(1.0, 0.0, 0.0, 1.0, 0.0, 0.0), z=-5.0)  # 单元素时原版 z=-5
    anim = kanim.AnimFile(
        anims=[kanim.Animation("idle", kanim.FACING_ALL, sym, 30.0, [kanim.AnimFrame(bbox, [], [element])])],
        names={sym: name},
    )
    members = {"build.bin": kanim.write_build(build), "anim.bin": kanim.write_anim(anim), "atlas-0.tex": tex}
    return members, {"sprite": (w, h), "atlas": (aw, ah), "origin_px": (px, py)}


def cmd_item(args) -> int:
    src = Image.open(args.input)
    sprite = prepare_sprite(src, args.height, args.alpha_floor)
    try:
        pvx, pvy = (float(t) for t in args.pivot.split(","))
    except ValueError:
        print("[ERROR] --pivot 格式是 x,y，例如 0.5,0.75")
        return 1
    members, meta = make_item(sprite, args.name, (pvx, pvy), args.level)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{args.name}.zip"
    kanim.write_zip(out, members)
    print(f"动画包: {out}")
    print(f"  bank = build = symbol = {args.name!r}，动画 'idle'（1 帧）")
    print(f"  图 {meta['sprite'][0]}x{meta['sprite'][1]}（含 {EDGE_PAD}px 透明边），atlas {meta['atlas'][0]}x{meta['atlas'][1]}，"
          f"原点在图上 ({meta['origin_px'][0]:.1f}, {meta['origin_px'][1]:.1f})")

    # 回读：重新解析 zip，渲染 idle 第 0 帧，与输入的图比较
    build, anim, atlases = load_zip(out)
    assert kanim.write_build(build) == members["build.bin"] and kanim.write_anim(anim) == members["anim.bin"]
    img, _ = render_frame(build, atlases, anim.anims[0].frames[0])
    ref = np.asarray(sprite, dtype=np.float32)
    got = np.asarray(img.crop((0, 0) + sprite.size), dtype=np.float32)
    mask = ref[..., 3] > 25
    err_rgb = float(np.abs(got[..., :3] - ref[..., :3])[mask].mean()) if mask.any() else 0.0
    err_a = float(np.abs(got[..., 3] - ref[..., 3]).mean())
    print(f"[OK] 回读：zip 结构可解析；渲染结果与原图平均误差 RGB {err_rgb:.1f} / Alpha {err_a:.1f}（DXT5 有损，10 左右正常）")
    if err_rgb > 16 or err_a > 8:
        print("[WARN] 误差偏大，看一下预览图")

    items = [render_ref(f"{out}:idle")]
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
