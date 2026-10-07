// Vita controls -> the game's actions. Shared by the Vita backend and the PC simulation profile, so `vita sim`
// exercises exactly the mapping the console runs (PORT_PLAN.md, Controls).
#pragma once
#include <cmath>
#include <cstdint>

#include "atlas.h"
#include "platform/platform.h"
#include "vitaport.h"

namespace platform::vita {

struct Binding { const char* name; uint32_t mask; int glyph; };
constexpr Binding kDash[] = {{"SQUARE", VP_SQUARE, atlas::kSquare}, {"R", VP_R, atlas::kR}, {"L", VP_L, atlas::kL},
                             {"TRIANGLE", VP_TRIANGLE, atlas::kTriangle}, {"CROSS", VP_CROSS, atlas::kCross}, {"CIRCLE", VP_CIRCLE, atlas::kCircle}};
constexpr int kDashCount = int(sizeof kDash / sizeof kDash[0]);

inline int glyph_of(uint32_t mask) { return mask == VP_CIRCLE ? atlas::kCircle : atlas::kCross; }

struct State { int dash = 0; bool stick_up = false, stick_down = false, touching = false; };

inline Input translate(const vp_input& in, State& st, const Viewport& vp) {
    Input o;
    float lx = (in.lx - 128) / 127.0f, ly = (in.ly - 128) / 127.0f;
    if (std::fabs(lx) < 0.2f) lx = 0;   // dead zone
    if (std::fabs(ly) < 0.2f) ly = 0;
    if (in.buttons & VP_LEFT) lx = -1;
    if (in.buttons & VP_RIGHT) lx = 1;
    if (in.buttons & VP_UP) ly = -1;
    if (in.buttons & VP_DOWN) ly = 1;
    o.move_x = lx, o.move_y = ly;
    bool su = ly < -0.6f, sd = ly > 0.6f;
    o.up = (in.pressed & VP_UP) || (su && !st.stick_up);
    o.down = (in.pressed & VP_DOWN) || (sd && !st.stick_down);
    st.stick_up = su, st.stick_down = sd;
    o.confirm = in.pressed & vp_confirm_button();
    o.back = in.pressed & vp_cancel_button();
    o.pause = in.pressed & VP_START;
    o.dash = in.pressed & kDash[st.dash].mask;
    o.dash_held = in.buttons & kDash[st.dash].mask;
    // front touch: a new touch is a tap, mapped from the screen into the game's 640x480 rect (menus only, rear and gyro off)
    if (in.front_count > 0 && !st.touching) {
        float sx = in.front[0].x * VP_SCREEN_W, sy = in.front[0].y * VP_SCREEN_H;
        o.tap = true;
        o.tap_x = (sx - vp.x) * kGameW / vp.w;
        o.tap_y = (sy - vp.y) * kGameH / vp.h;
    }
    st.touching = in.front_count > 0;
    return o;
}

inline vp_config config() {
    vp_config c{};
    c.data_folder = VP_DATA_FOLDER;
    c.assets_dir = VP_ASSETS_DIR;
    c.assets_external = VP_ASSETS_EXTERNAL;
    c.enable_front_touch = 1;   // menus only
    c.enable_rear_touch = 0;    // off (intake)
    c.enable_motion = 0;        // off (intake)
    return c;
}

}  // namespace platform::vita
