# vitaGL: OpenGL on the Vita

vitaGL (Rinnegatamante, https://github.com/Rinnegatamante/vitaGL) translates OpenGL calls to `sceGxm`. vdpm ships
it (`vitaGL`); this machine's native SDK had r1488, the `vitasdk/vitasdk` Docker image r1448 (2026-10-07). Check
your version's README for what it supports; the facts below were read from the installed `vitaGL.h` and the
symbols in `libvitaGL.a`.

## Setup
- `#include <vitaGL.h>` (it declares the GL functions and enums itself: no GLEW/glad on the Vita).
- `vglInit(legacy_pool_size)`: 960x544, default pools. `legacy_pool_size` is memory for immediate-mode style
  draws (`glBegin`, client arrays): 512 KiB (`0x80000`) is a sane start.
  `vglInitExtended(pool, w, h, ram_threshold, msaa)` and `vglInitWithCustomSizes(...)` control the resolution,
  MSAA and how much CDRAM/RAM/PHYCONT vitaGL takes.
- Present: `vglSwapBuffers(GL_FALSE)` (`GL_TRUE` when a common dialog, e.g. the IME, is on screen).
- There is no shutdown call: process exit frees vitaGL's memory blocks.
- Link: `vitaGL vitashark SceShaccCgExt mathneon taihen_stub SceShaccCg_stub SceKernelDmacMgr_stub SceGxm_stub
  SceDisplay_stub SceAppMgr_stub SceCommonDialog_stub SceIme_stub SceSysmodule_stub SceLibKernel_stub m`
  (`VITAPORT_VITAGL_LIBS` in cmake/VitaPort.cmake), plus SDL's own stubs if SDL is linked.
- Memory introspection: `vglMemFree(VGL_MEM_VRAM|VGL_MEM_RAM|VGL_MEM_PHYCONT|VGL_MEM_ALL)`, `vglMemTotal(...)`.

## SDL and vitaGL
- vdpm `sdl2` is SDL2's Vita port with its GXM renderer: no `SDL_GL_CreateContext`. Using it for audio and input
  and calling `vglInit` yourself works with any SDL flavour (the example does this).
- vdpm `sdl2_vitagl` builds SDL2's video on vitaGL so `SDL_GL_CreateContext`/`SDL_GL_SwapWindow` work; it
  conflicts with `sdl2`. The Docker image ships `sdl2_vitagl`.
- SDL3 (vdpm `sdl3`, 3.4.x): check its video backend's GL support before relying on SDL's GL context.

## What's there (r1448/r1488 symbols)
Fixed-function pipeline (matrices, lighting, fog, client arrays, `glBegin/glEnd`), VBOs, FBOs
(`glGenFramebuffers`, `glBlitFramebuffer`), VAOs (`glGenVertexArrays`), `glMapBuffer(Range)`,
`glDrawArraysInstanced`, compressed textures (`glCompressedTexImage2D`: S3TC DXT1/3/5, PVRTC, ETC1), shaders
(below). Treat anything newer than GL 2.1/GLES 2 plus those extensions as "verify first": geometry, tessellation
and compute shaders don't exist on SGX; MRT, 3D textures and texture arrays need checking. `vita scan` lists
the risky features a project uses.

## Shaders
- **Offline GXP compilation needs Sony's `psp2cgc`, which isn't distributable: not an option.**
- **Runtime compilation**: vitaGL compiles shaders on the console through vitaShaRK and Sony's runtime compiler
  `libshacccg.suprx`. vitaShaRK loads `ur0:/data/libshacccg.suprx`; vitaGL also looks for
  `ur0:data/external/libshacccg.suprx`. **The user extracts it on their own Vita** (current method: PSM Runtime
  1.00, 2.00 and 2.01, then ShaRKF00D, which writes `ur0:data/libshacccg.suprx`). It's a **user prerequisite**:
  the handoff README and the hardware checklist list it; `vita tools check` doesn't need it on the PC.
- vitaGL's own fixed-function shaders are generated and compiled at runtime too: even a shader-free GL 1.x game
  needs `libshacccg.suprx`.
- **Languages**: CG natively; GLSL through vitaGL's GLSL-to-CG translator (present in r1448/r1488: `glsl_translator_*`
  symbols). Desktop GLSL (`#version 330 core` features, `layout(location=...)`) may need edits; GLSL ES 1.00 /
  GLSL 1.20 style ports most easily. Bind attribute locations explicitly.
- **Shader cache**: compiled shaders are cached in `ux0:data/shader_cache/v<N>/{v,f}/` (`vglSetShaderCachePath()`
  before `vglInit*` moves it). The first run compiles (slow), later runs load the cache.
- In the PC simulation, shaders run through the PC driver: shader compile errors specific to vitaGL show up only
  in Vita3K or on hardware. Port shaders early and keep them simple.

## Common pitfalls
- `glReadPixels`, `glFinish` and texture uploads mid-frame stall the tile-based GPU.
- Client-side arrays are copied into the legacy pool each draw: big meshes belong in VBOs.
- Non-power-of-two textures with mipmaps/repeat: test; prefer POT for compressed textures.
- `GL_QUADS` and `GL_POLYGON` work through vitaGL's immediate-mode emulation but cost CPU; triangles are better.
- Desktop-only enums (e.g. `GL_CLAMP`, `GL_TEXTURE_RECTANGLE`) may be missing: compile errors tell you.
- Viewport origin is bottom-left as in GL; the Vita framebuffer is 960x544.
