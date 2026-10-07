"""Texture helpers for `vita assets convert`: decode any image to RGBA with ffmpeg, encode BC1 (DXT1) and BC3 (DXT5)
in pure Python, write DDS. The Vita's GPU samples S3TC/UBC natively (vitaGL: glCompressedTexImage2D with
GL_COMPRESSED_RGB(A)_S3TC_DXT1/5_EXT). The encoder is a simple bounding-box fit: good for UI-free world textures,
not for pixel art or text (keep those uncompressed). For large sets, etcpak or another encoder is faster."""
from __future__ import annotations

import struct
import subprocess
from pathlib import Path


def decode_rgba(src: Path, width: int, height: int, scale_filter: str | None = None) -> bytes:
    """RGBA8 pixels of `src`, scaled to width x height (ffmpeg)."""
    vf = scale_filter or f"scale={width}:{height}:flags=lanczos"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(src), "-vf", vf, "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgba", "-"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg could not decode {src}: {r.stderr.decode(errors='replace')[-300:]}")
    if len(r.stdout) != width * height * 4:
        raise RuntimeError(f"ffmpeg returned {len(r.stdout)} bytes for {width}x{height} RGBA")
    return r.stdout


def _565(r: int, g: int, b: int) -> int:
    return ((r * 31 + 127) // 255) << 11 | ((g * 63 + 127) // 255) << 5 | ((b * 31 + 127) // 255)


def _unpack565(c: int) -> tuple[int, int, int]:
    r, g, b = (c >> 11) & 31, (c >> 5) & 63, c & 31
    return (r << 3 | r >> 2, g << 2 | g >> 4, b << 3 | b >> 2)


def _color_block(px: list[tuple[int, int, int, int]]) -> bytes:
    # endpoints: the two pixels farthest apart along the luminance axis of the block's bounding box
    lum = [(p[0] * 2 + p[1] * 4 + p[2], i) for i, p in enumerate(px)]
    hi, lo = px[max(lum)[1]], px[min(lum)[1]]
    c0, c1 = _565(*hi[:3]), _565(*lo[:3])
    if c0 < c1:
        c0, c1 = c1, c0
    if c0 == c1:
        return struct.pack("<HHI", c0, c1, 0)
    e0, e1 = _unpack565(c0), _unpack565(c1)
    pal = [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1, strict=True)), tuple((a + 2 * b) // 3 for a, b in zip(e0, e1, strict=True))]
    bits = 0
    for i, p in enumerate(px):
        best = min(range(4), key=lambda k: (p[0] - pal[k][0]) ** 2 + (p[1] - pal[k][1]) ** 2 + (p[2] - pal[k][2]) ** 2)
        bits |= best << (2 * i)
    return struct.pack("<HHI", c0, c1, bits)


def _alpha_block(px: list[tuple[int, int, int, int]]) -> bytes:
    al = [p[3] for p in px]
    a0, a1 = max(al), min(al)
    if a0 == a1:
        return struct.pack("<BB", a0, a1) + b"\0" * 6
    pal = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    bits = 0
    for i, a in enumerate(al):
        best = min(range(8), key=lambda k: abs(a - pal[k]))
        bits |= best << (3 * i)
    return struct.pack("<BB", a0, a1) + bits.to_bytes(6, "little")


def encode(rgba: bytes, width: int, height: int, fmt: str) -> bytes:
    """BC1 ("dxt1") or BC3 ("dxt5") blocks for an RGBA8 image; width/height padded to multiples of 4 by edge clamping."""
    out = bytearray()
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            px = []
            for y in range(4):
                yy = min(by + y, height - 1)
                for x in range(4):
                    xx = min(bx + x, width - 1)
                    o = (yy * width + xx) * 4
                    px.append((rgba[o], rgba[o + 1], rgba[o + 2], rgba[o + 3]))
            if fmt == "dxt5":
                out += _alpha_block(px)
            out += _color_block(px)
    return bytes(out)


def dds(width: int, height: int, fmt: str, blocks: bytes) -> bytes:
    """A DDS file (one mip level) around BC1/BC3 blocks."""
    four = b"DXT1" if fmt == "dxt1" else b"DXT5"
    linear = len(blocks)
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000          # CAPS HEIGHT WIDTH PIXELFORMAT LINEARSIZE
    pf = struct.pack("<II4sIIIII", 32, 0x4, four, 0, 0, 0, 0, 0)
    head = struct.pack("<IIIIIII", 124, flags, height, width, linear, 0, 1) + b"\0" * 44 + pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    return b"DDS " + head + blocks


def decode_dxt(blocks: bytes, width: int, height: int, fmt: str) -> bytes:
    """Inverse of encode (for tests and spot checks): RGBA8 pixels."""
    out = bytearray(width * height * 4)
    step = 16 if fmt == "dxt5" else 8
    i = 0
    for by in range(0, height, 4):
        for bx in range(0, width, 4):
            blk = blocks[i:i + step]
            i += step
            alpha = [255] * 16
            if fmt == "dxt5":
                a0, a1 = blk[0], blk[1]
                pal = [a0, a1] + ([((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)] if a0 > a1 else
                                  [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255])
                bits = int.from_bytes(blk[2:8], "little")
                alpha = [pal[(bits >> (3 * k)) & 7] for k in range(16)]
                blk = blk[8:]
            c0, c1, bits = struct.unpack("<HHI", blk)
            e0, e1 = _unpack565(c0), _unpack565(c1)
            if c0 > c1 or fmt == "dxt5":
                pal = [e0, e1, tuple((2 * a + b) // 3 for a, b in zip(e0, e1, strict=True)), tuple((a + 2 * b) // 3 for a, b in zip(e0, e1, strict=True))]
            else:
                pal = [e0, e1, tuple((a + b) // 2 for a, b in zip(e0, e1, strict=True)), (0, 0, 0)]
            for k in range(16):
                x, y = bx + k % 4, by + k // 4
                if x < width and y < height:
                    c = pal[(bits >> (2 * k)) & 3]
                    o = (y * width + x) * 4
                    out[o:o + 4] = bytes((c[0], c[1], c[2], alpha[k]))
    return bytes(out)
