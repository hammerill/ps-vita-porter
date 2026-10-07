#include "render.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <vector>

#include "atlas.h"
#include "gl.h"
#include "platform/platform.h"

namespace {
GLuint g_tex;
struct V { float x, y, u, v; unsigned char r, g, b, a; };
std::vector<V> g_verts;

struct Color { unsigned char r, g, b, a; };
constexpr Color kWhite{255, 255, 255, 255}, kDim{150, 160, 190, 255}, kHot{255, 214, 102, 255}, kBg{14, 12, 36, 255};

bool load_tga(const std::vector<uint8_t>& d, int& w, int& h, std::vector<uint8_t>& rgba) {
    if (d.size() < 18 || d[2] != 2 || d[16] != 32) return false;
    w = d[12] | d[13] << 8, h = d[14] | d[15] << 8;
    bool top = d[17] & 0x20;
    size_t off = 18 + d[0];
    if (d.size() < off + size_t(w) * h * 4) return false;
    rgba.resize(size_t(w) * h * 4);
    for (int y = 0; y < h; ++y) {
        int sy = top ? y : h - 1 - y;
        for (int x = 0; x < w; ++x) {
            const uint8_t* s = &d[off + (size_t(sy) * w + x) * 4];
            uint8_t* o = &rgba[(size_t(y) * w + x) * 4];
            o[0] = s[2], o[1] = s[1], o[2] = s[0], o[3] = s[3];
        }
    }
    return true;
}

void quad(float x, float y, float w, float h, int sx, int sy, int sw, int sh, Color c) {
    float s = 1.0f / atlas::kSize;
    float u0 = sx * s, v0 = sy * s, u1 = (sx + sw) * s, v1 = (sy + sh) * s;
    V a{x, y, u0, v0, c.r, c.g, c.b, c.a}, b{x + w, y, u1, v0, c.r, c.g, c.b, c.a};
    V d{x, y + h, u0, v1, c.r, c.g, c.b, c.a}, e{x + w, y + h, u1, v1, c.r, c.g, c.b, c.a};
    g_verts.insert(g_verts.end(), {a, b, d, b, e, d});
}

void sprite(const atlas::Sprite& s, float cx, float cy, float scale, Color c) {
    float sz = s.size * scale;
    quad(cx - sz / 2, cy - sz / 2, sz, sz, s.x, s.y, s.size, s.size, c);
}

void glyph(int g, float x, float y, float size) {
    quad(x, y, size, size, g * atlas::kGlyphSize, atlas::kGlyphY, atlas::kGlyphSize, atlas::kGlyphSize, kWhite);
}

float text(const char* s, float x, float y, int scale, Color c) {
    for (const char* p = s; *p; ++p) {
        const char* at = std::strchr(atlas::kFontOrder, *p);
        int i = at ? int(at - atlas::kFontOrder) : 0;
        quad(x, y, 8.0f * scale, 8.0f * scale, (i % 32) * atlas::kCell, (i / 32) * atlas::kCell, atlas::kCell, atlas::kCell, c);
        x += 6.0f * scale;
    }
    return x;
}

float text_w(const char* s, int scale) { return float(std::strlen(s)) * 6.0f * scale; }

void centred(const char* s, float y, int scale, Color c) { text(s, 320 - text_w(s, scale) / 2, y, scale, c); }

// "<glyph or key> LABEL" prompt, centred
void prompt(int vita_glyph, const char* key, const char* label, float y) {
    bool vita = platform::prompts() == platform::Prompts::Vita;
    float w = (vita ? 24 + 6 : text_w(key, 2) + 12) + text_w(label, 2);
    float x = 320 - w / 2;
    if (vita) {
        glyph(vita_glyph, x, y - 4, 24);
        x += 30;
    } else {
        x = text(key, x, y, 2, kHot) + 12;
    }
    text(label, x, y, 2, kDim);
}

void flush() {
    if (g_verts.empty()) return;
    glEnableClientState(GL_VERTEX_ARRAY);
    glEnableClientState(GL_TEXTURE_COORD_ARRAY);
    glEnableClientState(GL_COLOR_ARRAY);
    glVertexPointer(2, GL_FLOAT, sizeof(V), &g_verts[0].x);
    glTexCoordPointer(2, GL_FLOAT, sizeof(V), &g_verts[0].u);
    glColorPointer(4, GL_UNSIGNED_BYTE, sizeof(V), &g_verts[0].r);
    glDrawArrays(GL_TRIANGLES, 0, GLsizei(g_verts.size()));
    glDisableClientState(GL_COLOR_ARRAY);
    glDisableClientState(GL_TEXTURE_COORD_ARRAY);
    glDisableClientState(GL_VERTEX_ARRAY);
    g_verts.clear();
}

void menu(const Game& g, float y0) {
    auto items = g.menu_items();
    for (size_t i = 0; i < items.size(); ++i) {
        std::string label = items[i];
        if (g.screen == Screen::Controls && i == 0) label = std::string("DASH: ") + platform::dash_binding_name(g.dash_binding);
        bool sel = int(i) == g.menu;
        float y = y0 + 36.0f * i;
        if (sel) centred((std::string("> ") + label + " <").c_str(), y, 3, kHot);
        else centred(label.c_str(), y, 3, kDim);
        if (g.screen == Screen::Controls && i == 0 && platform::dash_binding_glyph(g.dash_binding) >= 0)
            glyph(platform::dash_binding_glyph(g.dash_binding), 320 + text_w((std::string("> ") + label + " <").c_str(), 3) / 2 + 10, y - 2, 28);
    }
}
}  // namespace

namespace render {

bool init() {
    std::vector<uint8_t> d = platform::load_asset("atlas.tga"), rgba;
    int w = 0, h = 0;
    if (!load_tga(d, w, h, rgba)) {
        platform::log("render: cannot load atlas.tga (%u bytes)", unsigned(d.size()));
        return false;
    }
    glGenTextures(1, &g_tex);
    glBindTexture(GL_TEXTURE_2D, g_tex);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);   // pixel art: nearest (PORT_PLAN.md)
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    return true;
}

void frame(const Game& g) {
    platform::Viewport vp = platform::viewport();
    glViewport(0, 0, vp.fb_w, vp.fb_h);
    glClearColor(0, 0, 0, 1);   // pillarbox bars
    glClear(GL_COLOR_BUFFER_BIT);
    glViewport(vp.x, vp.fb_h - vp.y - vp.h, vp.w, vp.h);
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    glOrtho(0, platform::kGameW, platform::kGameH, 0, -1, 1);
    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    glEnable(GL_TEXTURE_2D);
    glBindTexture(GL_TEXTURE_2D, g_tex);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);

    // background: the atlas's solid block stretched over the arena, tinted
    quad(0, 0, 640, 480, atlas::kSolidX, atlas::kSolidY, 1, 1, kBg);
    for (int i = 0; i < 40; ++i) {   // fixed star field
        float sx = float((i * 151) % 640), sy = float((i * 97) % 440 + 40);
        sprite(atlas::kSpark, sx, sy, 0.25f, Color{200, 210, 255, 90});
    }
    char buf[64];
    if (g.screen == Screen::Title) {
        centred("LUMEN DRIFT", 120, 6, kWhite);
        centred("COLLECT THE SPARKS. DODGE THE SHARDS.", 190, 2, kDim);
        menu(g, 250);
        std::snprintf(buf, sizeof buf, "BEST %d", g.best);
        centred(buf, 400, 2, kDim);
        prompt(platform::confirm_glyph(), "ENTER", "SELECT", 440);
    } else {
        for (auto& s : g.sparks) sprite(atlas::kSpark, s.x, s.y, 1.0f + 0.15f * std::sin(g.tick * 0.2f), kWhite);
        for (auto& s : g.shards) sprite(atlas::kShard, s.x, s.y, 0.8f, kWhite);
        bool blink = g.invuln > 0 && (g.tick / 4) % 2;
        if (!blink) sprite(atlas::kOrb, g.px, g.py, g.dash_time > 0 ? 1.4f : 1.0f, kWhite);
        if (g.dash_cooldown <= 0) sprite(atlas::kRing, g.px, g.py, 1.0f, Color{120, 230, 255, 90});
        quad(0, 0, 640, 36, atlas::kSolidX, atlas::kSolidY, 1, 1, Color{0, 0, 0, 150});
        std::snprintf(buf, sizeof buf, "SCORE %d", g.score);
        text(buf, 12, 10, 2, kWhite);
        std::snprintf(buf, sizeof buf, "LIVES %d", g.lives);
        text(buf, 520, 10, 2, g.lives > 1 ? kWhite : Color{255, 92, 138, 255});
        if (g.screen == Screen::Playing && g.tick < 240) {
            bool vita = platform::prompts() == platform::Prompts::Vita;
            prompt(platform::dash_binding_glyph(g.dash_binding), platform::dash_binding_name(g.dash_binding), "DASH", 440);
            if (!vita) centred("MOVE: WASD / ARROWS   PAUSE: ESC", 410, 2, kDim);
        }
        if (g.screen != Screen::Playing) {
            quad(0, 0, 640, 480, atlas::kSolidX, atlas::kSolidY, 1, 1, Color{0, 0, 0, 170});
            const char* title = g.screen == Screen::Paused ? "PAUSED" : g.screen == Screen::Controls ? "CONTROLS" : "GAME OVER";
            centred(title, 150, 5, kWhite);
            if (g.screen == Screen::GameOver) {
                std::snprintf(buf, sizeof buf, "SCORE %d   BEST %d", g.score, g.best);
                centred(buf, 205, 2, kDim);
            }
            menu(g, 250);
            prompt(platform::back_glyph(), "ESC", "BACK", 440);
        }
    }
    flush();
}

void read_pixels(int w, int h, unsigned char* rgba) {
    std::vector<unsigned char> tmp(size_t(w) * h * 4);
    glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, tmp.data());
    for (int y = 0; y < h; ++y) std::memcpy(rgba + size_t(y) * w * 4, &tmp[size_t(h - 1 - y) * w * 4], size_t(w) * 4);
}

}  // namespace render
