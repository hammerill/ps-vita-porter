"""Image headers without dependencies: PNG chunk analysis (what LiveArea cares about), a small PNG writer for
fixtures, and size/format sniffing for PNG, JPEG, BMP, TGA, DDS, KTX, GIF, WebP (asset inventory)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"
COLOR_TYPES = {0: "grayscale", 2: "rgb", 3: "indexed", 4: "grayscale+alpha", 6: "rgba"}
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def png_info(path: str | Path) -> dict:
    """Header facts of a PNG: width, height, bit_depth, color_type (+name), palette_entries, has_trns, alpha.
    Raises ValueError for anything that isn't a PNG."""
    data = Path(path).read_bytes()
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG file")
    pos, info = 8, {}
    chunks = []
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        chunks.append(ctype.decode("latin-1"))
        if ctype == b"IHDR":
            w, h, depth, color, _comp, _flt, interlace = struct.unpack(">IIBBBBB", body[:13])
            info.update(width=w, height=h, bit_depth=depth, color_type=color, color=COLOR_TYPES.get(color, f"unknown {color}"),
                        interlaced=bool(interlace))
        elif ctype == b"PLTE":
            info["palette_entries"] = length // 3
        elif ctype == b"tRNS":
            info["has_trns"] = True
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if "width" not in info:
        raise ValueError("PNG without IHDR")
    info.setdefault("palette_entries", 0)
    info.setdefault("has_trns", False)
    info["alpha"] = info["color_type"] in (4, 6) or info["has_trns"]
    info["chunks"] = chunks
    info["size"] = len(data)
    return info


def write_png(path: str | Path, width: int, height: int, pixels: bytes, color_type: int = 2, bit_depth: int = 8,
              palette: bytes | None = None, trns: bytes | None = None):
    """Write a PNG from raw rows (no filter). pixels: width*height*channels*(bit_depth/8) bytes, big-endian for 16-bit;
    for color_type 3 one index byte per pixel (bit_depth 8) and `palette` as RGB triplets."""
    ch = CHANNELS[color_type]
    bpp = ch * bit_depth // 8
    stride = width * bpp
    if len(pixels) != stride * height:
        raise ValueError(f"expected {stride * height} bytes of pixels, got {len(pixels)}")
    raw = b"".join(b"\0" + pixels[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(t: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body) & 0xFFFFFFFF)

    out = PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0))
    if palette is not None:
        out += chunk(b"PLTE", palette)
    if trns is not None:
        out += chunk(b"tRNS", trns)
    out += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    Path(path).write_bytes(out)


def _chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    pos, out = 8, []
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        out.append((ctype, data[pos + 8:pos + 8 + length]))
        if ctype == b"IEND":
            break
        pos += 12 + length
    return out


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytes:
    """Undo PNG scanline filters (non-interlaced). bpp = bytes per complete pixel, at least 1."""
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if ft == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ft == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ft == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
        out += line
        prev = line
    return bytes(out)


def expand_indexed_to_8bit(path: str | Path) -> bool:
    """Rewrite a 1/2/4-bit indexed PNG as 8-bit indexed (same palette and tRNS). pngquant writes low bit depths
    for images with few colours; LiveArea wants 8 bits. Returns True if the file was rewritten."""
    p = Path(path)
    data = p.read_bytes()
    info = png_info(p)
    if info["color_type"] != 3 or info["bit_depth"] == 8:
        return False
    if info["interlaced"]:
        raise ValueError("interlaced indexed PNG: re-encode it without interlacing first")
    ch = _chunks(data)
    plte = next(b for t, b in ch if t == b"PLTE")
    trns = next((b for t, b in ch if t == b"tRNS"), None)
    raw = zlib.decompress(b"".join(b for t, b in ch if t == b"IDAT"))
    w, h, d = info["width"], info["height"], info["bit_depth"]
    stride = (w * d + 7) // 8
    rows = _unfilter(raw, h, stride, 1)
    per = 8 // d
    mask = (1 << d) - 1
    idx = bytearray()
    for y in range(h):
        row = rows[y * stride:(y + 1) * stride]
        for x in range(w):
            byte = row[x // per]
            shift = 8 - d * (x % per + 1)
            idx.append((byte >> shift) & mask)
    write_png(p, w, h, bytes(idx), color_type=3, bit_depth=8, palette=plte, trns=trns)
    return True


def sniff(path: str | Path) -> dict | None:
    """{format, width, height, channels?, compressed?} from the header, or None if not a known image."""
    p = Path(path)
    try:
        with open(p, "rb") as fh:
            head = fh.read(256)
    except OSError:
        return None
    ext = p.suffix.lower()
    try:
        if head.startswith(PNG_SIG) and head[12:16] == b"IHDR":
            w, h, depth, color = struct.unpack(">IIBB", head[16:26])
            return dict(format="png", width=w, height=h, channels=CHANNELS.get(color, 4), bit_depth=depth)
        if head[:2] == b"\xff\xd8":
            return _jpeg(p)
        if head[:2] == b"BM" and len(head) >= 26:
            w, h = struct.unpack("<ii", head[18:26])
            return dict(format="bmp", width=w, height=abs(h), channels=4)
        if head[:4] == b"DDS ":
            h, w = struct.unpack("<II", head[12:20])
            four = head[84:88].decode("latin-1", "replace")
            return dict(format="dds", width=w, height=h, compressed=four.strip("\0") or "uncompressed")
        if head[:12] == b"\xabKTX 11\xbb\r\n\x1a\n":
            w, h = struct.unpack("<II", head[36:44])
            return dict(format="ktx", width=w, height=h, compressed="ktx")
        if head[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", head[6:10])
            return dict(format="gif", width=w, height=h, channels=4)
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            return dict(format="webp", width=None, height=None, channels=4)
        if ext == ".tga" and len(head) >= 18 and head[2] in (1, 2, 3, 9, 10, 11):
            w, h = struct.unpack("<HH", head[12:16])
            return dict(format="tga", width=w, height=h, channels=max(1, head[16] // 8))
    except struct.error:
        return None
    return None


def _jpeg(p: Path) -> dict | None:
    data = p.read_bytes()
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return dict(format="jpeg", width=w, height=h, channels=3)
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        i += 2 + seg
    return dict(format="jpeg", width=None, height=None, channels=3)
