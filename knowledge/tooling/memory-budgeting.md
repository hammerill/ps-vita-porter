---
kind: topic
title: "Memory budgeting for a Vita port"
family: tooling
tags: [memory, heap, cdram, extended-memory, simulation]
tools: ["VitaSDK 2026.08 (newlib)", "vita 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://vita-rust.github.io/book/dev/mem.html", "https://github.com/vitasdk/newlib"]
---

# Memory budgeting for a Vita port

> PC games assume gigabytes. A default Vita app gets 256 MiB of main memory, 112 MiB of CDRAM, 26 MiB of
> physically contiguous RAM and ~8 MiB for dialogs, and `malloc` gets a 128 MiB newlib heap out of the main
> memory. `vita scan` estimates, `vita sim` enforces the heap cap, the hardware decides.

## When to use it
At intake (textures/streaming questions), in the technical plan, and whenever the simulation reports
`VITASIM OOM` or the console runs out.

## How
- Budgets: MAIN 256 MiB (365 MiB with `ATTRIBUTE2=12` in param.sfo, read at install time), CDRAM 112 MiB, PHYCONT
  26 MiB, CDLG ~8 MiB (vita-rust book). Stack, newlib heap and sceLibc heap all live in MAIN.
- newlib heap default: 128 MiB (`libc/sys/vita/sbrk.c` in vitasdk/newlib: `_newlib_heap_size = 128 * 1024 * 1024`
  unless `unsigned int _newlib_heap_size_user` is defined). Older forum posts say 32 MiB: outdated.
- `vita scan`: decoded texture bytes vs CDRAM, everything else vs the heap.
- `vita sim --memory <MiB>`: the kit wraps malloc/calloc/realloc/free (GNU ld `--wrap`) and new/delete, and aborts
  with `VITASIM OOM` over the cap; `stats.json` has the peak.

## Gotchas
1. **The simulation's peak is far below what the Vita needs.** **Cause:** GPU memory (textures, buffers) and shared
   libraries aren't counted, only the game's own allocations. **Fix:** compare decoded textures with CDRAM
   separately (`vita assets check`); keep a margin on the heap.
2. **malloc fails on the Vita although the heap was raised.** **Cause:** heap + stacks + vitaGL's RAM pool + code
   exceed MAIN. **Fix:** lower vitaGL's pools (`vglInitWithCustomSizes`) or the heap, or extended memory
   (plan decision, reinstall after changing it).
3. **Binary saves from the PC don't load.** **Cause:** `long`/pointer-sized fields are 4 bytes on the Vita.
   **Fix:** fixed-size types in save structures.

## Seen in
`skills/port-to-vita/references/memory.md`, `examples/lumen-drift` (peak 6.6 MiB of 128 MiB in the simulation).
