#include "game.h"

#include <cmath>
#include <cstdio>
#include <cstring>

namespace {
constexpr float kAccel = 1400, kMaxSpeed = 260, kDrag = 4.0f, kDashSpeed = 620, kDashTime = 0.18f, kDashCooldown = 0.9f;
constexpr float kOrbR = 11, kSparkR = 7, kShardR = 11;

bool hit(float ax, float ay, float ar, const Entity& e) {
    float dx = ax - e.x, dy = ay - e.y;
    return dx * dx + dy * dy < (ar + e.r) * (ar + e.r);
}
}  // namespace

uint32_t Game::rand() {
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
}

float Game::frand(float lo, float hi) { return lo + (hi - lo) * float(rand() % 10000) / 10000.0f; }

void Game::reset_run() {
    px = 320, py = 240, pvx = pvy = 0;
    dash_time = dash_cooldown = invuln = 0;
    lives = 3, score = 0;
    sparks.clear(), shards.clear();
    spawn_timer = 0;
    for (int i = 0; i < 3; ++i) sparks.push_back({frand(40, 600), frand(60, 440), 0, 0, kSparkR, true});
}

std::vector<std::string> Game::menu_items() const {
    switch (screen) {
        case Screen::Title:
            if (platform::quit_supported()) return {"START", "CONTROLS", "QUIT"};
            return {"START", "CONTROLS"};
        case Screen::Paused: return {"RESUME", "CONTROLS", "QUIT TO TITLE"};
        case Screen::Controls: return {"DASH", "BACK"};
        case Screen::GameOver: return {"PLAY AGAIN", "TITLE"};
        default: return {};
    }
}

void Game::activate(int item) {
    if (sfx_select >= 0) platform::play_sound(sfx_select);
    switch (screen) {
        case Screen::Title:
            if (item == 0) { reset_run(); screen = Screen::Playing; }
            else if (item == 1) { controls_return = Screen::Title; screen = Screen::Controls; menu = 0; }
            else want_quit = true;
            break;
        case Screen::Paused:
            if (item == 0) screen = Screen::Playing;
            else if (item == 1) { controls_return = Screen::Paused; screen = Screen::Controls; menu = 0; }
            else { screen = Screen::Title; menu = 0; }
            break;
        case Screen::Controls:
            if (item == 0) {
                dash_binding = (dash_binding + 1) % platform::dash_binding_count();
                platform::set_dash_binding(dash_binding);
                save_settings(*this);
            } else { screen = controls_return; menu = 0; }
            break;
        case Screen::GameOver:
            if (item == 0) { reset_run(); screen = Screen::Playing; }
            else { screen = Screen::Title; menu = 0; }
            break;
        default: break;
    }
}

void Game::step(const platform::Input& in, float dt) {
    ++tick;
    if (screen != Screen::Playing) {
        auto items = menu_items();
        int n = int(items.size());
        if (in.up) menu = (menu + n - 1) % n;
        if (in.down) menu = (menu + 1) % n;
        if (in.tap) {   // menu items are laid out by render.cpp: centred rows from y=250, 36 px apart
            int row = int((in.tap_y - 238) / 36);
            if (row >= 0 && row < n && std::fabs(in.tap_x - 320) < 170) { menu = row; activate(row); return; }
        }
        if (in.confirm) { activate(menu); return; }
        if (in.back || (in.pause && screen == Screen::Paused)) {
            if (screen == Screen::Paused) screen = Screen::Playing;
            else if (screen == Screen::Controls) { screen = controls_return; menu = 0; }
        }
        return;
    }
    if (in.pause) { screen = Screen::Paused; menu = 0; return; }
    // movement: acceleration + drag, dash burst in the stick direction
    float mx = in.move_x, my = in.move_y;
    float len = std::sqrt(mx * mx + my * my);
    if (len > 1) mx /= len, my /= len, len = 1;
    pvx += mx * kAccel * dt, pvy += my * kAccel * dt;
    pvx -= pvx * kDrag * dt, pvy -= pvy * kDrag * dt;
    float sp = std::sqrt(pvx * pvx + pvy * pvy);
    float cap = dash_time > 0 ? kDashSpeed : kMaxSpeed;
    if (sp > cap) pvx *= cap / sp, pvy *= cap / sp;
    if (in.dash && dash_cooldown <= 0 && len > 0.2f) {
        pvx = mx / len * kDashSpeed, pvy = my / len * kDashSpeed;
        dash_time = kDashTime, dash_cooldown = kDashCooldown;
        if (sfx_dash >= 0) platform::play_sound(sfx_dash);
    }
    dash_time -= dt, dash_cooldown -= dt, invuln -= dt;
    px += pvx * dt, py += pvy * dt;
    if (px < kOrbR) px = kOrbR, pvx = -pvx * 0.5f;
    if (px > 640 - kOrbR) px = 640 - kOrbR, pvx = -pvx * 0.5f;
    if (py < 40 + kOrbR) py = 40 + kOrbR, pvy = -pvy * 0.5f;
    if (py > 480 - kOrbR) py = 480 - kOrbR, pvy = -pvy * 0.5f;
    // shards drift in from the edges, faster as the score grows
    spawn_timer -= dt;
    if (spawn_timer <= 0) {
        float speed = 70 + score * 4.0f;
        int side = int(rand() % 4);
        Entity e{0, 0, 0, 0, kShardR, true};
        if (side == 0) e.x = -20, e.y = frand(60, 460);
        if (side == 1) e.x = 660, e.y = frand(60, 460);
        if (side == 2) e.x = frand(20, 620), e.y = 20;
        if (side == 3) e.x = frand(20, 620), e.y = 500;
        float tx = frand(120, 520) - e.x, ty = frand(120, 400) - e.y, tl = std::sqrt(tx * tx + ty * ty);
        e.vx = tx / tl * speed, e.vy = ty / tl * speed;
        shards.push_back(e);
        spawn_timer = std::fmax(0.35f, 1.4f - score * 0.03f);
    }
    for (auto& s : shards) {
        s.x += s.vx * dt, s.y += s.vy * dt;
        if (s.x < -60 || s.x > 700 || s.y < -40 || s.y > 540) s.alive = false;
        if (s.alive && invuln <= 0 && dash_time <= 0 && hit(px, py, kOrbR, s)) {
            s.alive = false;
            --lives;
            invuln = 1.5f;
            if (sfx_hit >= 0) platform::play_sound(sfx_hit);
        }
    }
    for (auto& s : sparks)
        if (s.alive && hit(px, py, kOrbR + 4, s)) {
            s.alive = false;
            ++score;
            if (sfx_pickup >= 0) platform::play_sound(sfx_pickup);
        }
    std::erase_if(shards, [](const Entity& e) { return !e.alive; });
    std::erase_if(sparks, [](const Entity& e) { return !e.alive; });
    while (sparks.size() < 3) sparks.push_back({frand(40, 600), frand(70, 440), 0, 0, kSparkR, true});
    if (lives <= 0) {
        if (score > best) { best = score; save_settings(*this); }
        screen = Screen::GameOver;
        menu = 0;
    }
}

uint32_t Game::hash() const {
    uint32_t h = 2166136261u;
    auto mix = [&h](const void* p, size_t n) {
        auto b = static_cast<const unsigned char*>(p);
        for (size_t i = 0; i < n; ++i) h = (h ^ b[i]) * 16777619u;
    };
    int ix = int(px), iy = int(py);
    mix(&ix, sizeof ix), mix(&iy, sizeof iy), mix(&score, sizeof score), mix(&lives, sizeof lives), mix(&rng, sizeof rng);
    return h;
}

void load_settings(Game& g) {
    std::string p = platform::save_path("settings.txt");
    if (FILE* f = std::fopen(p.c_str(), "r")) {
        char key[32];
        int v;
        while (std::fscanf(f, "%31[^=]=%d\n", key, &v) == 2) {
            if (!std::strcmp(key, "best")) g.best = v;
            if (!std::strcmp(key, "dash") && v >= 0 && v < platform::dash_binding_count()) g.dash_binding = v;
        }
        std::fclose(f);
    }
    platform::set_dash_binding(g.dash_binding);
}

void save_settings(const Game& g) {
    if (!g.persist) return;
    std::string p = platform::save_path("settings.txt");
    if (FILE* f = std::fopen(p.c_str(), "w")) {
        std::fprintf(f, "best=%d\ndash=%d\n", g.best, g.dash_binding);
        std::fclose(f);
    }
}
