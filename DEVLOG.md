# DEVLOG

The build journal of ps-vita-porter itself: decisions, tool substitutions, what failed and why, the next
step. Newest entries at the bottom of each day.

## Status
- Phase: initial build (see the acceptance checklist in the original brief, mirrored at the end of this file)
- Next step: see the last entry

## 2026-10-07

### Study of the reference projects
- Cloned outside the repo (session scratchpad): universal-modder `6c02e77` (2026-10-06) and
  universal-decompiler `57ce0bb` (2026-10-07).
- universal-decompiler (`ud`) already mirrors universal-modder (`um`) and carries its MIT notice on the derived
  files (`bin/ud`, `hooks/add-to-path.sh`, `ud/cli.py`, `ud/common.py`, `ud/kb.py`, parts of `ud/publish.py`,
  the skill-copy and PATH-hook tests). ps-vita-porter follows `ud`'s layout one to one: skills in `skills/`
  with real copies in `.claude/skills` and `.agents/skills` (`scripts/sync_skills.py` + a test), one CLI module
  per group with `register(sub)` and a docstring that doubles as `--help`, a TOML tool registry, SessionStart
  PATH hook only, no MCP server, `knowledge/` with TEMPLATE/INDEX/index.json, `uv` + hatchling, ruff.
- Files derived from `um` through `ud` keep the universal-modder notice in their header and are listed in
  `NOTICE`. Files adapted from `ud` (same author, MIT) are listed there too.

### Command name `vita`
- Checked VitaSDK 2026.08 (`$VITASDK/bin`, built 2026-08-25): binaries are `arm-vita-eabi-*`, `vita-elf-create`,
  `vita-elf-export`, `vita-libs-gen`, `vita-libs-gen-2`, `vita-make-fself`, `vita-makepkg`, `vita-mksfoex`,
  `vita-nid-check`, `vita-pack-vpk`, `psp2rela`, `vdpm`, `vdpm-channel`. **No binary is named `vita`**, so the
  CLI name doesn't clash. The Python module is `vita_porter` (not `vita`) so `python -m vita_porter` can't
  shadow anything either. A test (`tests/test_repo.py`) keeps a list of the SDK's binary names and asserts
  that `vita` is not among them.

### Facts checked against current sources (not memory)
- **Vita3K command line** (`vita3k/config/src/config.cpp`, master, 2026-10-07): positional `content-path` installs
  and runs a `.vpk`/`.zip`; `-r/--installed-path <TITLEID>` runs an installed app; `-S/--self`; `-B/--backend-renderer
  OpenGL|Vulkan`; `-F/--fullscreen`; `-c/--config-location`; `-l/--log-level 0-6`; `-A/--archive-log`; `-w`
  keep config; `-v/--version`. Releases: `continuous` (build 4134, 2026-10-06) ships `Vita3K-x86_64.AppImage`,
  `windows-latest.zip`, `ubuntu-latest.zip`, `macos-latest.dmg`. Pref path with ux0: Windows
  `%APPDATA%/Vita3K/Vita3K`, Linux `~/.local/share/Vita3K/Vita3K`, macOS `~/Library/Application Support/Vita3K`.
  Firmware + font firmware must be installed by the user.
- **vitacompanion** (devnoname120/vitacompanion README): FTP on 1337, commands on TCP 1338, `;`-separated:
  `launch <TITLEID>`, `quit <TITLEID>|all`, `reboot`, `screen on|off`, `promote <dir>` (installs an *extracted*
  app directory, not a `.vpk`), `press/release`, `nosleep`, `version`. **`promote` is only in the development
  tree**: the latest release, 1.07 (2026-09-16), lacks it and answers `Error: Unknown command.`; both have `help`
  (one command per line). `vita deploy --vpk --yes` sends `help` first and, without `promote`, uploads the `.vpk`
  as is to `ux0:<name>.vpk` for the user to install with VitaShell (a dry run can't know, so it shows the promote
  plan plus a note). **There is no `destroy` command** in the
  current README (older forks had it) -> `vita kill` sends `quit <TITLEID>`.
- **libshacccg.suprx**: current community method (Vita Troubleshooting Guide, consolemods wiki): install PSM
  Runtime 1.00, 2.00, 2.01, install ShaRKF00D.vpk, run it; it writes `ur0:data/libshacccg.suprx`.
- **vita-parse-core** (xyzz): Python **2**, `python2 main.py <core.psp2dmp> <app.elf>`, needs the unstripped ELF and
  `arm-vita-eabi-objdump/addr2line` on PATH. No maintained Python 3 port found (forks isage/CreepNT/... are old or
  unchanged) -> registered as an optional tool; `vita core` fetches and decompresses the dump itself and calls
  vita-parse-core if it is configured.
- **Docker**: `vitasdk/vitasdk` tags updated 2026-09-25: `latest` (full, ~1.6 GB, all ~130 packages),
  `minimal` (core only), `*-non-root`. CI uses `latest`.
- **newlib heap** (vitasdk/newlib `libc/sys/vita/sbrk.c`, current): default heap **128 MiB** unless the program
  defines `unsigned int _newlib_heap_size_user`. (Older posts say 32 MiB: outdated.)
- **Extended memory**: `ATTRIBUTE2=12` in `param.sfo` (read at install time; reinstall needed). Set through
  `VITA_MKSFOEX_FLAGS` (`-d ATTRIBUTE2=12`) because `vita_create_vpk` has no option for it.
- **Safe vs unsafe eboot**: `vita_create_self` passes `-s` (safe) unless `UNSAFE` is given. Empirically, with
  `vita-make-fself` from this SDK the only difference is the app-info authid (u64 at the offset stored at
  0x38 of the SELF, 0x80 here): `0x2F00000000000002` safe, `0x2F00000000000001` unsafe. `vita vpk check` reads it.
- **vdpm** (2026.08, pacman-based): installed here: `sdl2 2.32.8`, `vitaGL r1488`, `vitaShaRK 1.7`,
  `SceShaccCgExt`, `libmathneon`, `taihen`. Available: `sdl3 3.4.16`, `sdl2_vitagl` ("SDL2 with the vitaGL video
  backend, for projects that need OpenGL"), `sdl2_mixer`, `sdl2_image`, `libpng`, `libogg`, ...
- **vitaGL API** (installed `vitaGL.h`): `vglInit(legacy_pool_size)`, `vglInitExtended(pool, w, h, ram_threshold,
  msaa)`, `vglSwapBuffers(GLboolean has_commondialog)`, `vglSetShaderCachePath()` (default `ux0:data/shader_cache`,
  needs `HAVE_SHADER_CACHE=1`), memory types `VGL_MEM_VRAM/RAM/PHYCONT/BUDGET/EXTERNAL`, `vglMemFree/vglMemTotal`.
  Compressed formats declared: S3TC DXT1/3/5, PVRTC 2/4bpp v1/v2, ETC1.
- **VitaDB**: the list endpoint VitaDB-Downloader uses is `https://www.rinnegatamante.eu/vitadb/list_hbs_json.php`.
  On 2026-10-07 it answered HTTP 200 with `[]` (empty) from here, and `rinnegatamante.it` is a parked domain.
  -> the title-ID / existing-port lookup is best effort: an empty or failed answer is reported as "unknown",
  never as "no conflict".

### The Docker image differs from a native install
- `vitasdk/vitasdk:latest` (digest `fd82d88f…`, VitaSDK built 2026-08-25, `VITASDK=/usr/local/vitasdk`, runs as root,
  CMake 3.28.3, ninja, make, python3; **no ffmpeg/pngquant**) ships **`sdl2_vitagl`** (SDL2 2.32.8 built with the
  vitaGL video backend) and **vitaGL r1448**, plus sdl3 3.4.16. The native SDK on this machine has plain **`sdl2`**
  and vitaGL **r1488**. The two `sdl2` flavours conflict in vdpm.
- Decision for the example and the kit: on Vita, render through vitaGL directly (`vglInit*` + `vglSwapBuffers`)
  and use SDL only for audio and (optionally) gamepads, never SDL's video subsystem. That builds and runs
  with either SDL2 flavour. Projects that want `SDL_GL_CreateContext` on Vita need `sdl2_vitagl` (or SDL3) and
  `vita scan`/the skill say so.
- `vita build --docker` runs the container as the calling user (`-u uid:gid`, `HOME=/tmp`) so build outputs in
  the bind mount are not root-owned. LiveArea image tools (ffmpeg, pngquant) run on the host, never in the container.

### LiveArea pipeline: pngquant writes low bit depths
- Measured with ffmpeg 6.1.1 and pngquant 2.18.0: ffmpeg `-pix_fmt rgb24` -> pngquant gives an **8-bit** 256-colour
  indexed PNG for a photo-like source, but a **1-bit** (1 colour) or **4-bit** (12 colours) indexed PNG for flat
  art. The spec requires 8 bits per channel (the install fails with 0x8010113D otherwise). pngquant has no option
  to force 8 bits -> `vita livearea make` re-expands 1/2/4-bit indexed PNGs to 8-bit in pure Python (PNG unfilter +
  repack, same PLTE and tRNS); verified pixel-identical with ffmpeg rawvideo dumps for 1- and 4-bit cases.
- `palettegen` reserves a transparent palette entry by default in recent FFmpeg (-> tRNS = alpha in pic0):
  `vita livearea make` passes `reserve_transparent=0`. ffmpeg's pal8 PNG always has a 256-entry PLTE: exactly what
  pic0 needs.

### "No unresolved imports"
- A program referencing a function that no stub provides doesn't link (`undefined reference`) unless linked
  with `--unresolved-symbols=ignore-all` / weak stubs; then **`vita-elf-create` stays silent and exits 0** (only
  `-v` shows the relocation). `arm-vita-eabi-nm -u <elf>` lists it as `U` (the toolchain's own weak `w` entries
  such as `_newlib_heap_size_user` are fine). -> `vita build` runs `nm -u` on the ELF and fails on any `U`, and
  also scans the log for vita-elf-create errors ("Unable to relocate", "not found").
- `vita.toolchain.cmake` sets `VITA True` and `CMAKE_SYSTEM_NAME Generic`: CMake projects branch on `if(VITA)`.

### Memory budget facts (for memory.md, `vita scan` and the kit)
- vita-rust book (Memory chapter), consistent with the WoWee port's notes: by default an app gets **256 MiB MAIN,
  112 MiB CDRAM, 26 MiB PHYCONT, ~8 MiB CDLG**; `-d ATTRIBUTE2=12` (vita-mksfoex) raises MAIN to **365 MiB**. Stack,
  newlib heap and sceLibc heap all live in MAIN. Hardware: 512 MiB LPDDR2 + 128 MiB CDRAM (Copetti, PlayStation
  Vita Architecture).
- Consequences used throughout: the PC simulation's default cap is the newlib heap (128 MiB) because that's what
  `malloc` can actually get without `_newlib_heap_size_user`; `vita scan` compares decoded textures against
  CDRAM 112 MiB (+ what vitaGL may spill into RAM) and everything else against the heap.

### vdpm package snapshot
- `vdpm search ""` on 2026-10-07 (VitaSDK 2026.08 channel): 134 packages; the snapshot used by `vita scan` lives in
  `vita_porter/deps.toml` ([vdpm] packages). Notable absences: plain Lua (luajit exists), SQLite, SDL3_mixer, GLFW,
  SFML, raylib, Qt, FMOD, BASS, Wwise, Steamworks.

### The kit, the simulation profile and the example (Lumen Drift)
- **vitaport kit** (`vita_porter/kit/`, copied by `vita init --kit`): one C API (`vitaport.h`) with two backends:
  `vitaport_vita.c` (SceCtrl/SceTouch/SceMotion/SceAppUtil, app0:/ux0:data paths, log file, optional UDP log) and
  `vitaport_sim.c` (SDL2 or SDL3 input state, path translation, scripted input, PNG screenshots through a readback
  callback, stats JSON) + `vitaport_alloc.cpp` (the memory cap). The game keeps its own window/renderer; the kit
  only owns what differs on the Vita. Compiled with `-Wall -Wextra` against VitaSDK 2026.08: no warnings.
- **Memory cap**: GNU ld `--wrap=malloc,calloc,realloc,free` + `malloc_usable_size` (counts the game's own C and
  C++ allocations; shared libraries excluded), new/delete only on MSVC/Apple. Frees of memory allocated outside the
  wrap (e.g. libc's strdup) can't underflow the counter (clamped). Default cap 128 MiB = the default newlib heap.
- **Sim controls** use Vita3K's default keyboard layout (arrows, WASD, IJKL, Z/X/C/V, Q/E, Enter, Backspace) so
  testers learn one layout; rear touch = mouse + Left Alt, gyro = numpad.
- **Scripted screenshots** are taken in `vp_frame()` (right before present), not while polling input: reading back
  during the poll would capture a half-built or previous frame.
- **Gotcha (example)**: solid quads sampled the atlas's transparent space glyph and vanished (no background, no
  pause dimming in the first simulation screenshots). Fixed with an opaque 8x8 block in the atlas.
- **Gotcha (example)**: one-shot inputs could be lost on frames where the 60 Hz logic doesn't step (high-refresh
  displays): they're now buffered until a step consumes them.
- **vitaGL has no shutdown call** (`vglEnd` doesn't exist in r1448 or r1488): the process exit frees its blocks.
- Verified on 2026-10-07 (this machine: WSL2 Ubuntu 24.04, GCC 13.3, VitaSDK 2026.08 native + Docker image):
  PC build + `--selftest`; `vita sim` with a 8.5 s input script (title -> play -> pause -> controls remap -> quit),
  5 screenshots inspected, peak 6.6 MiB of 128 MiB; `vita livearea make/check` PASS; `vita build` native (embedded),
  native with `-D VITA_ASSETS_MODE=external` in a second build folder, and `--docker`: all three `vita vpk check`
  PASS, no unresolved imports, 0 warnings.

### `vita scan` false positives found on the example (fixed)
- The SIMD include regex matched `<windows.h>` (`w` + `\w*`). Now it lists the real intrinsics headers.
- `.d` make-dependency files in extra build folders were counted as D sources: folders with `CMakeCache.txt`,
  `vita-build.log` or `.vita-backend` are skipped, and so is the vitaport kit (it's the port's code, not the game's).
- "platform" (as in `platform::`) made every project a "platformer": the genre keywords no longer include it.
- Integer scaling is recommended only when it fills >= 90% of the 544 lines (640x480 at 1x fills 88%: fit-to-height
  with nearest filtering is recommended instead).

### More facts checked in the libraries themselves
- **libshacccg paths**: vitaShaRK 1.7 (`libvitashark.a`) loads `ur0:/data/libshacccg.suprx`; vitaGL r1448 and r1488
  also contain `ur0:data/external/libshacccg.suprx`. Shader cache strings: `ux0:data/shader_cache/v%d/{v,f}/...`.
  Both vitaGL builds contain the GLSL translator (`glsl_translator_*`), VAOs, `glMapBuffer(Range)`,
  `glDrawArraysInstanced`, `glBlitFramebuffer`, `glCompressedTexImage2D`.
- **Vita3K + vitaGL**: an older vitaGL fork's README had a `HAVE_VITA3K_SUPPORT` build flag; the current vitaGL README
  doesn't mention Vita3K at all. Whether vdpm's vitaGL boots in Vita3K is unverified (no Vita3K here): the
  Vita3K note says so and asks the next agent to check.
- CPU masks (`psp2/kernel/cpu.h`): `SCE_KERNEL_CPU_MASK_USER_0/1/2` + `SCE_KERNEL_CPU_MASK_SYSTEM` -> 3 cores for apps.
  VitaSDK GCC defaults: `-march=armv7-a+simd -mtune=cortex-a9 -mfpu=neon -mfloat-abi=hard`, `long`/pointers 4 bytes.

### vita-elf-create segment overlap (found by a test)
- A two-file C test project failed in "Converting to Sony ELF": `Cannot allocate 1464 bytes for SCE data at end of
  segment 0; segment 1 overlaps` + a segfault. Cause (vita-toolchain `sce-elf.c`): the SCE tables are appended
  after the code segment and the data segment starts at the next 64 KiB boundary (default linker script,
  `DATA_SEGMENT_ALIGN(0x10000, 0x10000)`); the code ended 0x268 bytes below it. Not flag-related (-O0/-O3,
  nocopyreloc all fail). Fix: `VITAPORT_ELF_PAD` in VitaPort.cmake (a used .rodata array) and `vita build` retries
  once with 4096 when it sees the message. Field note: `knowledge/tooling/vita-elf-create-segment-overlap.md`.

### Bounded build parallelism (reported from a Zuma Deluxe port on WSL)
- `vita build` and `vita sim` ran `cmake --build <dir> --parallel` with no number. Checked with CMake 3.28.3 and a
  wrapper make: a bare `--parallel` gives `make -f Makefile -j` (unlimited) and ignores `CMAKE_BUILD_PARALLEL_LEVEL`
  (no `--parallel` gives `-j3` with it set to 3). About 500 SDL3 and libopenmpt files at once took WSL (7.6 GiB)
  down twice and left a truncated `cmake_pch.h.gch`.
- Now always `--parallel N`: `--jobs`, `[build] jobs`, `$CMAKE_BUILD_PARALLEL_LEVEL`, else min(CPUs, MemAvailable
  GiB). The middle two are lowered to fit 700 MiB per job; `--jobs` is obeyed with a warning.
- Builds run in their own process group with a watchdog (`[build] timeout_min` 120, `stall_min` 15; 0 = off). A
  timeout, a stall or Ctrl+C kills the group, plus the named container for Docker (`docker kill`; killing the client
  doesn't stop the container). Verified against a sleeping container.
- `build-vita/.vita-build-running` (holding the PID) is left behind when a build never finished. The next build deletes
  the precompiled headers it may have half-written, and refuses to start if that PID is still a live vita process.
  PCH files that start without `gpch`/`CPCH` are deleted, and so are all of them after a `-Winvalid-pch` build.
- Not done: preferring Ninja automatically. An existing build dir can't change generator without `--fresh`, and with a
  bounded `-j` Make is safe. `docker run --memory` isn't set either: Docker Desktop's VM already shares WSL's memory.

### Packaging and CI checks run locally
- `uv tool install .` into a scratch tool dir: `vita --version`, `vita tools list`, `vita init --kit` (the wheel carries
  templates, kit, tools.toml, deps.toml, ps1/), `vita scan`, `vita vpk check` all work.
- The CI jobs replayed from a fresh clone: `example-vpk` (livearea check, assets convert/check, `vita build --docker`
  for both modes, both `vita vpk check`, publish check) and the Linux half of `example-pc` (PC + `-DVITA_SIM=ON` builds,
  selftest). **Not run here: the Windows legs** (MSVC builds of the example and the kit's simulation sources, the
  Windows test job). The example was hardened for them (`SDL_MAIN_HANDLED` + `SDL_SetMainReady`, no SDL2main,
  `NOMINMAX`), but the first CI run is the real check.
- The example's PC simulation runs vsync-less under WSLg (674 fps): fps numbers from WSL are not meaningful.

## Acceptance checklist (from the brief), status 2026-10-07
- [x] New, non-fork repo; layout as §3; agent manifests; skill copies in sync (script + test).
- [x] `vita` installs via `uv tool install git+…` (verified with a local `uv tool install .`), via the plugin manifests,
      via clone (`bin/vita`); SessionStart hook puts it on PATH (test); no clash with VitaSDK binaries (checked + test).
- [x] Every §5.1 command exists, has `--help` with examples, `--json` where it reports, and is tested
      (94 tests; device commands against a fake vitacompanion; Vita3K with a fake binary).
- [x] `port-to-vita` + the 5 companion skills + share-field-notes; all 11 references written.
- [x] Intake questions and recommendation logic documented in `vita-recon`; `vita scan` emits them.
- [x] Example builds as PC and as `.vpk` (CI workflow written and replayed locally on Linux/Docker; Windows legs
      pending the first CI run), passes `vita vpk check` and `vita livearea check`.
- [x] README (inspiration, no affiliation, relation with universal-decompiler, end-user prerequisites); NOTICE lists
      derived files; MIT.
- [x] This DEVLOG records the decisions and substitutions.
- Not verified anywhere: real hardware (no Vita here) and Vita3K (not installed): `vita deploy/launch/kill/logs/core`
  are tested against fakes only; vitacompanion `promote` with an FTP-uploaded folder is untested on a console.
