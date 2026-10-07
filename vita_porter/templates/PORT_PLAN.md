# PS Vita port plan: {name}

Written at intake and kept current. Every intake answer records the **alternatives that were declined and
why**. The done criterion is fixed once agreed; evidence for it goes in PORTLOG.md.

## Prerequisites
- Project kind: {kind} <!-- ud: a universal-decompiler reconstruction; read DECOMP_PLAN.md and decomp/progress.json -->
- Complete source and a working PC build: <!-- command run + result, date -->
- Language / engine supported (C/C++, CMake): <!-- yes / added a CMake build / refused (reason) / user insisted (logged) -->
- The user owns the game: <!-- confirmed on date -->

## Prior art
<!-- vita kb search results; existing Vita ports (VitaDB, GitHub, forums) checked on <date> with links; what we reuse -->

## Done criterion (agreed at intake)
- [ ] The `.vpk` builds (`vita build`)
- [ ] Static checks pass: `vita vpk check`, `vita livearea check`, `vita-elf-create` reports no unresolved imports
- [ ] The PC simulation (`vita sim`) is playable to: <!-- agreed state, e.g. "the end of the first level" -->
- [ ] Vita3K reaches that state too, if it's installed and can boot the game (its compatibility limits are not port bugs)
- [ ] Handoff: the `.vpk`, the external asset folder (if any), README install steps, the hardware test checklist

## Intake answers
<!-- One subsection per topic. Format for each decision:
     - **Decision:** ...   - **Declined:** ... (why)   - **Why:** grounded in the game (genre, original controls, UI, vita scan) -->

### Controls
<!-- every original action -> Vita button/stick (two sticks, D-pad, L/R only; how L2/R2/L3/R3 actions are recovered),
     front touch, rear touch (or off), gyro (or off), character/camera/cursor control -->
| Original action | Original binding | Vita | Notes |
|---|---|---|---|

### In-game UI integration
<!-- Vita button glyphs (original drawings or CC0, never Sony's), the remapping menu, touch-zone hints -->

### Resolution and scaling
<!-- internal resolution, aspect handling (letterbox/pillarbox, stretch, crop), UI/text scale for a 5-inch screen, filtering -->

### Textures and memory
<!-- downscaling policy, compression format (DXT/UBC, PVRTC, ETC1, none), streaming vs preloading, from vita scan's estimate -->

### Assets
- Mode: {assets} <!-- embedded in the .vpk (app0:) | external in ux0:data/{data_folder}/ -->

### Target frame rate

### App identity
- Title ID: {title_id} <!-- checked against known IDs on <date> -->
- Display name: {name}
- Version: 01.00

### Other decisions flagged by `vita scan`
<!-- audio formats, saves, language, how to quit, online features to strip, ... -->

## Defaults (not asked)
- The confirm button follows the system setting (Cross or Circle) through the system parameter API.
- Button glyphs are original drawings or CC0 assets, never Sony's.
- Saves and config go in `ux0:data/{data_folder}/`.

## Technical plan
- Platform backend: SDL's Vita port (audio, input) + vitaGL (OpenGL), behind the existing platform layer
- Vita target: VitaSDK toolchain file, `platform/vita/` backend, `vita_create_self` / `vita_create_vpk(... FILE sce_sys sce_sys)`

### Dependencies without a Vita build
| Dependency | vdpm package? | Replacement / plan |
|---|---|---|

### Shaders
Runtime compilation through vitaGL with `libshacccg.suprx` (user prerequisite on the console) and vitaGL's
shader cache. Offline GXP compilation needs Sony's non-distributable `psp2cgc`: not an option.

### Memory budget
| Pool | Budget | Estimate (vita scan / profiling) |
|---|---|---|
| newlib heap (main RAM) | | |
| vitaGL RAM / CDRAM / phycont | | |

### Heap extension, extended memory, overclocking, unsafe
<!-- Only if analysis or profiling shows they're needed: record why, and that unsafe implies the unsafe flag. Default: none. -->

## Hardware test checklist (filled in at handoff)
<!-- Derived from this plan: install, LiveArea, boot, controls (every mapping), touch/rear/gyro, glyphs and confirm button,
     scaling, frame rate, audio, saves, suspend/resume, quitting, memory over a long session -->
