---
kind: topic
title: "vita-elf-create: 'Cannot allocate N bytes for SCE data ... segment 1 overlaps'"
family: tooling
tags: [vitasdk, vita-elf-create, linker, build]
tools: ["VitaSDK 2026.08 (vita-toolchain c527abc)", "vita 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://github.com/vitasdk/vita-toolchain/blob/master/src/vita-elf-create/sce-elf.c"]
---

# vita-elf-create: 'Cannot allocate N bytes for SCE data ... segment 1 overlaps'

> A perfectly normal program can fail to become a .velf just because of its code size: vita-elf-create appends
> its module info and import tables after the code segment, and the default linker script starts the data segment
> at the next 64 KiB boundary. If the code ends closer to that boundary than the tables need, it fails (and
> segfaults). `vita build` detects it and retries once with `-D VITAPORT_ELF_PAD=4096`.

## When to use it
A build that links fine and then dies in "Converting to Sony ELF" with that message.

## How
- The check is in `sce-elf.c` (vita-toolchain): the SCE data goes at the end of the segment holding
  `module_start`; any other segment starting inside that range is an error.
- `arm-vita-eabi-readelf -lW <elf>` shows it: here segment 0 ended at `0x8100fd98`, segment 1 started at
  `0x81010000` (0x268 bytes free) and the tables needed 1464 bytes.
- Workaround: change the code size so the boundary moves. `cmake/VitaPort.cmake` adds a used, initialised
  read-only array of `VITAPORT_ELF_PAD` bytes (`vitaport_elf_pad.c`, generated in the build folder); 4096 pushes
  the data segment to the next 64 KiB boundary.

## Gotchas
1. **It looks flag-related but isn't.** **Cause:** -O0/-O3 and `-z,nocopyreloc` all failed the same way for the
   same tiny program; only the code size matters. **Fix:** padding (or any code change) moves the boundary.
2. **It comes and goes as code grows.** **Cause:** every edit changes where the code ends. **Fix:** if it recurs,
   keep `VITAPORT_ELF_PAD=4096` in `[build] options` in vita.toml.

## Seen in
`tests/test_assets_build.py::test_native_build_of_a_minimal_project` (a two-file C program hit it).
