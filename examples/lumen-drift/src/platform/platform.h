// Lumen Drift's platform layer: everything the game needs from the OS goes through here.
// Backends: platform_sdl2.cpp (PC; with -DVITA_SIM=ON it becomes the PC "Vita simulation" profile) and
// platform_vita.cpp (PS Vita: vitaGL + the vitaport kit + SDL2 audio). Game code never calls SDL, GL setup or Sce* directly.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace platform {

constexpr int kGameW = 640, kGameH = 480;      // the game's own resolution (4:3)

struct Input {
    float move_x = 0, move_y = 0;              // -1..1
    bool up = false, down = false, left = false, right = false;   // menu navigation edges
    bool confirm = false, back = false, pause = false, dash = false;   // edges
    bool dash_held = false;
    bool tap = false;                          // a click / front-touch tap this frame
    float tap_x = 0, tap_y = 0;                // in game coordinates (640x480)
    bool quit = false;                         // window closed (PC) / scripted quit (sim)
};

enum class Prompts { Keyboard, Vita };

struct Viewport { int fb_w, fb_h, x, y, w, h; };   // framebuffer size and the game's rect inside it (top-left origin)

bool init();
void shutdown();
Input poll();
Viewport viewport();
void present();
uint64_t ticks_ms();

// prompts: which glyph set to draw, and the glyph/key name for each action
Prompts prompts();
int confirm_glyph();                           // atlas::Glyph (Vita) - follows the system's confirm-button setting
int back_glyph();
// the remappable Dash binding
int dash_binding_count();
const char* dash_binding_name(int i);
int dash_binding_glyph(int i);                 // atlas::Glyph or -1
void set_dash_binding(int i);
bool quit_supported();                         // false on the Vita: apps are closed from LiveArea (PORT_PLAN.md)

// files
std::vector<uint8_t> load_asset(const std::string& rel);
std::string save_path(const std::string& rel);
void log(const char* fmt, ...);

// audio: play a loaded sound
int load_sound(const std::string& rel);
void play_sound(int id);

}  // namespace platform
