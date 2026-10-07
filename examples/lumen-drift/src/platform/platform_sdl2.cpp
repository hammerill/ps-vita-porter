// PC backend: SDL2 window + OpenGL. With VITA_SIM it becomes the PC "Vita simulation" profile: a 960x544 window,
// input read through vitaport (Vita layout on keyboard/gamepad/mouse), Vita paths, the memory cap, screenshots.
#include <SDL.h>

#include <cstdarg>
#include <cstdio>
#include <cstdlib>

#include "audio.h"
#include "gl.h"
#include "platform/platform.h"
#include "render.h"
#ifdef VITA_SIM
#include "platform/vita_input.h"
#include "vitaport.h"
#endif

namespace platform {
namespace {
SDL_Window* g_win;
SDL_GLContext g_ctx;
SDL_GameController* g_pad;
int g_dash;
#ifdef VITA_SIM
vita::State g_vs;
void readback(int w, int h, uint8_t* rgba) { render::read_pixels(w, h, rgba); }
#else
struct Key { const char* name; SDL_Scancode sc; };
constexpr Key kDashKeys[] = {{"SPACE", SDL_SCANCODE_SPACE}, {"SHIFT", SDL_SCANCODE_LSHIFT}, {"X", SDL_SCANCODE_X}, {"J", SDL_SCANCODE_J}};
#endif
}  // namespace

bool init() {
#ifdef VITA_SIM
    int w = 960, h = 544;
#else
    int w = kGameW, h = kGameH;
#endif
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_EVENTS | SDL_INIT_GAMECONTROLLER) != 0) {
        std::fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
        return false;
    }
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 2);
    SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION, 1);
    SDL_GL_SetAttribute(SDL_GL_DOUBLEBUFFER, 1);
    g_win = SDL_CreateWindow(
#ifdef VITA_SIM
        "Lumen Drift (Vita simulation)",
#else
        "Lumen Drift",
#endif
        SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED, w, h, SDL_WINDOW_OPENGL);
    if (!g_win || !(g_ctx = SDL_GL_CreateContext(g_win))) {
        std::fprintf(stderr, "window/GL context: %s\n", SDL_GetError());
        return false;
    }
    SDL_GL_SetSwapInterval(1);
#ifdef VITA_SIM
    vp_config cfg = vita::config();
    vp_init(&cfg);
    vp_set_readback(readback, 960, 544);
#else
    for (int i = 0; i < SDL_NumJoysticks() && !g_pad; ++i)
        if (SDL_IsGameController(i)) g_pad = SDL_GameControllerOpen(i);
#endif
    if (!audio::init()) log("audio: %s (continuing without sound)", SDL_GetError());
    return true;
}

void shutdown() {
    audio::shutdown();
#ifdef VITA_SIM
    vp_shutdown();
#endif
    if (g_pad) SDL_GameControllerClose(g_pad);
    if (g_ctx) SDL_GL_DeleteContext(g_ctx);
    if (g_win) SDL_DestroyWindow(g_win);
    SDL_Quit();
}

Viewport viewport() {
    int fw = 0, fh = 0;
    SDL_GL_GetDrawableSize(g_win, &fw, &fh);
    // keep 4:3, pillarbox (PORT_PLAN.md: resolution and scaling)
    int w = fh * kGameW / kGameH, h = fh;
    if (w > fw) w = fw, h = fw * kGameH / kGameW;
    return Viewport{fw, fh, (fw - w) / 2, (fh - h) / 2, w, h};
}

Input poll() {
    Input in;
    SDL_Event e;
#ifndef VITA_SIM
    const Uint8* k = SDL_GetKeyboardState(nullptr);
#endif
    while (SDL_PollEvent(&e)) {
        if (e.type == SDL_QUIT) in.quit = true;
#ifndef VITA_SIM
        if (e.type == SDL_KEYDOWN && !e.key.repeat) {
            SDL_Scancode sc = e.key.keysym.scancode;
            if (sc == SDL_SCANCODE_UP || sc == SDL_SCANCODE_W) in.up = true;
            if (sc == SDL_SCANCODE_DOWN || sc == SDL_SCANCODE_S) in.down = true;
            if (sc == SDL_SCANCODE_RETURN || sc == SDL_SCANCODE_KP_ENTER) in.confirm = true;
            if (sc == SDL_SCANCODE_ESCAPE || sc == SDL_SCANCODE_BACKSPACE) in.back = true;
            if (sc == SDL_SCANCODE_ESCAPE || sc == SDL_SCANCODE_P) in.pause = true;
            if (sc == kDashKeys[g_dash].sc) in.dash = true;
        }
        if (e.type == SDL_MOUSEBUTTONDOWN && e.button.button == SDL_BUTTON_LEFT) {
            Viewport v = viewport();
            int ww, wh;
            SDL_GetWindowSize(g_win, &ww, &wh);
            float sx = e.button.x * float(v.fb_w) / ww, sy = e.button.y * float(v.fb_h) / wh;
            in.tap = true, in.tap_x = (sx - v.x) * kGameW / v.w, in.tap_y = (sy - v.y) * kGameH / v.h;
        }
        if (e.type == SDL_CONTROLLERBUTTONDOWN) {
            auto b = e.cbutton.button;
            if (b == SDL_CONTROLLER_BUTTON_A) in.confirm = true;
            if (b == SDL_CONTROLLER_BUTTON_B) in.back = true;
            if (b == SDL_CONTROLLER_BUTTON_X) in.dash = true;
            if (b == SDL_CONTROLLER_BUTTON_START) in.pause = true;
            if (b == SDL_CONTROLLER_BUTTON_DPAD_UP) in.up = true;
            if (b == SDL_CONTROLLER_BUTTON_DPAD_DOWN) in.down = true;
        }
#endif
    }
#ifdef VITA_SIM
    vp_input vin;
    vp_poll(&vin);
    Input v = vita::translate(vin, g_vs, viewport());
    v.quit = in.quit || vp_should_quit();
    return v;
#else
    float mx = float(k[SDL_SCANCODE_D] || k[SDL_SCANCODE_RIGHT]) - float(k[SDL_SCANCODE_A] || k[SDL_SCANCODE_LEFT]);
    float my = float(k[SDL_SCANCODE_S] || k[SDL_SCANCODE_DOWN]) - float(k[SDL_SCANCODE_W] || k[SDL_SCANCODE_UP]);
    if (g_pad) {
        float ax = SDL_GameControllerGetAxis(g_pad, SDL_CONTROLLER_AXIS_LEFTX) / 32767.0f;
        float ay = SDL_GameControllerGetAxis(g_pad, SDL_CONTROLLER_AXIS_LEFTY) / 32767.0f;
        if (ax * ax + ay * ay > 0.04f) mx = ax, my = ay;
    }
    in.move_x = mx, in.move_y = my;
    in.dash_held = k[kDashKeys[g_dash].sc];
    return in;
#endif
}

void present() {
#ifdef VITA_SIM
    vp_frame();
#endif
    SDL_GL_SwapWindow(g_win);
}

uint64_t ticks_ms() { return SDL_GetTicks64(); }

#ifdef VITA_SIM
Prompts prompts() { return Prompts::Vita; }
int confirm_glyph() { return vita::glyph_of(vp_confirm_button()); }
int back_glyph() { return vita::glyph_of(vp_cancel_button()); }
int dash_binding_count() { return vita::kDashCount; }
const char* dash_binding_name(int i) { return vita::kDash[i].name; }
int dash_binding_glyph(int i) { return vita::kDash[i].glyph; }
void set_dash_binding(int i) { g_dash = g_vs.dash = i; }
bool quit_supported() { return false; }
std::vector<uint8_t> load_asset(const std::string& rel) {
    char buf[1024];
    vp_asset_path(rel.c_str(), buf, sizeof buf);
    std::vector<uint8_t> d;
    if (FILE* f = std::fopen(buf, "rb")) {
        std::fseek(f, 0, SEEK_END);
        d.resize(size_t(std::ftell(f)));
        std::fseek(f, 0, SEEK_SET);
        if (std::fread(d.data(), 1, d.size(), f) != d.size()) d.clear();
        std::fclose(f);
    } else {
        log("missing asset %s", buf);
    }
    return d;
}
std::string save_path(const std::string& rel) {
    char buf[1024];
    return vp_save_path(rel.c_str(), buf, sizeof buf);
}
void log(const char* fmt, ...) {
    char msg[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    vp_log("%s", msg);
}
#else
Prompts prompts() { return Prompts::Keyboard; }
int confirm_glyph() { return -1; }
int back_glyph() { return -1; }
int dash_binding_count() { return int(sizeof kDashKeys / sizeof kDashKeys[0]); }
const char* dash_binding_name(int i) { return kDashKeys[i].name; }
int dash_binding_glyph(int) { return -1; }
void set_dash_binding(int i) { g_dash = i; }
bool quit_supported() { return true; }
std::vector<uint8_t> load_asset(const std::string& rel) {
    const char* base = std::getenv("LUMEN_DATA");
    std::string p = std::string(base && *base ? base : "assets") + "/" + rel;
    std::vector<uint8_t> d;
    if (FILE* f = std::fopen(p.c_str(), "rb")) {
        std::fseek(f, 0, SEEK_END);
        d.resize(size_t(std::ftell(f)));
        std::fseek(f, 0, SEEK_SET);
        if (std::fread(d.data(), 1, d.size(), f) != d.size()) d.clear();
        std::fclose(f);
    } else {
        log("missing asset %s", p.c_str());
    }
    return d;
}
std::string save_path(const std::string& rel) {
    char* pref = SDL_GetPrefPath("hammerill", "LumenDrift");
    std::string p = std::string(pref ? pref : "./") + rel;
    SDL_free(pref);
    return p;
}
void log(const char* fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    std::vfprintf(stderr, fmt, ap);
    va_end(ap);
    std::fputc('\n', stderr);
}
#endif

int load_sound(const std::string& rel) { return audio::load_wav(load_asset(rel)); }
void play_sound(int id) { audio::play(id); }

}  // namespace platform
