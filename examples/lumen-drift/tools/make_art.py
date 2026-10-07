#!/usr/bin/env python3
"""Draw every asset of Lumen Drift from code: no third-party art, no dependencies (Python 3.10+).

    python tools/make_art.py            # writes assets/ (what the game loads) and art/ (sources for LiveArea)

assets/atlas.tga     256x256 RGBA: a 5x7 pixel font, the orb, spark and shard sprites, and original button glyphs
                     (cross, circle, square, triangle, L, R, START, SELECT) drawn here, not Sony's artwork, and an
                     opaque white 8x8 block at (248, 248) for solid quads
assets/*.wav         sound effects, 44.1 kHz stereo 16-bit (the PC originals; `vita assets convert` makes 22.05 kHz mono)
art/keyart.png       1280x720 key art (pic0 and bg0 sources)
art/icon.png         256x256 icon (icon0)
art/logo.png         560x316 logo with transparency (startup)

The layout (cell positions) is mirrored in src/atlas.h. Deterministic: same bytes every run.
"""
from __future__ import annotations

import math
import random
import struct
import wave
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FONT = {
    " ": ["     "] * 7,
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "J": ["  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "## ##", "#   #"],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#### ", "    #", "    #", " ### ", "    #", "    #", "#### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": [" ### ", "#    ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "    #", " ### "],
    ".": ["     ", "     ", "     ", "     ", "     ", " ##  ", " ##  "],
    ",": ["     ", "     ", "     ", "     ", " ##  ", "  #  ", " #   "],
    ":": ["     ", " ##  ", " ##  ", "     ", " ##  ", " ##  ", "     "],
    "!": ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
    "?": [" ### ", "#   #", "    #", "   # ", "  #  ", "     ", "  #  "],
    "-": ["     ", "     ", "     ", "#####", "     ", "     ", "     "],
    "+": ["     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "],
    "/": ["    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "],
    "'": ["  #  ", "  #  ", " #   ", "     ", "     ", "     ", "     "],
    "(": ["   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "],
    ")": [" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "],
    "<": ["    #", "   # ", "  #  ", " #   ", "  #  ", "   # ", "    #"],
    ">": ["#    ", " #   ", "  #  ", "   # ", "  #  ", " #   ", "#    "],
    "=": ["     ", "     ", "#####", "     ", "#####", "     ", "     "],
    "%": ["##   ", "##  #", "   # ", "  #  ", " #   ", "#  ##", "   ##"],
}
FONT_ORDER = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:!?-+/'()<>=%"
CELL = 8           # font cell 8x8 (5x7 glyph + spacing), 32 per row
SPRITES = {"orb": (0, 64, 32), "spark": (32, 64, 16), "shard": (48, 64, 32), "ring": (80, 64, 32)}
GLYPHS = ["cross", "circle", "square", "triangle", "l", "r", "start", "select"]   # 32x32 each at y=128


class Img:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)

    def blend(self, x: int, y: int, r: int, g: int, b: int, a: float):
        if 0 <= x < self.w and 0 <= y < self.h and a > 0:
            o = (y * self.w + x) * 4
            a = min(1.0, a)
            da = self.px[o + 3] / 255
            oa = a + da * (1 - a)
            for i, c in enumerate((r, g, b)):
                self.px[o + i] = int((c * a + self.px[o + i] * da * (1 - a)) / oa) if oa else 0
            self.px[o + 3] = int(oa * 255)

    def fill(self, r, g, b, a=255):
        for i in range(self.w * self.h):
            self.px[i * 4:i * 4 + 4] = bytes((r, g, b, a))

    def disc(self, cx, cy, rad, col, soft=1.0, alpha=1.0):
        for y in range(int(cy - rad - 2), int(cy + rad + 3)):
            for x in range(int(cx - rad - 2), int(cx + rad + 3)):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                self.blend(x, y, *col, alpha * max(0.0, min(1.0, (rad - d) / soft + 0.5)))

    def glow(self, cx, cy, rad, col, power=2.0):
        for y in range(int(cy - rad), int(cy + rad) + 1):
            for x in range(int(cx - rad), int(cx + rad) + 1):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy) / rad
                if d < 1:
                    self.blend(x, y, *col, (1 - d) ** power)

    def line(self, x0, y0, x1, y1, width, col, alpha=1.0):
        minx, maxx = int(min(x0, x1) - width - 1), int(max(x0, x1) + width + 2)
        miny, maxy = int(min(y0, y1) - width - 1), int(max(y0, y1) + width + 2)
        dx, dy = x1 - x0, y1 - y0
        ll = dx * dx + dy * dy or 1
        for y in range(miny, maxy):
            for x in range(minx, maxx):
                px, py = x + 0.5, y + 0.5
                t = max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / ll))
                d = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
                self.blend(x, y, *col, alpha * max(0.0, min(1.0, width / 2 - d + 0.5)))

    def ring(self, cx, cy, rad, width, col):
        for y in range(int(cy - rad - width), int(cy + rad + width) + 1):
            for x in range(int(cx - rad - width), int(cx + rad + width) + 1):
                d = abs(math.hypot(x + 0.5 - cx, y + 0.5 - cy) - rad)
                self.blend(x, y, *col, max(0.0, min(1.0, width / 2 - d + 0.5)))

    def text(self, s, x, y, scale, col, alpha=1.0):
        for i, ch in enumerate(s.upper()):
            rows = FONT.get(ch, FONT["?"])
            for gy, row in enumerate(rows):
                for gx, c in enumerate(row):
                    if c == "#":
                        for sy in range(scale):
                            for sx in range(scale):
                                self.blend(x + (i * 6 + gx) * scale + sx, y + gy * scale + sy, *col, alpha)

    def tga(self, path: Path):
        head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, self.w, self.h, 32, 0x28)   # top-left origin, 8 alpha bits
        body = bytearray()
        for i in range(self.w * self.h):
            r, g, b, a = self.px[i * 4:i * 4 + 4]
            body += bytes((b, g, r, a))
        path.write_bytes(head + bytes(body))

    def png(self, path: Path, alpha: bool):
        ch = 4 if alpha else 3
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)
            for x in range(self.w):
                o = (y * self.w + x) * 4
                raw += self.px[o:o + ch]

        def chunk(t, b):
            return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6 if alpha else 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
        path.write_bytes(data)


CYAN, GOLD, ROSE, WHITE = (120, 230, 255), (255, 214, 102), (255, 92, 138), (255, 255, 255)


def draw_glyph(img: Img, name: str, x0: int, y0: int):
    cx, cy = x0 + 16, y0 + 16
    img.disc(cx, cy, 14.5, (40, 44, 60))
    img.ring(cx, cy, 14, 1.5, (200, 205, 220))
    if name == "cross":
        img.line(cx - 6, cy - 6, cx + 6, cy + 6, 3, (140, 180, 255))
        img.line(cx - 6, cy + 6, cx + 6, cy - 6, 3, (140, 180, 255))
    elif name == "circle":
        img.ring(cx, cy, 6.5, 3, (255, 120, 130))
    elif name == "square":
        for a, b, c, d in ((-6, -6, 6, -6), (6, -6, 6, 6), (6, 6, -6, 6), (-6, 6, -6, -6)):
            img.line(cx + a, cy + b, cx + c, cy + d, 3, (240, 150, 220))
    elif name == "triangle":
        pts = [(cx, cy - 8), (cx + 7, cy + 5), (cx - 7, cy + 5)]
        for i in range(3):
            img.line(*pts[i], *pts[(i + 1) % 3], 3, (110, 230, 190))
    else:
        label = {"l": "L", "r": "R", "start": "ST", "select": "SE"}[name]
        img.text(label, cx - len(label) * 3 * 2 + 1, cy - 7, 2, WHITE)


def atlas() -> Img:
    img = Img(256, 256)
    for i, ch in enumerate(FONT_ORDER):
        x0, y0 = (i % 32) * CELL, (i // 32) * CELL
        for gy, row in enumerate(FONT[ch]):
            for gx, c in enumerate(row):
                if c == "#":
                    img.blend(x0 + gx, y0 + gy, *WHITE, 1)
    x, y, s = SPRITES["orb"]
    img.glow(x + s / 2, y + s / 2, s / 2, CYAN, 1.6)
    img.disc(x + s / 2, y + s / 2, 7, WHITE)
    x, y, s = SPRITES["spark"]
    c = s / 2
    img.line(x + c, y + 1, x + c, y + s - 1, 2, GOLD)
    img.line(x + 1, y + c, x + s - 1, y + c, 2, GOLD)
    img.glow(x + c, y + c, c, GOLD, 1.2)
    x, y, s = SPRITES["shard"]
    pts = [(x + 16, y + 2), (x + 28, y + 16), (x + 16, y + 30), (x + 4, y + 16)]
    for yy in range(y, y + s):
        for xx in range(x, x + s):
            u = abs(xx + 0.5 - (x + 16)) / 12 + abs(yy + 0.5 - (y + 16)) / 14
            if u <= 1:
                img.blend(xx, yy, *ROSE, 0.55 + 0.45 * (1 - u))
    for i in range(4):
        img.line(*pts[i], *pts[(i + 1) % 4], 1.5, (255, 200, 220))
    x, y, s = SPRITES["ring"]
    img.ring(x + 16, y + 16, 13, 2, WHITE)
    for i, g in enumerate(GLYPHS):
        draw_glyph(img, g, i * 32, 128)
    for y in range(248, 256):          # an opaque white block for solid quads (background, bars, dimming)
        for x in range(248, 256):
            img.blend(x, y, *WHITE, 1)
    return img


def keyart(w=1280, h=720) -> Img:
    img = Img(w, h)
    for y in range(h):
        t = y / h
        col = (int(14 + 20 * t), int(10 + 14 * t), int(40 + 40 * t))
        for x in range(w):
            o = (y * w + x) * 4
            img.px[o:o + 4] = bytes((*col, 255))
    rnd = random.Random(7)
    for _ in range(140):
        img.disc(rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(0.6, 1.8), WHITE, alpha=rnd.uniform(0.3, 0.9))
    for _ in range(9):
        sx, sy = rnd.uniform(0, w), rnd.uniform(0, h)
        img.glow(sx, sy, 34, ROSE, 2.5)
    for _ in range(14):
        img.glow(rnd.uniform(0, w), rnd.uniform(0, h), 18, GOLD, 2.0)
    img.glow(w * 0.68, h * 0.62, 150, CYAN, 1.8)
    img.disc(w * 0.68, h * 0.62, 34, WHITE)
    title = "LUMEN DRIFT"
    sc = 12
    tw = len(title) * 6 * sc
    img.text(title, (w - tw) // 2 + 4, int(h * 0.16) + 4, sc, (0, 0, 0), 0.5)
    img.text(title, (w - tw) // 2, int(h * 0.16), sc, (235, 245, 255))
    return img


def icon() -> Img:
    img = Img(256, 256)
    img.fill(18, 16, 48)
    img.glow(128, 128, 120, CYAN, 1.7)
    img.disc(128, 128, 40, WHITE)
    img.glow(196, 66, 30, GOLD, 1.5)
    img.glow(58, 196, 34, ROSE, 1.8)
    return img


def logo() -> Img:
    img = Img(560, 316)
    for i, word in enumerate(("LUMEN", "DRIFT")):
        sc = 10
        tw = len(word) * 6 * sc
        img.text(word, (560 - tw) // 2 + 3, 40 + i * 120 + 3, sc, (0, 0, 0), 0.6)
        img.text(word, (560 - tw) // 2, 40 + i * 120, sc, (235, 245, 255))
    img.glow(470, 60, 40, CYAN, 1.6)
    return img


def sfx(path: Path, seconds: float, fn):
    rate = 44100
    n = int(rate * seconds)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = min(1.0, t / 0.005) * max(0.0, 1 - t / seconds) ** 1.5
        v = max(-1.0, min(1.0, fn(t) * env))
        s = int(v * 28000)
        frames += struct.pack("<hh", s, s)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def main():
    (ROOT / "assets").mkdir(exist_ok=True)
    (ROOT / "art").mkdir(exist_ok=True)
    atlas().tga(ROOT / "assets" / "atlas.tga")
    rnd = random.Random(3)
    noise = [rnd.uniform(-1, 1) for _ in range(44100)]
    sfx(ROOT / "assets" / "pickup.wav", 0.18, lambda t: math.sin(2 * math.pi * (880 + 2400 * t) * t))
    sfx(ROOT / "assets" / "hit.wav", 0.35, lambda t: 0.7 * noise[int(t * 44100) % 44100] + 0.4 * math.sin(2 * math.pi * 90 * t))
    sfx(ROOT / "assets" / "dash.wav", 0.22, lambda t: 0.5 * noise[int(t * 22050) % 44100] * math.sin(2 * math.pi * 30 * t))
    sfx(ROOT / "assets" / "select.wav", 0.08, lambda t: math.sin(2 * math.pi * 660 * t) * (1 if t < 0.04 else 0.6))
    keyart().png(ROOT / "art" / "keyart.png", alpha=False)
    icon().png(ROOT / "art" / "icon.png", alpha=False)
    logo().png(ROOT / "art" / "logo.png", alpha=True)
    print("wrote assets/atlas.tga, assets/*.wav, art/keyart.png, art/icon.png, art/logo.png")


if __name__ == "__main__":
    main()
