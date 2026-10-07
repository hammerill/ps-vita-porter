/* vitaport: code shared by the Vita and the simulation backends (included by both, not compiled on its own).
 * Shipped by ps-vita-porter (MIT). */
#include <stdio.h>
#include <string.h>

static vp_config g_cfg;
static char g_folder[64] = "game";
static char g_assets[64] = "assets";

static void vp__store_config(const vp_config* cfg) {
    if (cfg) {
        g_cfg = *cfg;
        if (cfg->data_folder && *cfg->data_folder) snprintf(g_folder, sizeof g_folder, "%s", cfg->data_folder);
        if (cfg->assets_dir && *cfg->assets_dir) snprintf(g_assets, sizeof g_assets, "%s", cfg->assets_dir);
    }
    g_cfg.data_folder = g_folder;
    g_cfg.assets_dir = g_assets;
}

vp_rect vp_fit(int src_w, int src_h, int dst_w, int dst_h, int mode) {
    vp_rect r = {0, 0, dst_w, dst_h};
    if (src_w <= 0 || src_h <= 0 || mode == VP_FIT_STRETCH) return r;
    if (mode == VP_FIT_INTEGER) {
        int kx = dst_w / src_w, ky = dst_h / src_h;
        int k = kx < ky ? kx : ky;
        if (k >= 1) {
            r.w = src_w * k;
            r.h = src_h * k;
            r.x = (dst_w - r.w) / 2;
            r.y = (dst_h - r.h) / 2;
            return r;
        }
        mode = VP_FIT_ASPECT;   /* source larger than the screen: fall back to aspect fit */
    }
    /* compare src_w/src_h with dst_w/dst_h without floats */
    long long a = (long long)src_w * dst_h, b = (long long)dst_w * src_h;
    int wide = a > b;   /* source is wider than the screen */
    if ((mode == VP_FIT_ASPECT) == wide) {
        r.w = dst_w;
        r.h = (int)((long long)src_h * dst_w / src_w);
    } else {
        r.h = dst_h;
        r.w = (int)((long long)src_w * dst_h / src_h);
    }
    r.x = (dst_w - r.w) / 2;
    r.y = (dst_h - r.h) / 2;
    return r;
}

uint32_t vp_cancel_button(void) { return vp_confirm_button() == VP_CROSS ? VP_CIRCLE : VP_CROSS; }

static void vp__edges(vp_input* in, uint32_t* prev) {
    in->pressed = in->buttons & ~*prev;
    in->released = *prev & ~in->buttons;
    *prev = in->buttons;
}
