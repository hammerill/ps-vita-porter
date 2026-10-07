// Layout of assets/atlas.tga (drawn by tools/make_art.py; keep both in sync).
#pragma once

namespace atlas {
constexpr int kSize = 256;
constexpr int kCell = 8;                       // font cells, 32 per row, 5x7 glyphs
constexpr const char* kFontOrder = " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:!?-+/'()<>=%";
struct Sprite { int x, y, size; };
constexpr Sprite kOrb{0, 64, 32}, kSpark{32, 64, 16}, kShard{48, 64, 32}, kRing{80, 64, 32};
enum Glyph { kCross, kCircle, kSquare, kTriangle, kL, kR, kStart, kSelect, kGlyphCount };
constexpr int kGlyphY = 128, kGlyphSize = 32;
constexpr int kSolidX = 250, kSolidY = 250;   // inside the opaque white block at (248, 248)
}  // namespace atlas
