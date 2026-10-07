// Lumen Drift game logic: deterministic, no rendering or OS calls (those go through platform::).
#pragma once
#include <cstdint>
#include <string>
#include <vector>

#include "platform/platform.h"

enum class Screen { Title, Playing, Paused, Controls, GameOver };

struct Entity { float x, y, vx, vy, r; bool alive; };

struct Game {
    Screen screen = Screen::Title;
    Screen controls_return = Screen::Title;
    int menu = 0;
    float px = 320, py = 240, pvx = 0, pvy = 0;
    float dash_time = 0, dash_cooldown = 0, invuln = 0;
    int lives = 3, score = 0, best = 0;
    int dash_binding = 0;
    uint64_t tick = 0;
    uint32_t rng = 0x9E3779B9u;
    std::vector<Entity> sparks, shards;
    float spawn_timer = 0;
    bool want_quit = false;
    bool persist = true;   // false in --selftest: no settings file
    int sfx_pickup = -1, sfx_hit = -1, sfx_dash = -1, sfx_select = -1;

    uint32_t rand();
    float frand(float lo, float hi);
    void reset_run();
    void step(const platform::Input& in, float dt);
    std::vector<std::string> menu_items() const;
    void activate(int item);
    uint32_t hash() const;
};

// settings: best score and the dash binding, in the platform's save folder
void load_settings(Game& g);
void save_settings(const Game& g);
