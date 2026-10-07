# Memory on the Vita

## Budgets (default app)
| Pool | Budget | Used by |
|---|---|---|
| MAIN (user RW) | **256 MiB** (365 MiB with `ATTRIBUTE2=12`) | code, stacks, the newlib heap (`malloc`/`new`), sceLibc heap, vitaGL's RAM pool |
| newlib heap | **128 MiB by default** (inside MAIN) | every `malloc`/`new` |
| CDRAM | **112 MiB** | vitaGL: framebuffers, textures, buffers first (it spills to RAM when CDRAM runs out) |
| PHYCONT | 26 MiB | vitaGL / media decoders (SceAvPlayer) |
| CDLG | ~8 MiB | common dialogs (IME, message boxes) |

Sources: vita-rust book (Memory), vitasdk/newlib `sbrk.c` (the 128 MiB default; older posts say 32 MiB: outdated).

## Heap size
- Define `unsigned int _newlib_heap_size_user = 192 * 1024 * 1024;` in one C/C++ file to change the heap.
  Heap + stacks + vitaGL's RAM pool + code must stay within MAIN, or `malloc` fails / vitaGL init fails.
- Extended memory (`ATTRIBUTE2=12`): `[app] extended_memory = true` in vita.toml (VitaPort.cmake adds
  `-d ATTRIBUTE2=12` to vita-mksfoex). It's read at **install** time: reinstall the `.vpk` after changing it.
- Heap extension and extended memory are plan decisions: only when the simulation or hardware shows the default
  doesn't fit; record why in PORT_PLAN.md (unsafe.md for how this toolkit treats them).

## Measuring
- `vita scan`: decoded texture size of every image vs CDRAM, other data vs the heap.
- `vita sim`: the allocator wrapper caps `malloc`/`new` at `[sim] memory_mb` (default 128 = the default heap) and
  reports the peak (`stats.json`, `mem_peak`). The simulation doesn't count GPU memory: compare decoded textures
  against CDRAM separately (`vita assets check`). An OOM in the simulation aborts with `VITASIM OOM` (exit 1).
- On the Vita: `vp_mem_used()/vp_mem_peak()` (newlib `mallinfo`), `vglMemFree(VGL_MEM_ALL)`,
  `sceKernelGetFreeMemorySize()`; log them with `vp_log` and read them with `vita logs`.

## Texture strategies
1. **Don't upload what you don't draw**: many PC games load every texture at startup; load per level.
2. **Downscale** textures larger than they ever appear on a 960x544 screen (a 4096 skybox face shows at <1024).
3. **Compress** world textures: DXT1 (4 bpp, opaque) / DXT5 (8 bpp, alpha) via `vita assets convert`
   (`format = "dds-dxt1|dds-dxt5"`): 8x / 4x smaller than RGBA8. PVRTC/ETC1 through external encoders.
   Keep pixel art, UI and text uncompressed.
4. **16-bit formats** (RGB565/RGBA4444) halve RGBA8 where banding is acceptable.
5. **Stream** music and large levels instead of preloading.

## Other memory traps
- Thread stacks: Vita threads get the stack size you ask for; PC code that recurses deeply needs larger stacks.
- 64-bit-sized structures shrink on the 32-bit Vita: binary save files written by the PC version may not load
  unless their layout uses fixed-size types.
