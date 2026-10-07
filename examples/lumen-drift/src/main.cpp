// Lumen Drift: a small original arcade game used as ps-vita-porter's worked example.
//   lumen-drift              play
//   lumen-drift --selftest   run 2 minutes of scripted play without a window; prints the score and a state hash
#include <cstdio>
#include <cstring>

#include "game.h"
#include "platform/platform.h"
#include "render.h"

namespace {
int selftest() {
    Game g;
    g.persist = false;
    g.reset_run();
    g.screen = Screen::Playing;
    for (int t = 0; t < 7200 && g.screen == Screen::Playing; ++t) {
        platform::Input in;
        // steer toward the nearest spark, dash every 2 s
        if (!g.sparks.empty()) {
            float dx = g.sparks[0].x - g.px, dy = g.sparks[0].y - g.py;
            in.move_x = dx > 4 ? 1.f : dx < -4 ? -1.f : 0.f;
            in.move_y = dy > 4 ? 1.f : dy < -4 ? -1.f : 0.f;
        }
        in.dash = t % 120 == 0;
        g.step(in, 1.0f / 60);
    }
    std::printf("selftest: ticks %llu score %d lives %d hash %08x\n", (unsigned long long)g.tick, g.score, g.lives, g.hash());
    return g.score > 0 ? 0 : 1;
}
}  // namespace

int main(int argc, char** argv) {
    for (int i = 1; i < argc; ++i)
        if (!std::strcmp(argv[i], "--selftest")) return selftest();
    if (!platform::init()) return 1;
    Game g;
    load_settings(g);
    if (!render::init()) {
        platform::shutdown();
        return 1;
    }
    g.sfx_pickup = platform::load_sound("pickup.wav");
    g.sfx_hit = platform::load_sound("hit.wav");
    g.sfx_dash = platform::load_sound("dash.wav");
    g.sfx_select = platform::load_sound("select.wav");
    platform::log("lumen-drift: started");
    uint64_t last = platform::ticks_ms();
    double acc = 0;
    const double step = 1.0 / 60;
    platform::Input pending;   // one-shot inputs wait here until a logic step consumes them
    for (;;) {
        platform::Input in = platform::poll();
        if (in.quit || g.want_quit) break;
        pending.confirm |= in.confirm, pending.back |= in.back, pending.pause |= in.pause, pending.dash |= in.dash;
        pending.up |= in.up, pending.down |= in.down;
        if (in.tap) pending.tap = true, pending.tap_x = in.tap_x, pending.tap_y = in.tap_y;
        uint64_t now = platform::ticks_ms();
        acc += (now - last) / 1000.0;
        last = now;
        if (acc > 0.25) acc = 0.25;
        while (acc >= step) {   // fixed 60 Hz logic
            platform::Input s = pending;
            s.move_x = in.move_x, s.move_y = in.move_y, s.dash_held = in.dash_held;
            g.step(s, float(step));
            pending = platform::Input{};
            acc -= step;
        }
        render::frame(g);
        platform::present();
    }
    platform::log("lumen-drift: exit (score %d, best %d)", g.score, g.best);
    platform::shutdown();
    return 0;
}
