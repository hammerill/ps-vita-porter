# PS Vita hardware, as a port sees it

Facts checked against the VitaSDK 2026.08 headers and toolchain, the vita-rust book (Memory chapter) and
Copetti's "PlayStation Vita Architecture". Numbers an app can rely on are marked as budgets, not totals.

## CPU
- **ARM Cortex-A9 MPCore, 4 cores**, ARMv7-A with Thumb-2, NEON and VFPv3 (hard float).
- **Apps get 3 cores.** Thread affinity masks: `SCE_KERNEL_CPU_MASK_USER_0/1/2` (`psp2/kernel/cpu.h`);
  `SCE_KERNEL_CPU_MASK_SYSTEM` is the system-reserved fourth core. A PC game that spawns
  `hardware_concurrency()` workers must be capped at 3 (or 2 + the main thread) on the Vita.
- Clock: apps start at 333 MHz; `scePowerSetArmClockFrequency(444)` (ScePower) is the highest stock setting
  (with `scePowerSetBusClockFrequency(222)`, `scePowerSetGpuClockFrequency(222)`,
  `scePowerSetGpuXbarClockFrequency(166)` for the GPU side). Raising clocks is a plan decision (unsafe.md):
  only when profiling shows the need. Higher clocks (500 MHz) need plugins: out of scope.
- What VitaSDK's GCC targets by default (`arm-vita-eabi-gcc -###`): `-march=armv7-a+simd -mtune=cortex-a9
  -mfpu=neon -mfloat-abi=hard`; predefined: `__vita__`, `__ARM_NEON__`, `__thumb2__`.
- **32-bit**: `sizeof(void*) == 4`, `sizeof(long) == 4` (on 64-bit Linux `long` is 8). Little-endian like x86.
- Unaligned access: `__ARM_FEATURE_UNALIGNED` covers plain 16/32-bit loads/stores only. 64-bit loads (`LDRD`),
  floats/doubles through casted byte pointers, NEON and atomics on misaligned addresses fault: use `memcpy`.

## Memory (see memory.md for the budget)
- 512 MiB LPDDR2 main memory (split by the system into MAIN, CDLG and PHYCONT) + **128 MiB CDRAM** (video).
- **A default app gets 256 MiB MAIN, 112 MiB CDRAM, 26 MiB PHYCONT and ~8 MiB CDLG.** `ATTRIBUTE2=12` in
  `param.sfo` raises MAIN to 365 MiB.
- The C heap (newlib) is **128 MiB by default**, inside MAIN; `unsigned int _newlib_heap_size_user = N;` changes it.

## GPU
- **PowerVR SGX543MP4+**, driven through `sceGxm`; OpenGL comes from vitaGL (vitagl.md), which translates to GXM.
- Tile-based deferred renderer: full-screen readbacks (`glReadPixels`), frequent render-target switches and
  mid-frame texture uploads are expensive. Batch draws; upload textures at load time.
- Maximum texture size: 4096 x 4096. Natively sampled compressed formats: S3TC/DXT (UBC1-3), PVRTC (2/4 bpp),
  ETC1 (vitaGL also declares ETC2 tokens).

## Screen
- **960 x 544**, 5 inches (OLED on the PCH-1000, LCD on the PCH-2000 "Slim"), about 220 ppi: text that is legible
  on a monitor can be too small here (scaling.md).
- 960:544 is 1.765:1, not exactly 16:9 (1.778:1): a 16:9 image is 960 x 540 with 2-pixel bars, or stretched by 0.7%.

## Inputs
- D-pad, Cross, Circle, Square, Triangle, **L, R** (the only shoulder buttons: SceCtrl reports them as
  LTRIGGER/RTRIGGER), Start, Select, PS (system), volume, power. **No L2/R2/L3/R3** on the handheld.
- Two analog sticks, 8-bit (0-255, 128 centre), `SCE_CTRL_MODE_ANALOG_WIDE` for the full range.
- **Front touchscreen**: capacitive multi-touch, up to 6 reports (`sceTouchPeek`, panel info gives the active
  area; the front panel is about 1920 x 1088 in touch units).
- **Rear touchpad**: smaller active area, up to 4 reports; under the fingers while holding the console.
- **Motion**: 3-axis accelerometer + gyroscope (+ magnetometer) through SceMotion.
- **PlayStation TV** (same software): no touch, no rear pad, no motion, DualShock controllers (which do have
  L2/R2/L3/R3, but a Vita port must not depend on them). Everything touch-only needs a button path.

## Storage partitions
| Partition | What | Port use |
|---|---|---|
| `app0:` | the installed app (`ux0:app/<TITLEID>/`), mounted read-only for the running app | embedded game data |
| `ux0:` | the memory card (or SD2Vita/USB through plugins); exFAT | `ux0:data/<name>/`: saves, config, logs, external assets |
| `ur0:` | internal user storage | `ur0:data/libshacccg.suprx` (user prerequisite), `ur0:tai/config.txt` |
| `uma0:`, `imc0:` | extra storage (USB/SD adapters, Slim internal) | never assume they exist |
| `vs0:`, `os0:`, `sa0:`, `pd0:` | system | never written |

File names on `ux0:` are case-insensitive (exFAT) but case-preserving; see filesystem.md.
