/* vitaport: the Vita side of a port's platform layer, and its PC "Vita simulation" twin.
 * Shipped by ps-vita-porter (`vita init --kit`, MIT). Yours to edit once copied.
 *
 * The same API runs in two builds:
 *   - on the Vita (VitaSDK, __vita__):  SceCtrl, SceTouch, SceMotion, SceAppUtil, app0:/ux0:data paths, a log file
 *                                       and an optional UDP network log (VP_LOG_HOST/VP_LOG_PORT at compile time);
 *   - on the PC with -DVITA_SIM=ON:     the Vita controls mapped to keyboard/gamepad/mouse, Vita paths translated to
 *                                       folders on disk, a memory cap enforced by an allocator wrapper, scripted
 *                                       input, screenshots and stats for `vita sim`.
 * Game code calls vp_* through the project's existing platform layer and never touches Sce* or SDL directly for
 * these concerns. C and C++ compatible. */
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Screen */
#define VP_SCREEN_W 960
#define VP_SCREEN_H 544

/* Buttons: the same bits as SceCtrlButtons. The Vita has no L2/R2/L3/R3: its shoulder buttons are L and R. */
#define VP_SELECT   0x00000001u
#define VP_START    0x00000008u
#define VP_UP       0x00000010u
#define VP_RIGHT    0x00000020u
#define VP_DOWN     0x00000040u
#define VP_LEFT     0x00000080u
#define VP_L        0x00000100u
#define VP_R        0x00000200u
#define VP_TRIANGLE 0x00001000u
#define VP_CIRCLE   0x00002000u
#define VP_CROSS    0x00004000u
#define VP_SQUARE   0x00008000u

#define VP_MAX_FRONT 6
#define VP_MAX_REAR  4

typedef struct vp_touch_point {
    int id;
    float x, y;            /* normalised to the panel: 0..1 left->right, top->bottom */
} vp_touch_point;

typedef struct vp_input {
    uint32_t buttons;      /* VP_* bits held now */
    uint32_t pressed;      /* went down since the previous vp_poll */
    uint32_t released;     /* went up since the previous vp_poll */
    uint8_t lx, ly, rx, ry;    /* sticks, 0..255, 128 = centre, y grows downwards */
    int front_count;
    vp_touch_point front[VP_MAX_FRONT];
    int rear_count;
    vp_touch_point rear[VP_MAX_REAR];
    float accel[3];        /* g */
    float gyro[3];         /* angular velocity, rad/s (x pitch, y yaw, z roll) */
} vp_input;

typedef struct vp_config {
    const char* data_folder;   /* ux0:data/<data_folder>/: saves, config, logs, external assets */
    const char* assets_dir;    /* folder name of the game data: app0:<assets_dir>/ or ux0:data/<data_folder>/<assets_dir>/ */
    int assets_external;       /* 1 = external assets (ux0:data), 0 = embedded (app0:) */
    int enable_front_touch;
    int enable_rear_touch;
    int enable_motion;
} vp_config;

/* Initialise sampling, paths and logging. Returns 0 on success. */
int vp_init(const vp_config* cfg);
void vp_shutdown(void);

/* Read every input once per frame. */
void vp_poll(vp_input* out);

/* The system's confirm/cancel buttons (Settings: Cross or Circle as "enter"). Never hard-code Cross. */
uint32_t vp_confirm_button(void);
uint32_t vp_cancel_button(void);

/* Paths. Asset paths are read-only game data; save paths are ux0:data/<data_folder>/<rel> (folders created).
 * vp_translate turns a Vita path ("app0:...", "ux0:...") into what fopen() needs on this build. */
const char* vp_asset_path(const char* rel, char* buf, size_t n);
const char* vp_save_path(const char* rel, char* buf, size_t n);
const char* vp_translate(const char* vita_path, char* buf, size_t n);

/* Log to stderr (sim), the log file ux0:data/<data_folder>/vitaport.log and, on the Vita, the network log. */
void vp_log(const char* fmt, ...);

/* Fit a src_w x src_h image into dst_w x dst_h. */
typedef struct vp_rect { int x, y, w, h; } vp_rect;
enum { VP_FIT_ASPECT = 0, VP_FIT_INTEGER = 1, VP_FIT_STRETCH = 2, VP_FIT_CROP = 3 };
vp_rect vp_fit(int src_w, int src_h, int dst_w, int dst_h, int mode);

/* Memory the game allocated through malloc/new (sim: the wrapper's count; Vita: newlib's mallinfo). */
size_t vp_mem_used(void);
size_t vp_mem_peak(void);
size_t vp_mem_budget(void);

/* Call once per frame right before presenting. The sim uses it for scripted input timing, screenshots and stats.
 * vp_set_readback: a function that copies the last rendered frame (w x h RGBA, top row first) for screenshots. */
typedef void (*vp_readback_fn)(int w, int h, uint8_t* rgba);
void vp_set_readback(vp_readback_fn fn, int w, int h);
void vp_frame(void);

/* 1 once a `quit` line of the sim's input script ran (always 0 on the Vita). */
int vp_should_quit(void);
/* 1 in the PC simulation profile. */
int vp_is_sim(void);

#ifdef __cplusplus
}
#endif
