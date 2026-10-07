/* vitaport, PS Vita backend (VitaSDK). Shipped by ps-vita-porter (MIT).
 * Links: SceCtrl_stub SceTouch_stub SceMotion_stub SceAppUtil_stub SceSysmodule_stub (+ SceNet_stub SceNetCtl_stub
 * when VP_LOG_HOST is defined). cmake/VitaPort.cmake adds them.
 *
 * Network log: compile with -DVP_LOG_HOST="192.168.1.10" [-DVP_LOG_PORT=18194] (Debug builds) and run
 * `vita logs` on that PC: every vp_log line is also sent as a UDP datagram. */
#include "vitaport.h"

#include <malloc.h>
#include <psp2/apputil.h>
#include <psp2/ctrl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/motion.h>
#include <psp2/system_param.h>
#include <psp2/touch.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

#ifdef VP_LOG_HOST
#include <psp2/net/net.h>
#include <psp2/net/netctl.h>
#include <psp2/sysmodule.h>
#ifndef VP_LOG_PORT
#define VP_LOG_PORT 18194
#endif
#endif

#include "vitaport_common.c"

extern unsigned int _newlib_heap_size_user __attribute__((weak));

static FILE* g_log;
static uint32_t g_prev;
static int g_enter_circle;
static SceTouchPanelInfo g_panel[2];
static size_t g_peak;
#ifdef VP_LOG_HOST
static int g_sock = -1;
static SceNetSockaddrIn g_addr;
static char g_net_mem[64 * 1024];
#endif

static void mkdirs(const char* path) {
    char tmp[512];
    snprintf(tmp, sizeof tmp, "%s", path);
    for (char* p = tmp + 5; *p; ++p)
        if (*p == '/') {
            *p = 0;
            sceIoMkdir(tmp, 0777);
            *p = '/';
        }
    sceIoMkdir(tmp, 0777);
}

#ifdef VP_LOG_HOST
static void net_init(void) {
    if (sceSysmoduleLoadModule(SCE_SYSMODULE_NET) < 0) return;
    SceNetInitParam p;
    p.memory = g_net_mem;
    p.size = sizeof g_net_mem;
    p.flags = 0;
    sceNetInit(&p);
    sceNetCtlInit();
    g_sock = sceNetSocket("vitaport_log", SCE_NET_AF_INET, SCE_NET_SOCK_DGRAM, 0);
    memset(&g_addr, 0, sizeof g_addr);
    g_addr.sin_family = SCE_NET_AF_INET;
    g_addr.sin_port = sceNetHtons(VP_LOG_PORT);
    sceNetInetPton(SCE_NET_AF_INET, VP_LOG_HOST, &g_addr.sin_addr);
}
#endif

int vp_init(const vp_config* cfg) {
    vp__store_config(cfg);
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG_WIDE);
    if (g_cfg.enable_front_touch) {
        sceTouchSetSamplingState(SCE_TOUCH_PORT_FRONT, SCE_TOUCH_SAMPLING_STATE_START);
        sceTouchGetPanelInfo(SCE_TOUCH_PORT_FRONT, &g_panel[0]);
    }
    if (g_cfg.enable_rear_touch) {
        sceTouchSetSamplingState(SCE_TOUCH_PORT_BACK, SCE_TOUCH_SAMPLING_STATE_START);
        sceTouchGetPanelInfo(SCE_TOUCH_PORT_BACK, &g_panel[1]);
    }
    if (g_cfg.enable_motion) sceMotionStartSampling();
    SceAppUtilInitParam ip;
    SceAppUtilBootParam bp;
    memset(&ip, 0, sizeof ip);
    memset(&bp, 0, sizeof bp);
    sceAppUtilInit(&ip, &bp);
    int enter = SCE_SYSTEM_PARAM_ENTER_BUTTON_CROSS;
    sceAppUtilSystemParamGetInt(SCE_SYSTEM_PARAM_ID_ENTER_BUTTON, &enter);
    g_enter_circle = enter == SCE_SYSTEM_PARAM_ENTER_BUTTON_CIRCLE;
    char dir[256];
    snprintf(dir, sizeof dir, "ux0:data/%s", g_folder);
    mkdirs(dir);
    char logp[300];
    snprintf(logp, sizeof logp, "%s/vitaport.log", dir);
    g_log = fopen(logp, "w");
#ifdef VP_LOG_HOST
    net_init();
#endif
    vp_log("vitaport: data folder %s, assets %s (%s), heap %u MiB, confirm %s", g_folder, g_assets,
           g_cfg.assets_external ? "external" : "embedded", (unsigned)(vp_mem_budget() >> 20), g_enter_circle ? "Circle" : "Cross");
    return 0;
}

void vp_shutdown(void) {
    vp_log("vitaport: peak heap use %u KiB", (unsigned)(g_peak >> 10));
    if (g_log) fclose(g_log);
    g_log = NULL;
#ifdef VP_LOG_HOST
    if (g_sock >= 0) sceNetSocketClose(g_sock);
    g_sock = -1;
#endif
}

uint32_t vp_confirm_button(void) { return g_enter_circle ? VP_CIRCLE : VP_CROSS; }

static void touch(int port, vp_touch_point* out, int* count, int max) {
    SceTouchData d;
    *count = 0;
    if (sceTouchPeek(port, &d, 1) < 1) return;
    const SceTouchPanelInfo* pi = &g_panel[port];
    float w = (float)(pi->maxAaX - pi->minAaX), h = (float)(pi->maxAaY - pi->minAaY);
    if (w <= 0 || h <= 0) return;
    for (unsigned i = 0; i < d.reportNum && *count < max; ++i) {
        vp_touch_point p;
        p.id = d.report[i].id;
        p.x = (d.report[i].x - pi->minAaX) / w;
        p.y = (d.report[i].y - pi->minAaY) / h;
        out[(*count)++] = p;
    }
}

void vp_poll(vp_input* in) {
    memset(in, 0, sizeof *in);
    SceCtrlData pad;
    memset(&pad, 0, sizeof pad);
    sceCtrlPeekBufferPositive(0, &pad, 1);
    in->buttons = pad.buttons & 0xFFFFu;
    in->lx = pad.lx;
    in->ly = pad.ly;
    in->rx = pad.rx;
    in->ry = pad.ry;
    vp__edges(in, &g_prev);
    if (g_cfg.enable_front_touch) touch(SCE_TOUCH_PORT_FRONT, in->front, &in->front_count, VP_MAX_FRONT);
    if (g_cfg.enable_rear_touch) touch(SCE_TOUCH_PORT_BACK, in->rear, &in->rear_count, VP_MAX_REAR);
    if (g_cfg.enable_motion) {
        SceMotionState m;
        if (sceMotionGetState(&m) == 0) {
            in->accel[0] = m.acceleration.x;
            in->accel[1] = m.acceleration.y;
            in->accel[2] = m.acceleration.z;
            in->gyro[0] = m.angularVelocity.x;
            in->gyro[1] = m.angularVelocity.y;
            in->gyro[2] = m.angularVelocity.z;
        }
    }
}

const char* vp_asset_path(const char* rel, char* buf, size_t n) {
    if (g_cfg.assets_external) snprintf(buf, n, "ux0:data/%s/%s/%s", g_folder, g_assets, rel);
    else snprintf(buf, n, "app0:%s/%s", g_assets, rel);
    return buf;
}

const char* vp_save_path(const char* rel, char* buf, size_t n) {
    snprintf(buf, n, "ux0:data/%s/%s", g_folder, rel);
    char parent[512];
    snprintf(parent, sizeof parent, "%s", buf);
    char* s = strrchr(parent, '/');
    if (s) {
        *s = 0;
        mkdirs(parent);
    }
    return buf;
}

const char* vp_translate(const char* p, char* buf, size_t n) {
    snprintf(buf, n, "%s", p);
    return buf;
}

void vp_log(const char* fmt, ...) {
    char msg[1024];
    va_list ap;
    va_start(ap, fmt);
    int len = vsnprintf(msg, sizeof msg - 1, fmt, ap);
    va_end(ap);
    if (len < 0) return;
    if (len > (int)sizeof msg - 2) len = (int)sizeof msg - 2;
    if (g_log) {
        fprintf(g_log, "%s\n", msg);
        fflush(g_log);
    }
#ifdef VP_LOG_HOST
    if (g_sock >= 0) {
        msg[len] = '\n';
        sceNetSendto(g_sock, msg, (unsigned)len + 1, 0, (SceNetSockaddr*)&g_addr, sizeof g_addr);
    }
#endif
}

size_t vp_mem_used(void) {
    struct mallinfo mi = mallinfo();
    size_t used = (size_t)mi.uordblks;
    if (used > g_peak) g_peak = used;
    return used;
}
size_t vp_mem_peak(void) {
    vp_mem_used();
    return g_peak;
}
size_t vp_mem_budget(void) { return &_newlib_heap_size_user ? _newlib_heap_size_user : 128u << 20; }

void vp_set_readback(vp_readback_fn fn, int w, int h) {
    (void)fn;
    (void)w;
    (void)h;
}

void vp_frame(void) {}
int vp_should_quit(void) { return 0; }
int vp_is_sim(void) { return 0; }
