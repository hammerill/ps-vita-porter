/* vitaport, PC "Vita simulation" backend (-DVITA_SIM=ON). Shipped by ps-vita-porter (MIT).
 *
 * The game keeps its own PC window/renderer (sized VP_SCREEN_W x VP_SCREEN_H in this profile); this file only
 * reads SDL's input state, so the game must keep pumping SDL events as usual. SDL2 by default, SDL3 with VP_SDL3.
 *
 * Controls (the same layout as Vita3K's defaults, so testers learn one layout):
 *   D-pad arrows        left stick WASD        right stick IJKL
 *   Cross X   Circle C   Square Z   Triangle V   L Q   R E   Start Enter   Select Backspace
 *   front touch: left mouse button        rear touch: left mouse button while Left Alt is held
 *   gyro: numpad 8/2 pitch, 4/6 yaw, 7/9 roll (held = +-2 rad/s)
 *   a gamepad maps by position: A Cross, B Circle, X Square, Y Triangle, LB L, RB R, Back Select, Start Start;
 *   its triggers and stick clicks do nothing (the Vita has no L2/R2/L3/R3).
 *
 * Environment (set by `vita sim`):
 *   VITASIM_APP0   folder standing in for app0: (embedded assets)          default ./app0
 *   VITASIM_UX0    folder standing in for ux0:                             default ./build-sim/ux0
 *   VITASIM_ENTER  cross | circle (the system's confirm button)            default cross
 *   VITASIM_INPUT  input script: one "<ms> <command> [args]" per line, ms since vp_init:
 *                  press|release|tap <button> [ms]   lstick|rstick <x 0-255> <y 0-255>   touch|rtouch <x> <y>
 *                  (pixels on the 960x544 screen)   untouch|unrtouch   gyro <x> <y> <z>   shot <name>   quit
 *                  buttons: cross circle square triangle l r start select up down left right
 *   VITASIM_SHOT_AT  seconds after vp_init for one screenshot; VITASIM_SHOT_DIR where PNGs go (default .)
 *   VITASIM_STATS    write JSON stats here at exit (frames, fps, memory peak/budget, oom, shots)
 *   VITASIM_MEM_MB / VITASIM_OOM   see vitaport_alloc.cpp */
#include "vitaport.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#define vp_mkdir(p) _mkdir(p)
#else
#define vp_mkdir(p) mkdir(p, 0755)
#endif

#ifdef VP_SDL3
#include <SDL3/SDL.h>
typedef SDL_Gamepad vp_pad_t;
#define VP_KMOD_LALT SDL_KMOD_LALT
#else
#include <SDL.h>
typedef SDL_GameController vp_pad_t;
#define VP_KMOD_LALT KMOD_LALT
#endif

#include "vitaport_common.c"

/* ------------------------------------------------------------------ state */
static FILE* g_log;
static char g_app0[512] = "app0";
static char g_ux0[512] = "build-sim/ux0";
static uint32_t g_prev;
static uint32_t g_t0;
static int g_enter_circle;
static vp_pad_t* g_pad;
static int g_quit;
static vp_readback_fn g_readback;
static int g_rb_w, g_rb_h;
static double g_shot_at = -1;
static char g_shot_dir[512] = ".";
static int g_shots;
static char g_pending_shot[64];
static unsigned long g_frames;
static char g_stats[512];

/* scripted input */
typedef struct { uint32_t ms; char cmd[12]; char arg[32]; int a, b, c; } vp_line;
static vp_line* g_script;
static int g_script_n, g_script_pos;
static uint32_t g_s_buttons;
static int g_s_l[2] = {128, 128}, g_s_r[2] = {128, 128}, g_s_lset, g_s_rset;
static int g_s_touch = -1, g_s_tx, g_s_ty, g_s_rtouch = -1, g_s_rx, g_s_ry;
static float g_s_gyro[3];
typedef struct { uint32_t button, until; } vp_tap;
static vp_tap g_taps[16];

extern size_t vp__alloc_used(void);
extern size_t vp__alloc_peak(void);
extern size_t vp__alloc_budget(void);
extern int vp__alloc_oom(void);

static uint32_t now_ms(void) { return (uint32_t)SDL_GetTicks() - g_t0; }

static void mkdirs(const char* path) {
    char tmp[1024];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char* p = tmp + 1; *p; ++p) {
        if (*p == '/' || *p == '\\') {
            char c = *p;
            *p = 0;
            vp_mkdir(tmp);
            *p = c;
        }
    }
    vp_mkdir(tmp);
}

static uint32_t button_by_name(const char* s) {
    static const struct { const char* n; uint32_t b; } T[] = {
        {"cross", VP_CROSS}, {"circle", VP_CIRCLE}, {"square", VP_SQUARE}, {"triangle", VP_TRIANGLE}, {"l", VP_L}, {"r", VP_R},
        {"start", VP_START}, {"select", VP_SELECT}, {"up", VP_UP}, {"down", VP_DOWN}, {"left", VP_LEFT}, {"right", VP_RIGHT},
        {"confirm", 0xFFFFFFFFu}, {"cancel", 0xFFFFFFFEu}};
    for (size_t i = 0; i < sizeof T / sizeof T[0]; ++i)
        if (!strcmp(s, T[i].n)) {
            if (T[i].b == 0xFFFFFFFFu) return vp_confirm_button();
            if (T[i].b == 0xFFFFFFFEu) return vp_cancel_button();
            return T[i].b;
        }
    return 0;
}

static void load_script(const char* path) {
    FILE* f = fopen(path, "r");
    if (!f) {
        vp_log("VITASIM: cannot open input script %s", path);
        return;
    }
    char line[256];
    int cap = 64;
    g_script = (vp_line*)calloc((size_t)cap, sizeof(vp_line));
    while (fgets(line, sizeof line, f)) {
        char* h = strchr(line, '#');
        if (h) *h = 0;
        vp_line L;
        memset(&L, 0, sizeof L);
        unsigned ms = 0;
        int n = sscanf(line, "%u %11s %31s %d %d", &ms, L.cmd, L.arg, &L.b, &L.c);
        if (n < 2) continue;
        L.ms = ms;
        L.a = atoi(L.arg);
        if (g_script_n == cap) {
            cap *= 2;
            g_script = (vp_line*)realloc(g_script, (size_t)cap * sizeof(vp_line));
        }
        g_script[g_script_n++] = L;
    }
    fclose(f);
    vp_log("VITASIM: input script %s (%d lines)", path, g_script_n);
}

/* ------------------------------------------------------------------ PNG (stored deflate) */
static uint32_t crc_table[256];
static uint32_t crc32_update(uint32_t c, const uint8_t* p, size_t n) {
    if (!crc_table[1])
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t k = i;
            for (int j = 0; j < 8; ++j) k = k & 1 ? 0xEDB88320u ^ (k >> 1) : k >> 1;
            crc_table[i] = k;
        }
    c = ~c;
    while (n--) c = crc_table[(c ^ *p++) & 0xFF] ^ (c >> 8);
    return ~c;
}
static void put32(uint8_t* p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static void chunk(FILE* f, const char* type, const uint8_t* data, uint32_t len) {
    uint8_t h[8];
    put32(h, len);
    memcpy(h + 4, type, 4);
    fwrite(h, 1, 8, f);
    if (len) fwrite(data, 1, len, f);
    uint32_t c = crc32_update(0, (const uint8_t*)type, 4);
    c = crc32_update(c, data, len);
    put32(h, c);
    fwrite(h, 1, 4, f);
}
static int write_png(const char* path, int w, int h, const uint8_t* rgba) {
    size_t row = (size_t)w * 4 + 1, raw_len = row * (size_t)h;
    uint8_t* raw = (uint8_t*)malloc(raw_len);
    if (!raw) return -1;
    for (int y = 0; y < h; ++y) {
        raw[y * row] = 0;
        memcpy(raw + y * row + 1, rgba + (size_t)y * w * 4, (size_t)w * 4);
    }
    size_t blocks = (raw_len + 65534) / 65535;
    size_t z_len = 2 + raw_len + blocks * 5 + 4;
    uint8_t* z = (uint8_t*)malloc(z_len);
    if (!z) { free(raw); return -1; }
    size_t o = 0, left = raw_len, pos = 0;
    z[o++] = 0x78; z[o++] = 0x01;
    uint32_t a = 1, b = 0;
    while (left) {
        uint16_t n = (uint16_t)(left > 65535 ? 65535 : left);
        z[o++] = left == n ? 1 : 0;
        z[o++] = (uint8_t)n; z[o++] = (uint8_t)(n >> 8); z[o++] = (uint8_t)~n; z[o++] = (uint8_t)(~n >> 8);
        memcpy(z + o, raw + pos, n);
        for (size_t i = 0; i < n; ++i) { a = (a + raw[pos + i]) % 65521; b = (b + a) % 65521; }
        o += n; pos += n; left -= n;
    }
    put32(z + o, (b << 16) | a);
    o += 4;
    FILE* f = fopen(path, "wb");
    if (!f) { free(raw); free(z); return -1; }
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A};
    fwrite(sig, 1, 8, f);
    uint8_t ihdr[13];
    put32(ihdr, (uint32_t)w); put32(ihdr + 4, (uint32_t)h);
    ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    chunk(f, "IHDR", ihdr, 13);
    chunk(f, "IDAT", z, (uint32_t)o);
    chunk(f, "IEND", NULL, 0);
    fclose(f);
    free(raw);
    free(z);
    return 0;
}

static void take_shot(const char* name) {
    if (!g_readback || g_rb_w <= 0 || g_rb_h <= 0) {
        vp_log("VITASIM: screenshot '%s' requested but no readback function is set (vp_set_readback)", name);
        return;
    }
    uint8_t* px = (uint8_t*)malloc((size_t)g_rb_w * g_rb_h * 4);
    if (!px) return;
    g_readback(g_rb_w, g_rb_h, px);
    char path[1024];
    snprintf(path, sizeof path, "%s/%s.png", g_shot_dir, name);
    if (write_png(path, g_rb_w, g_rb_h, px) == 0) {
        ++g_shots;
        vp_log("VITASIM: screenshot %s", path);
    }
    free(px);
}

/* ------------------------------------------------------------------ API */
static void write_stats(void) {
    if (!g_stats[0]) return;
    FILE* f = fopen(g_stats, "w");
    if (!f) return;
    double secs = now_ms() / 1000.0;
    fprintf(f, "{\"frames\": %lu, \"seconds\": %.2f, \"fps\": %.1f, \"mem_peak\": %lu, \"mem_used\": %lu, \"mem_budget\": %lu, "
               "\"oom\": %d, \"shots\": %d, \"quit_by_script\": %d}\n",
            g_frames, secs, secs > 0 ? g_frames / secs : 0.0, (unsigned long)vp_mem_peak(), (unsigned long)vp_mem_used(),
            (unsigned long)vp_mem_budget(), vp__alloc_oom(), g_shots, g_quit);
    fclose(f);
}

int vp_init(const vp_config* cfg) {
    vp__store_config(cfg);
    const char* e;
    if ((e = getenv("VITASIM_APP0")) && *e) snprintf(g_app0, sizeof g_app0, "%s", e);
    if ((e = getenv("VITASIM_UX0")) && *e) snprintf(g_ux0, sizeof g_ux0, "%s", e);
    if ((e = getenv("VITASIM_ENTER"))) g_enter_circle = !strcmp(e, "circle");
    if ((e = getenv("VITASIM_SHOT_DIR")) && *e) snprintf(g_shot_dir, sizeof g_shot_dir, "%s", e);
    if ((e = getenv("VITASIM_SHOT_AT")) && *e) g_shot_at = atof(e);
    if ((e = getenv("VITASIM_STATS")) && *e) snprintf(g_stats, sizeof g_stats, "%s", e);
    char dir[1024];
    snprintf(dir, sizeof dir, "%s/data/%s", g_ux0, g_folder);
    mkdirs(dir);
    char logp[1100];
    snprintf(logp, sizeof logp, "%s/vitaport.log", dir);
    g_log = fopen(logp, "w");
#ifdef VP_SDL3
    SDL_InitSubSystem(SDL_INIT_GAMEPAD);
    int count = 0;
    SDL_JoystickID* ids = SDL_GetGamepads(&count);
    if (ids && count > 0) g_pad = SDL_OpenGamepad(ids[0]);
    SDL_free(ids);
#else
    SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER);
    for (int i = 0; i < SDL_NumJoysticks() && !g_pad; ++i)
        if (SDL_IsGameController(i)) g_pad = SDL_GameControllerOpen(i);
#endif
    g_t0 = (uint32_t)SDL_GetTicks();
    if ((e = getenv("VITASIM_INPUT")) && *e) load_script(e);
    vp_log("VITASIM: Vita simulation profile: %dx%d, data folder %s, assets %s (%s), memory budget %lu MiB, confirm %s",
           VP_SCREEN_W, VP_SCREEN_H, g_folder, g_assets, g_cfg.assets_external ? "external" : "embedded",
           (unsigned long)(vp_mem_budget() >> 20), g_enter_circle ? "Circle" : "Cross");
    atexit(write_stats);
    return 0;
}

void vp_shutdown(void) {
    vp_log("VITASIM: frames %lu, peak memory %lu KiB of %lu KiB", g_frames, (unsigned long)(vp_mem_peak() >> 10),
           (unsigned long)(vp_mem_budget() >> 10));
    write_stats();
    g_stats[0] = 0;
#ifdef VP_SDL3
    if (g_pad) SDL_CloseGamepad(g_pad);
#else
    if (g_pad) SDL_GameControllerClose(g_pad);
#endif
    g_pad = NULL;
    if (g_log) fclose(g_log);
    g_log = NULL;
}

uint32_t vp_confirm_button(void) { return g_enter_circle ? VP_CIRCLE : VP_CROSS; }

static void run_script(uint32_t t) {
    for (int i = 0; i < 16; ++i)
        if (g_taps[i].button && t >= g_taps[i].until) {
            g_s_buttons &= ~g_taps[i].button;
            g_taps[i].button = 0;
        }
    while (g_script_pos < g_script_n && g_script[g_script_pos].ms <= t) {
        vp_line* L = &g_script[g_script_pos++];
        if (!strcmp(L->cmd, "press")) g_s_buttons |= button_by_name(L->arg);
        else if (!strcmp(L->cmd, "release")) g_s_buttons &= ~button_by_name(L->arg);
        else if (!strcmp(L->cmd, "tap")) {
            uint32_t b = button_by_name(L->arg);
            g_s_buttons |= b;
            for (int i = 0; i < 16; ++i)
                if (!g_taps[i].button) { g_taps[i].button = b; g_taps[i].until = t + (uint32_t)(L->b > 0 ? L->b : 100); break; }
        } else if (!strcmp(L->cmd, "lstick")) { g_s_l[0] = L->a; g_s_l[1] = L->b; g_s_lset = !(L->a == 128 && L->b == 128); }
        else if (!strcmp(L->cmd, "rstick")) { g_s_r[0] = L->a; g_s_r[1] = L->b; g_s_rset = !(L->a == 128 && L->b == 128); }
        else if (!strcmp(L->cmd, "touch")) { g_s_touch = 1; g_s_tx = L->a; g_s_ty = L->b; }
        else if (!strcmp(L->cmd, "untouch")) g_s_touch = -1;
        else if (!strcmp(L->cmd, "rtouch")) { g_s_rtouch = 1; g_s_rx = L->a; g_s_ry = L->b; }
        else if (!strcmp(L->cmd, "unrtouch")) g_s_rtouch = -1;
        else if (!strcmp(L->cmd, "gyro")) { g_s_gyro[0] = (float)atof(L->arg); g_s_gyro[1] = (float)L->b; g_s_gyro[2] = (float)L->c; }
        else if (!strcmp(L->cmd, "shot")) snprintf(g_pending_shot, sizeof g_pending_shot, "%s", L->arg[0] ? L->arg : "script");
        else if (!strcmp(L->cmd, "quit")) { g_quit = 1; vp_log("VITASIM: quit requested by the input script"); }
        vp_log("VITASIM: script %u ms: %s %s", L->ms, L->cmd, L->arg);
    }
}

static uint8_t axis(int neg, int pos) { return (uint8_t)(neg && !pos ? 0 : pos && !neg ? 255 : 128); }

void vp_poll(vp_input* in) {
    memset(in, 0, sizeof *in);
    uint32_t t = now_ms();
    run_script(t);
#ifdef VP_SDL3
    const bool* k = SDL_GetKeyboardState(NULL);
#else
    const Uint8* k = SDL_GetKeyboardState(NULL);
#endif
    uint32_t b = 0;
    if (k[SDL_SCANCODE_UP]) b |= VP_UP;
    if (k[SDL_SCANCODE_DOWN]) b |= VP_DOWN;
    if (k[SDL_SCANCODE_LEFT]) b |= VP_LEFT;
    if (k[SDL_SCANCODE_RIGHT]) b |= VP_RIGHT;
    if (k[SDL_SCANCODE_X]) b |= VP_CROSS;
    if (k[SDL_SCANCODE_C]) b |= VP_CIRCLE;
    if (k[SDL_SCANCODE_Z]) b |= VP_SQUARE;
    if (k[SDL_SCANCODE_V]) b |= VP_TRIANGLE;
    if (k[SDL_SCANCODE_Q]) b |= VP_L;
    if (k[SDL_SCANCODE_E]) b |= VP_R;
    if (k[SDL_SCANCODE_RETURN]) b |= VP_START;
    if (k[SDL_SCANCODE_BACKSPACE]) b |= VP_SELECT;
    in->lx = axis(k[SDL_SCANCODE_A], k[SDL_SCANCODE_D]);
    in->ly = axis(k[SDL_SCANCODE_W], k[SDL_SCANCODE_S]);
    in->rx = axis(k[SDL_SCANCODE_J], k[SDL_SCANCODE_L]);
    in->ry = axis(k[SDL_SCANCODE_I], k[SDL_SCANCODE_K]);
    if (g_pad) {
#ifdef VP_SDL3
#define PADB(x) SDL_GetGamepadButton(g_pad, SDL_GAMEPAD_BUTTON_##x)
#define PADA(x) SDL_GetGamepadAxis(g_pad, SDL_GAMEPAD_AXIS_##x)
        if (PADB(SOUTH)) b |= VP_CROSS;
        if (PADB(EAST)) b |= VP_CIRCLE;
        if (PADB(WEST)) b |= VP_SQUARE;
        if (PADB(NORTH)) b |= VP_TRIANGLE;
        if (PADB(LEFT_SHOULDER)) b |= VP_L;
        if (PADB(RIGHT_SHOULDER)) b |= VP_R;
        if (PADB(START)) b |= VP_START;
        if (PADB(BACK)) b |= VP_SELECT;
        if (PADB(DPAD_UP)) b |= VP_UP;
        if (PADB(DPAD_DOWN)) b |= VP_DOWN;
        if (PADB(DPAD_LEFT)) b |= VP_LEFT;
        if (PADB(DPAD_RIGHT)) b |= VP_RIGHT;
        int ax[4] = {PADA(LEFTX), PADA(LEFTY), PADA(RIGHTX), PADA(RIGHTY)};
#else
#define PADB(x) SDL_GameControllerGetButton(g_pad, SDL_CONTROLLER_BUTTON_##x)
#define PADA(x) SDL_GameControllerGetAxis(g_pad, SDL_CONTROLLER_AXIS_##x)
        if (PADB(A)) b |= VP_CROSS;
        if (PADB(B)) b |= VP_CIRCLE;
        if (PADB(X)) b |= VP_SQUARE;
        if (PADB(Y)) b |= VP_TRIANGLE;
        if (PADB(LEFTSHOULDER)) b |= VP_L;
        if (PADB(RIGHTSHOULDER)) b |= VP_R;
        if (PADB(START)) b |= VP_START;
        if (PADB(BACK)) b |= VP_SELECT;
        if (PADB(DPAD_UP)) b |= VP_UP;
        if (PADB(DPAD_DOWN)) b |= VP_DOWN;
        if (PADB(DPAD_LEFT)) b |= VP_LEFT;
        if (PADB(DPAD_RIGHT)) b |= VP_RIGHT;
        int ax[4] = {PADA(LEFTX), PADA(LEFTY), PADA(RIGHTX), PADA(RIGHTY)};
#endif
        uint8_t* dst[4] = {&in->lx, &in->ly, &in->rx, &in->ry};
        for (int i = 0; i < 4; ++i)
            if (ax[i] > 8000 || ax[i] < -8000) *dst[i] = (uint8_t)((ax[i] + 32768) >> 8);
    }
    b |= g_s_buttons;
    if (g_s_lset) { in->lx = (uint8_t)g_s_l[0]; in->ly = (uint8_t)g_s_l[1]; }
    if (g_s_rset) { in->rx = (uint8_t)g_s_r[0]; in->ry = (uint8_t)g_s_r[1]; }
    in->buttons = b;
    vp__edges(in, &g_prev);

    /* touch: mouse in the focused window; Left Alt held = rear panel */
#ifdef VP_SDL3
    float mx = 0, my = 0;
    SDL_MouseButtonFlags mb = SDL_GetMouseState(&mx, &my);
#else
    int mx = 0, my = 0;
    Uint32 mb = SDL_GetMouseState(&mx, &my);
#endif
    SDL_Window* w = SDL_GetMouseFocus();
    int ww = VP_SCREEN_W, wh = VP_SCREEN_H;
    if (w) SDL_GetWindowSize(w, &ww, &wh);
    int rear = (SDL_GetModState() & VP_KMOD_LALT) != 0;
    if ((mb & SDL_BUTTON_LMASK) && w && ww > 0 && wh > 0) {
        vp_touch_point p = {0, (float)mx / (float)ww, (float)my / (float)wh};
        if (rear && g_cfg.enable_rear_touch) in->rear[in->rear_count++] = p;
        else if (!rear && g_cfg.enable_front_touch) in->front[in->front_count++] = p;
    }
    if (g_s_touch > 0 && g_cfg.enable_front_touch && in->front_count < VP_MAX_FRONT) {
        vp_touch_point p = {1, g_s_tx / (float)VP_SCREEN_W, g_s_ty / (float)VP_SCREEN_H};
        in->front[in->front_count++] = p;
    }
    if (g_s_rtouch > 0 && g_cfg.enable_rear_touch && in->rear_count < VP_MAX_REAR) {
        vp_touch_point p = {1, g_s_rx / (float)VP_SCREEN_W, g_s_ry / (float)VP_SCREEN_H};
        in->rear[in->rear_count++] = p;
    }
    if (g_cfg.enable_motion) {
        in->accel[2] = -1.0f;
        in->gyro[0] = (k[SDL_SCANCODE_KP_8] ? 2.f : 0.f) - (k[SDL_SCANCODE_KP_2] ? 2.f : 0.f) + g_s_gyro[0];
        in->gyro[1] = (k[SDL_SCANCODE_KP_6] ? 2.f : 0.f) - (k[SDL_SCANCODE_KP_4] ? 2.f : 0.f) + g_s_gyro[1];
        in->gyro[2] = (k[SDL_SCANCODE_KP_9] ? 2.f : 0.f) - (k[SDL_SCANCODE_KP_7] ? 2.f : 0.f) + g_s_gyro[2];
    }
}

static void join(char* buf, size_t n, const char* a, const char* b, const char* c) {
    snprintf(buf, n, "%s/%s%s%s", a, b, c && *c ? "/" : "", c ? c : "");
}

const char* vp_asset_path(const char* rel, char* buf, size_t n) {
    char base[700];
    if (g_cfg.assets_external) snprintf(base, sizeof base, "%s/data/%s/%s", g_ux0, g_folder, g_assets);
    else snprintf(base, sizeof base, "%s/%s", g_app0, g_assets);
    snprintf(buf, n, "%s/%s", base, rel);
    return buf;
}

const char* vp_save_path(const char* rel, char* buf, size_t n) {
    char dir[700];
    snprintf(dir, sizeof dir, "%s/data/%s", g_ux0, g_folder);
    join(buf, n, dir, rel, NULL);
    char parent[1024];
    snprintf(parent, sizeof parent, "%s", buf);
    char* s = strrchr(parent, '/');
    if (s) { *s = 0; mkdirs(parent); }
    return buf;
}

const char* vp_translate(const char* p, char* buf, size_t n) {
    if (!strncmp(p, "app0:", 5)) snprintf(buf, n, "%s/%s", g_app0, p[5] == '/' ? p + 6 : p + 5);
    else if (!strncmp(p, "ux0:", 4)) snprintf(buf, n, "%s/%s", g_ux0, p[4] == '/' ? p + 5 : p + 4);
    else snprintf(buf, n, "%s", p);
    return buf;
}

void vp_log(const char* fmt, ...) {
    char msg[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    fprintf(stderr, "[%7.3f] %s\n", (SDL_GetTicks() - g_t0) / 1000.0, msg);
    if (g_log) {
        fprintf(g_log, "%s\n", msg);
        fflush(g_log);
    }
}

size_t vp_mem_used(void) { return vp__alloc_used(); }
size_t vp_mem_peak(void) { return vp__alloc_peak(); }
size_t vp_mem_budget(void) { return vp__alloc_budget(); }

void vp_set_readback(vp_readback_fn fn, int w, int h) {
    g_readback = fn;
    g_rb_w = w;
    g_rb_h = h;
}

void vp_frame(void) {
    ++g_frames;
    if (g_pending_shot[0]) {   /* taken here: vp_frame runs right before present, so the frame is complete */
        take_shot(g_pending_shot);
        g_pending_shot[0] = 0;
    }
    if (g_shot_at >= 0 && now_ms() >= (uint32_t)(g_shot_at * 1000.0)) {
        char name[64];
        snprintf(name, sizeof name, "shot-%ds", (int)g_shot_at);
        take_shot(name);
        g_shot_at = -1;
    }
}

int vp_should_quit(void) { return g_quit; }
int vp_is_sim(void) { return 1; }
