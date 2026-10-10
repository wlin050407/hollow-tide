"""
DST 动画包（anim/*.zip）的二进制格式读写库 —— 只用 Python 标准库，check_mod.py 和 make_anim.py 共用。

动画包是一个 zip（deflate），里面有：
  build.bin     "外观"：每个 symbol（部件）的若干帧图片，每帧是若干个四边形，指向 atlas 贴图的某块区域
  anim.bin      "动画"：bank 下的若干动画，每帧摆放哪些 symbol 的第几帧、用什么 2D 变换
  atlas-N.tex   贴图（KTEX，DXT5，预乘 alpha，上下翻转存储，完整 mipmap，和物品栏图标相同的约定）
只有 build 没有 anim 的包也合法（例如原版 moondial_build.zip），反过来也一样（moondial.zip）。

格式全部对照游戏自带文件实测（build 756039 的 gems / flint / moondial / moondial_build），
并用 `make_anim.py selftest` 验证：读入再写出与原文件逐字节相同。

build.bin（小端）：
  "BILD" u32 version(=6) u32 nsymbols u32 nframes(所有 symbol 的帧数之和)
  str build_name  u32 natlases  natlases*str atlas_name
  每个 symbol（按 hash 升序）：u32 hash  u32 nframes
      每帧：u32 framenum  u32 duration  f32 x y w h（包围盒中心与宽高）  u32 vert_start  u32 vert_count(6 的倍数)
  u32 nverts  nverts*(f32 x y z u v w)   —— 每 6 个顶点 = 一个矩形的两个三角形；w = atlas 序号
  u32 nhash  nhash*(u32 hash, str name)
anim.bin（小端）：
  "ANIM" u32 version(=4) u32 总元素数 u32 总帧数 u32 总事件数 u32 nanims
  每个动画：str name  u8 facing(255=所有朝向)  u32 bank_hash  f32 fps  u32 nframes
      每帧：f32 x y w h  u32 nevents nevents*u32  u32 nelements
          每个元素：u32 symbol_hash  u32 build_frame  u32 layer_hash  f32 a b c d tx ty  f32 z
  u32 nhash  nhash*(u32 hash, str name)
str = u32 长度 + 字节。

坐标约定（已用原版贴图渲染验证）：
  * 动画坐标 y 轴向下为正：负 y 是"往上"（建筑主体的 ty 都是负数，例如 moondial basin ty=-140）
  * 1 个 build 单位 = 1 个 atlas 像素（gems/flint 都是 1:1）
  * UV 的 v=0 是贴图文件里存储的第一行；因为存储时上下翻转，所以 v 越大越靠近图片顶部：
    矩形上沿（y 较小）对应较大的 v
"""

from __future__ import annotations

import io
import struct
import zipfile
from dataclasses import dataclass, field

BUILD_VERSION = 6
ANIM_VERSION = 4
FACING_ALL = 255
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def strhash(s: str) -> int:
    """Klei 的字符串 hash（不区分大小写）。与游戏里 symbol / layer / bank 名的 hash 一致。"""
    h = 0
    for ch in s.lower():
        h = (ord(ch) + (h << 6) + (h << 16) - h) & 0xFFFFFFFF
    return h


# ---------------------------------------------------------------------------
# 数据结构：名字一律以 hash 存放，names 表单独保存（保持文件里的顺序，保证逐字节往返）
# ---------------------------------------------------------------------------

@dataclass
class BuildFrame:
    framenum: int
    duration: int
    bbox: tuple[float, float, float, float]          # 中心 x, 中心 y, 宽, 高
    verts: list[tuple[float, float, float, float, float, float]]  # (x, y, z, u, v, atlas)


@dataclass
class BuildSymbol:
    hash: int
    frames: list[BuildFrame]


@dataclass
class Build:
    name: str
    atlases: list[str]
    symbols: list[BuildSymbol]
    names: dict[int, str] = field(default_factory=dict)
    version: int = BUILD_VERSION


@dataclass
class AnimElement:
    symbol: int                     # hash
    build_frame: int
    layer: int                      # hash
    matrix: tuple[float, float, float, float, float, float]  # a b c d tx ty
    z: float


@dataclass
class AnimFrame:
    bbox: tuple[float, float, float, float]
    events: list[int]
    elements: list[AnimElement]


@dataclass
class Animation:
    name: str
    facing: int
    bank: int                       # hash
    fps: float
    frames: list[AnimFrame]


@dataclass
class AnimFile:
    anims: list[Animation]
    names: dict[int, str] = field(default_factory=dict)
    version: int = ANIM_VERSION


class FormatError(ValueError):
    pass


# ---------------------------------------------------------------------------
# 读写基础
# ---------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, fmt: str):
        try:
            values = struct.unpack_from(fmt, self.data, self.pos)
        except struct.error as e:
            raise FormatError(f"文件在偏移 {self.pos} 处提前结束") from e
        self.pos += struct.calcsize(fmt)
        return values

    def u8(self) -> int:
        return self.take("<B")[0]

    def u32(self) -> int:
        return self.take("<I")[0]

    def str(self) -> str:
        n = self.u32()
        if self.pos + n > len(self.data):
            raise FormatError(f"字符串长度 {n} 超出文件范围（偏移 {self.pos}）")
        s = self.data[self.pos:self.pos + n].decode("latin-1")
        self.pos += n
        return s

    def tag(self) -> bytes:
        t = self.data[self.pos:self.pos + 4]
        self.pos += 4
        return t

    def names(self) -> dict[int, str]:
        out: dict[int, str] = {}
        if self.pos >= len(self.data):
            return out
        for _ in range(self.u32()):
            h = self.u32()
            out[h] = self.str()
        return out


class _Writer:
    def __init__(self):
        self.buf = io.BytesIO()

    def put(self, fmt: str, *values) -> None:
        self.buf.write(struct.pack(fmt, *values))

    def str(self, s: str) -> None:
        b = s.encode("latin-1")
        self.put("<I", len(b))
        self.buf.write(b)

    def names(self, names: dict[int, str]) -> None:
        self.put("<I", len(names))
        for h, s in names.items():
            self.put("<I", h)
            self.str(s)

    def bytes(self) -> bytes:
        return self.buf.getvalue()


# ---------------------------------------------------------------------------
# build.bin
# ---------------------------------------------------------------------------

def read_build(data: bytes) -> Build:
    r = _Reader(data)
    if r.tag() != b"BILD":
        raise FormatError("build.bin 缺少 'BILD' 文件头")
    version = r.u32()
    if version != BUILD_VERSION:
        raise FormatError(f"build.bin 版本 {version}，本工具只认识 {BUILD_VERSION}")
    nsymbols, total_frames = r.take("<II")
    name = r.str()
    atlases = [r.str() for _ in range(r.u32())]
    raw = []
    for _ in range(nsymbols):
        h, nframes = r.take("<II")
        frames = []
        for _ in range(nframes):
            framenum, duration, x, y, w, hh, start, count = r.take("<II4fII")
            frames.append((framenum, duration, (x, y, w, hh), start, count))
        raw.append((h, frames))
    nverts = r.u32()
    flat = r.take(f"<{nverts * 6}f")
    verts = [tuple(flat[i:i + 6]) for i in range(0, len(flat), 6)]
    names = r.names()
    if r.pos != len(data):
        raise FormatError(f"build.bin 解析到 {r.pos} 字节就结束了，文件共有 {len(data)} 字节")
    if sum(len(f) for _, f in raw) != total_frames:
        raise FormatError("build.bin 头部的帧数与实际帧数不符")

    symbols = []
    expected_start = 0
    for h, frames in raw:
        out = []
        for framenum, duration, bbox, start, count in frames:
            if count % 6 or start + count > nverts:
                raise FormatError(f"symbol {names.get(h, hex(h))} 的顶点范围 {start}+{count} 不合法")
            if start != expected_start:
                raise FormatError("build.bin 的顶点不是按 symbol/帧 顺序连续存放的（本工具不支持）")
            expected_start += count
            out.append(BuildFrame(framenum, duration, bbox, verts[start:start + count]))
        symbols.append(BuildSymbol(h, out))
    return Build(name=name, atlases=atlases, symbols=symbols, names=names, version=version)


def write_build(build: Build) -> bytes:
    w = _Writer()
    w.buf.write(b"BILD")
    w.put("<III", build.version, len(build.symbols), sum(len(s.frames) for s in build.symbols))
    w.str(build.name)
    w.put("<I", len(build.atlases))
    for a in build.atlases:
        w.str(a)
    start = 0
    for sym in build.symbols:
        w.put("<II", sym.hash, len(sym.frames))
        for f in sym.frames:
            w.put("<II4fII", f.framenum, f.duration, *f.bbox, start, len(f.verts))
            start += len(f.verts)
    w.put("<I", start)
    for sym in build.symbols:
        for f in sym.frames:
            for v in f.verts:
                w.put("<6f", *v)
    w.names(build.names)
    return w.bytes()


# ---------------------------------------------------------------------------
# anim.bin
# ---------------------------------------------------------------------------

def read_anim(data: bytes) -> AnimFile:
    r = _Reader(data)
    if r.tag() != b"ANIM":
        raise FormatError("anim.bin 缺少 'ANIM' 文件头")
    version = r.u32()
    if version != ANIM_VERSION:
        raise FormatError(f"anim.bin 版本 {version}，本工具只认识 {ANIM_VERSION}")
    total_elements, total_frames, total_events, nanims = r.take("<IIII")
    anims = []
    for _ in range(nanims):
        name = r.str()
        facing = r.u8()
        bank, fps, nframes = r.take("<IfI")
        frames = []
        for _ in range(nframes):
            bbox = r.take("<4f")
            events = list(r.take(f"<{r.u32()}I"))
            elements = []
            for _ in range(r.u32()):
                sym, bframe, layer, a, b, c, d, tx, ty, z = r.take("<III7f")
                elements.append(AnimElement(sym, bframe, layer, (a, b, c, d, tx, ty), z))
            frames.append(AnimFrame(bbox, events, elements))
        anims.append(Animation(name, facing, bank, fps, frames))
    names = r.names()
    if r.pos != len(data):
        raise FormatError(f"anim.bin 解析到 {r.pos} 字节就结束了，文件共有 {len(data)} 字节")
    out = AnimFile(anims=anims, names=names, version=version)
    if anim_totals(out) != (total_elements, total_frames, total_events):
        raise FormatError("anim.bin 头部的元素/帧/事件总数与实际内容不符")
    return out


def anim_totals(af: AnimFile) -> tuple[int, int, int]:
    frames = [f for a in af.anims for f in a.frames]
    return (sum(len(f.elements) for f in frames), len(frames), sum(len(f.events) for f in frames))


def write_anim(af: AnimFile) -> bytes:
    w = _Writer()
    w.buf.write(b"ANIM")
    w.put("<I", af.version)
    w.put("<III", *anim_totals(af))
    w.put("<I", len(af.anims))
    for a in af.anims:
        w.str(a.name)
        w.put("<B", a.facing)
        w.put("<IfI", a.bank, a.fps, len(a.frames))
        for f in a.frames:
            w.put("<4f", *f.bbox)
            w.put("<I", len(f.events))
            for e in f.events:
                w.put("<I", e)
            w.put("<I", len(f.elements))
            for e in f.elements:
                w.put("<III7f", e.symbol, e.build_frame, e.layer, *e.matrix, e.z)
    w.names(af.names)
    return w.bytes()


# ---------------------------------------------------------------------------
# zip
# ---------------------------------------------------------------------------

def write_zip(path, members: dict[str, bytes]) -> None:
    """固定时间戳 + deflate（和原版一致），同样的输入总是得到同样的 zip，方便 git 对比。"""
    with zipfile.ZipFile(path, "w") as z:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            z.writestr(info, members[name], compresslevel=9)
