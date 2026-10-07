---
name: vita-graphics
description: Get a PC game's rendering onto the PS Vita - vitaGL (OpenGL over sceGxm) setup and linking, SDL+vitaGL combinations (sdl2 vs sdl2_vitagl), the GL subset and risky features, shaders compiled at runtime through libshacccg.suprx with vitaGL's GLSL translator and shader cache (never offline psp2cgc), Direct3D/Vulkan renderers needing a GL backend, resolution and scaling (native 960x544, lower internal resolution, pillarbox, integer scaling for pixel art), texture memory (CDRAM budget, downscaling, DXT/PVRTC/ETC1 compression with `vita assets convert`) and GPU performance on the SGX543MP4+. Use when the Vita build shows nothing/garbage, shaders fail, memory runs out, or when planning the graphics side of a port.
---

# Vita graphics

References: `port-to-vita/references/vitagl.md`, `scaling.md`, `memory.md`, `hardware.md`.

## 1. Pick the path (from `vita scan`'s graphics section)
| The game uses | On the Vita |
|---|---|
| OpenGL 1.x/2.x or GLES2 | vitaGL directly; usually little code changes |
| OpenGL 3.x core | vitaGL + GLSL translator; check every feature `vita scan` marks risky; VAOs, `glMapBuffer`, instancing exist in current vitaGL |
| SDL_Renderer | vdpm `sdl2`'s GXM renderer works without vitaGL |
| Software framebuffer | upload it as a texture each frame (vitaGL or SDL_Renderer) |
| Direct3D / Vulkan / Metal | blocker: write a GL renderer behind the platform layer first (and test it on PC) |

## 2. Set it up
- `vglInit(0x80000)` (or `vglInitExtended`) after `vp_init`; present with `vglSwapBuffers(GL_FALSE)`.
- Link `${VITAPORT_VITAGL_LIBS}` (cmake/VitaPort.cmake). With SDL: init only `SDL_INIT_AUDIO` (and joystick if
  you use it); SDL's GL context only with `sdl2_vitagl`/SDL3's GL-capable backend.
- Viewport: the framebuffer is 960x544; draw the game into `vp_fit(...)`'s rectangle (bottom-left origin for
  `glViewport`).

## 3. Shaders
- Runtime compilation only (`libshacccg.suprx` on the console: user prerequisite; vitaShaRK loads
  `ur0:data/libshacccg.suprx`). Even fixed-function rendering compiles shaders at runtime.
- GLSL goes through vitaGL's translator: prefer GLSL 1.20 / ES 1.00 style; bind attribute locations; avoid
  `#version 330 core`-only syntax or convert it. CG is native.
- First boot compiles and fills `ux0:data/shader_cache/`; later boots are faster. Mention it in the handoff.
- The PC simulation can't catch vitaGL shader errors: Vita3K/hardware do. Log `glGetShaderInfoLog` with `vp_log`.

## 4. Memory and textures
- Budget: 112 MiB CDRAM (vitaGL spills to RAM). `vita scan` estimates decoded textures; `vita assets check`
  re-checks the converted set.
- `[[assets.rule]]` with `action = "texture"`: `max_size`, `scale`, `filter = "neighbor"` for pixel art,
  `format = "dds-dxt1" | "dds-dxt5"` for world textures (load them with `glCompressedTexImage2D` and the
  `GL_COMPRESSED_RGB(A)_S3TC_DXT1/5_EXT` formats), `format = "command"` + `command = "... {in} {out}"` for
  ETC1/PVRTC encoders. Keep UI, text and pixel art lossless.

## 5. Performance
Batch draws, VBOs for static geometry, no mid-frame `glReadPixels`/uploads, fewer render-target switches, a
lower internal resolution (FBO + upscale) if the GPU is the bottleneck, 30 fps locked if 60 can't hold. Raising
clocks is a plan decision (unsafe.md), only after profiling.
