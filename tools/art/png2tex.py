#!/usr/bin/env python3
"""
PNG -> DST 贴图（KTEX .tex + 图集 .xml），纯 Python，不依赖 Don't Starve Mod Tools。

格式约定全部对照游戏自带文件实测（build 756039，images/inventoryimages*.tex），并与 ktools(ktech) 源码默认行为一致：
  * 文件头："KTEX" + 32 位字：platform=0, compression=DXT5(2), texture_type=2D(1), mipmaps=N, flags=3, fill=0xFFF
  * 每级 mipmap 描述：u16 宽, u16 高, u16 pitch(每行块字节数), u32 数据字节数；随后依次是各级数据
  * 完整 mipmap 链一直到 1x1（小于 4 像素的级别仍占一个 16 字节的 DXT5 块）
  * 预乘 alpha（alpha <= 0.1 的像素 RGB 置 0，同 ktech）
  * 数据按"上下翻转"存储（原版图标解码后是倒着的，ktech 也默认翻转）
  * 图集 UV 向内缩半个像素（原版惯例）

用法：
  python tools/art/png2tex.py art/icons/tide_crystal.png
  python tools/art/png2tex.py art/icons/tide_crystal.png --out-dir mod/images/inventoryimages --name tide_crystal
输出：<out-dir>/<name>.tex 与 <out-dir>/<name>.xml，并做一次"解码回读"自检。

依赖：Pillow、numpy、quicktex（DXT5 编码）、texture2ddecoder（回读校验，可选）
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
    from quicktex import RawTexture
    from quicktex.s3tc.bc3 import BC3Encoder
except ImportError as e:  # pragma: no cover
    print(f"缺少依赖：{e}。请先运行  pip install -r tools/requirements.txt")
    sys.exit(2)

REPO = Path(__file__).resolve().parents[2]

PLATFORM_DEFAULT = 0
COMPRESSION_DXT5 = 2
TEXTURE_2D = 1
FLAGS = 3
FILL = 0xFFF


def is_pow2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def mip_chain(img: Image.Image) -> list[Image.Image]:
    """在预乘 alpha 空间逐级缩小，避免透明边缘混色。"""
    levels = [img]
    w, h = img.size
    while w > 1 or h > 1:
        w, h = max(1, w // 2), max(1, h // 2)
        levels.append(img.convert("RGBa").resize((w, h), Image.LANCZOS).convert("RGBA"))
    return levels


def premultiply(img: Image.Image) -> np.ndarray:
    a = np.asarray(img, dtype=np.float32)
    alpha = a[..., 3:4] / 255.0
    alpha = np.where(alpha <= 0.1, 0.0, alpha)  # 与 ktech premultiplyPixelAlpha 相同
    out = a.copy()
    out[..., :3] = np.round(a[..., :3] * alpha)
    return out.clip(0, 255).astype(np.uint8)


def encode_dxt5(rgba: np.ndarray, encoder: BC3Encoder) -> tuple[bytes, int]:
    h, w = rgba.shape[:2]
    bw, bh = max(1, (w + 3) // 4), max(1, (h + 3) // 4)
    padded = np.zeros((bh * 4, bw * 4, 4), dtype=np.uint8)
    padded[:h, :w] = rgba
    data = encoder.encode(RawTexture.frombytes(padded.tobytes(), bw * 4, bh * 4)).tobytes()
    assert len(data) == bw * bh * 16
    return data, bw * 16  # pitch = 每行块的字节数（与 ktech/squish 一致）


def write_ktex(levels: list[Image.Image], path: Path, encoder: BC3Encoder) -> None:
    descs, blobs = [], []
    for lvl in levels:
        rgba = np.flipud(premultiply(lvl))  # 存储时上下翻转
        data, pitch = encode_dxt5(np.ascontiguousarray(rgba), encoder)
        descs.append(struct.pack("<HHHI", lvl.width, lvl.height, pitch, len(data)))
        blobs.append(data)
    word = (PLATFORM_DEFAULT
            | (COMPRESSION_DXT5 << 4)
            | (TEXTURE_2D << 9)
            | (len(levels) << 13)
            | (FLAGS << 18)
            | (FILL << 20))
    path.write_bytes(b"KTEX" + struct.pack("<I", word) + b"".join(descs) + b"".join(blobs))


def write_atlas(xml_path: Path, tex_name: str, element: str, w: int, h: int) -> None:
    du, dv = 0.5 / w, 0.5 / h
    xml_path.write_text(
        f'<Atlas><Texture filename="{tex_name}" /><Elements>'
        f'<Element name="{element}" u1="{du:.7f}" u2="{1 - du:.7f}" v1="{dv:.7f}" v2="{1 - dv:.7f}" />'
        f'</Elements></Atlas>\n',
        encoding="utf-8",
    )


def verify(tex_path: Path, source: Image.Image) -> None:
    """用独立的解码器读回第 0 级，翻转、反预乘后与源图比较。"""
    try:
        import texture2ddecoder
    except ImportError:
        print("[INFO] 未安装 texture2ddecoder，跳过回读校验")
        return
    data = tex_path.read_bytes()
    w, h, _pitch, size = struct.unpack("<HHHI", data[8:18])
    mips = (struct.unpack("<I", data[4:8])[0] >> 13) & 0x1F
    off = 8 + 10 * mips
    bgra = texture2ddecoder.decode_bc3(data[off:off + size], w, h)
    dec = np.frombuffer(bgra, dtype=np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]]
    dec = np.flipud(dec).astype(np.float32)
    ref = premultiply(source).astype(np.float32)
    mask = ref[..., 3] > 25
    err_rgb = np.abs(dec[..., :3] - ref[..., :3])[mask].mean() if mask.any() else 0.0
    err_a = np.abs(dec[..., 3] - ref[..., 3]).mean()
    print(f"[OK] 回读校验：平均误差 RGB {err_rgb:.1f} / Alpha {err_a:.1f}"
          f"（0-255；DXT5 有损压缩，细节多的图 10 左右属正常）")
    if err_rgb > 16 or err_a > 8:
        print("[WARN] 误差偏大：检查源图是否有大量细碎噪点，或把 art/review 预览和游戏内效果对比一下")


def main() -> int:
    ap = argparse.ArgumentParser(description="PNG -> DST KTEX(.tex) + atlas(.xml)")
    ap.add_argument("input", type=Path, help="源 PNG（物品栏图标建议先用 prepare_icon.py 处理成 64x64）")
    ap.add_argument("--name", help="输出名（默认取输入文件名），图集里的元素名为 <name>.tex")
    ap.add_argument("--out-dir", type=Path, default=REPO / "mod" / "images" / "inventoryimages")
    ap.add_argument("--level", type=int, default=12, help="DXT 编码质量 0-18（默认 12）")
    args = ap.parse_args()

    name = args.name or args.input.stem
    img = Image.open(args.input).convert("RGBA")
    w, h = img.size
    if not (is_pow2(w) and is_pow2(h)):
        print(f"[ERROR] 尺寸 {w}x{h} 不是 2 的幂（物品栏图标用 64x64）")
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = args.out_dir / f"{name}.tex"
    xml_path = args.out_dir / f"{name}.xml"
    levels = mip_chain(img)
    write_ktex(levels, tex_path, BC3Encoder(args.level))
    write_atlas(xml_path, tex_path.name, f"{name}.tex", w, h)
    print(f"贴图: {tex_path}  ({w}x{h}, DXT5, {len(levels)} 级 mipmap)")
    print(f"图集: {xml_path}")
    verify(tex_path, img)
    return 0


if __name__ == "__main__":
    sys.exit(main())
