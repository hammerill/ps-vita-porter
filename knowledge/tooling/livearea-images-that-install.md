---
kind: topic
title: "LiveArea images that install (and the ya8 grayscale bug)"
family: tooling
tags: [livearea, sce_sys, pngquant, ffmpeg, "0x8010113D"]
tools: ["ffmpeg 6.1.1", "pngquant 2.18.0", "vita 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://gist.github.com/hammerill/64411eebf071b93396b7d310ba8d6776"]
---

# LiveArea images that install (and the ya8 grayscale bug)

> The Vita refuses a .vpk with error 0x8010113D when a LiveArea image has the wrong size or pixel format.
> `vita livearea make` produces images that install and `vita livearea check` rejects the rest; this note is the
> why behind both, based on hammerill's "LiveArea Specs" gist with its colour bug fixed.

## When to use it
Every port, when building `sce_sys/`, and whenever an install fails with 0x8010113D.

## How
- `icon0.png` 128x128, `pic0.png` 960x544, `livearea/contents/bg0.png` 840x500, `livearea/contents/startup.png`
  280x158, all 8-bit indexed PNGs; only `startup.png` may have transparency; `pic0.png` has exactly 256 colours.
- icon0/bg0: `ffmpeg ... -pix_fmt rgb24` then `pngquant`; startup: the same with `rgba`; pic0: `palettegen` +
  `paletteuse`, never pngquant.
- `template.xml`: style `a1` (startup centred) or `psmobile` (right), referencing `bg0.png` and `startup.png`.
- CMake: `vita_create_vpk(... FILE sce_sys sce_sys)`.

## Gotchas
1. **Every LiveArea image comes out gray.** **Cause:** the gist's `-pix_fmt ya8` is grayscale + alpha. **Fix:**
   `rgb24` (and `rgba` for startup.png); `vita livearea check` rejects gray+alpha PNGs by name.
2. **A flat-colour icon fails the 8-bit check.** **Cause:** pngquant writes 1-, 2- or 4-bit PNGs when there are
   few colours (measured: a single-colour image became 1-bit, a 12-colour one 4-bit). **Fix:** `vita livearea
   make` re-expands them to 8-bit with the same palette; pixels verified identical with ffmpeg rawvideo dumps.
3. **pic0 gets a tRNS chunk.** **Cause:** recent FFmpeg's `palettegen` reserves a transparent entry by default.
   **Fix:** `palettegen=max_colors=256:reserve_transparent=0`. FFmpeg's pal8 PNG always carries a 256-entry
   palette, which is what pic0 needs.
4. **Game art in LiveArea.** **Cause:** in a universal-decompiler repo the sources come from `data/`. **Fix:** treat
   `sce_sys/` and any .vpk built with it as private, like `data/`.

## Seen in
`examples/lumen-drift` (its own key art, icon and logo), `skills/port-to-vita/references/livearea.md`.
