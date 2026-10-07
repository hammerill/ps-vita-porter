// PS Vita backend: vitaGL for OpenGL, the vitaport kit for controls/touch/paths/logging, SDL2 for audio only
// (never SDL's video subsystem, so it builds with either vdpm sdl2 flavour). See PORT_PLAN.md.
#include <psp2/kernel/processmgr.h>
#include <vitaGL.h>

#include <cstdarg>
#include <cstdio>

#include "audio.h"
#include "platform/platform.h"
#include "platform/vita_input.h"
#include "vitaport.h"

namespace platform {
namespace {
vita::State g_vs;
}

bool init() {
    vp_config cfg = vita::config();
    vp_init(&cfg);
    vglInit(0x80000);   // 512 KiB legacy pool for immediate-mode style draws; 960x544 framebuffer
    if (!audio::init()) log("audio: SDL audio failed (continuing without sound)");
    return true;
}

void shutdown() {
    audio::shutdown();
    // vitaGL has no shutdown call (checked r1448 and r1488): the process exit releases its memory blocks
    vp_shutdown();
}

Viewport viewport() {
    vp_rect r = vp_fit(kGameW, kGameH, VP_SCREEN_W, VP_SCREEN_H, VP_FIT_ASPECT);   // 4:3 pillarbox: 725x544 at x=117
    return Viewport{VP_SCREEN_W, VP_SCREEN_H, r.x, r.y, r.w, r.h};
}

Input poll() {
    vp_input vin;
    vp_poll(&vin);
    return vita::translate(vin, g_vs, viewport());
}

void present() {
    vp_frame();
    vglSwapBuffers(GL_FALSE);
}

uint64_t ticks_ms() { return sceKernelGetProcessTimeWide() / 1000; }

Prompts prompts() { return Prompts::Vita; }
int confirm_glyph() { return vita::glyph_of(vp_confirm_button()); }
int back_glyph() { return vita::glyph_of(vp_cancel_button()); }
int dash_binding_count() { return vita::kDashCount; }
const char* dash_binding_name(int i) { return vita::kDash[i].name; }
int dash_binding_glyph(int i) { return vita::kDash[i].glyph; }
void set_dash_binding(int i) { g_vs.dash = i; }
bool quit_supported() { return false; }   // Vita apps are closed from LiveArea (PORT_PLAN.md: quit)

std::vector<uint8_t> load_asset(const std::string& rel) {
    char buf[512];
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
    char buf[512];
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

int load_sound(const std::string& rel) { return audio::load_wav(load_asset(rel)); }
void play_sound(int id) { audio::play(id); }

}  // namespace platform
