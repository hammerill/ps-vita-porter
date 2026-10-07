// Drawing for Lumen Drift: fixed-function OpenGL with client vertex arrays, one texture atlas.
// The same code runs on desktop GL (PC) and on vitaGL (Vita), which implements this subset.
#pragma once
#include "game.h"

namespace render {
bool init();                 // loads assets/atlas.tga
void frame(const Game& g);   // clears the framebuffer, draws the game in platform::viewport()
void read_pixels(int w, int h, unsigned char* rgba);   // last frame, top row first (simulation screenshots)
}  // namespace render
