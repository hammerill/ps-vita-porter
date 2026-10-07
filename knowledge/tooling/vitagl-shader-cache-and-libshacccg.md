---
kind: topic
title: "vitaGL shaders: libshacccg.suprx, the GLSL translator and the shader cache"
family: tooling
tags: [vitagl, shaders, libshacccg, glsl, cg, shader-cache]
tools: ["vitaGL r1448 and r1488", "vitaShaRK 1.7", "VitaSDK 2026.08"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://github.com/Rinnegatamante/vitaGL", "https://consolemods.org/wiki/Vita:Installing_Libshacccg.suprx"]
---

# vitaGL shaders: libshacccg.suprx, the GLSL translator and the shader cache

> Vita homebrew can't compile shaders offline (Sony's `psp2cgc` isn't distributable), so vitaGL compiles them on
> the console through vitaShaRK and Sony's runtime compiler `libshacccg.suprx`, which every user must extract on
> their own console. This note records where the pieces look for files, read from the libraries themselves.

## When to use it
Planning a port's shader strategy, writing the handoff README, or when a vitaGL app shows nothing on hardware.

## How
- The user prerequisite: PSM Runtime 1.00, 2.00, 2.01, then ShaRKF00D, which writes `ur0:data/libshacccg.suprx`.
- vitaShaRK 1.7 loads `ur0:/data/libshacccg.suprx`; vitaGL r1448/r1488 also contain `ur0:data/external/libshacccg.suprx`.
- GLSL is translated to CG by vitaGL (the `glsl_translator_*` symbols are in both versions); CG is native.
- Compiled shaders are cached under `ux0:data/shader_cache/v<N>/v/` (vertex) and `.../f/` (fragment);
  `vglSetShaderCachePath()` before `vglInit*` moves the cache.
- Even fixed-function GL needs the compiler: vitaGL generates its FFP shaders at runtime.

## Gotchas
1. **A vitaGL app shows a black screen or exits at boot on a fresh console.** **Cause:** `libshacccg.suprx` isn't
   extracted. **Fix:** list it as a prerequisite in the handoff README and the hardware checklist; log a clear
   message if shader compilation fails.
2. **The first boot is slow, later boots fast.** **Cause:** the cache is filled on first use. **Fix:** tell the
   user; don't treat the first boot's frame times as the performance baseline.
3. **Shader bugs never show in the PC simulation.** **Cause:** the simulation compiles through the PC's GL driver.
   **Fix:** keep shaders close to GLSL 1.20 / ES 1.00, bind attribute locations explicitly, check
   `glGetShaderInfoLog` output in `vitaport.log` on Vita3K/hardware.

## Seen in
`skills/port-to-vita/references/vitagl.md`, `examples/lumen-drift` (fixed-function GL through vitaGL).
