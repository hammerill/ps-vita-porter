# PS Vita port plan: Lumen Drift

Written at intake (2026-10-07) and kept current. Every intake answer records the alternatives that were
declined and why. Evidence for the done criterion is in PORTLOG.md.

## Prerequisites
- Project kind: cmake (an original game, not a universal-decompiler repo). Full source: `src/`, assets drawn by
  `tools/make_art.py`.
- PC build works: `cmake -S . -B build && cmake --build build`, `./build/bin/lumen-drift --selftest` ->
  `selftest: ticks 1057 score 17 lives 0 hash 35cbc457` (2026-10-07, GCC 13.3, SDL 2.32.8 fetched by CMake).
- Language / engine: C++20 + SDL2 + OpenGL 2.1 fixed function, CMake. Supported.
- Ownership: the game is ps-vita-porter's own example (MIT); its art and sounds are drawn by code in this repo.

## Prior art
- `vita kb search "lumen drift"`: nothing (new game). `vita kb search vitagl`: the tooling notes on shaders,
  Docker and memory, used below.
- Existing Vita port: none (the game was written for this example).

## Done criterion (agreed at intake)
- [x] The `.vpk` builds (`vita build`, native and `--docker`)
- [x] Static checks pass: `vita vpk check`, `vita livearea check`, no unresolved imports
- [x] The PC simulation is playable to: **title -> a run -> pause -> remap Dash in Controls -> back -> quit**
      (`sim/title-to-play.txt`)
- [ ] Vita3K reaches that state too, if installed and able to boot the game: not installed on the build machine
      (optional level skipped, see PORTLOG.md)
- [x] Handoff: both `.vpk` flavours, the external asset folder, README install steps, the hardware checklist

## Intake answers
`vita scan --questions` drafted the questions; for this example the toolkit's author played the user's role.

### Controls
| Original action | Original binding (PC) | Vita | Notes |
|---|---|---|---|
| Move | WASD / arrows / gamepad left stick | left stick + D-pad | dead zone 0.2 |
| Dash | Space (remappable: Shift, X, J) | Square (remappable: R, L, Triangle, Cross, Circle) | the only gameplay button |
| Pause | Escape / P / gamepad Start | Start | |
| Menu confirm | Enter / gamepad A | the system confirm button (Cross or Circle) | not asked: follows the system setting |
| Menu back | Escape / Backspace / gamepad B | the system cancel button | |
| Menu navigation | Up/Down, W/S | D-pad / left stick up-down | |
| Menu click | left mouse button | front-touch tap on the item | |
- **Decision:** the table above. **Declined:** Cross for Dash (it's often the confirm button: pressing it to leave a
  menu would also dash); R for Dash (kept as an alternative in the remap list). **Why:** one action button on the
  most reachable face button; menus follow the system setting.
- **Extra actions / L2-R2-L3-R3:** none needed (5 actions). **Declined:** combos, virtual buttons. **Why:** they fit.
- **Front touch: menus only** (tap an item to choose it). **Declined:** direct interaction (touch-to-move would
  fight the stick and hide the orb under the finger), off. **Why:** the PC version clicks menu items with the mouse.
- **Rear touch: off.** **Declined:** zones as extra shoulder buttons. **Why:** nothing to map; accidental grips.
- **Gyro: off.** **Declined:** tilt steering. **Why:** a precise dodging game; tilt would clash with its feel.
- **Character/camera/cursor:** the orb moves with the left stick/D-pad; no camera; no cursor (menus use the
  D-pad or taps).

### In-game UI integration
- Vita glyphs replace key names in prompts (Dash, Select, Back), drawn by `tools/make_art.py` (original shapes,
  not Sony's art); confirm/back prompts follow the system setting.
- Remapping: the game's own Controls menu (title and pause menus) cycles the Dash button; saved in
  `ux0:data/LumenDrift/settings.txt`. **Declined:** a Start+Select overlay (the game has a menu).
- Touch hints: none (taps hit visible menu items only).
- "QUIT" is hidden on the Vita (apps close from LiveArea). **Declined:** a clean-exit Quit item.

### Resolution and scaling
- The game renders 640x480 (4:3). **Decision:** keep 640x480 logic and scale to fit the height: 725x544,
  pillarboxed (117 px black bars). **Declined:** integer x1 (640x480 centred: 88% of the height, needlessly small
  for 2x-scaled text), stretch to 960x544 (distorts the round orb), crop (cuts the HUD).
- UI/text: the game's text is drawn at 2x-6x of a 5x7 font: >= 16 px tall after scaling. No change.
- Filtering: nearest (pixel font and sprites).

### Textures and memory
- One 256x256 RGBA atlas (256 KiB decoded) and four short sounds: **no downscaling, no compression** (pixel art),
  **preload** everything. `vita scan` estimate: ~0.4 MiB of 112 MiB CDRAM / 128 MiB heap.

### Assets
- **Embedded** (`app0:assets/`): the game's own small art, one self-contained .vpk. **Declined:** external (no
  benefit for 0.4 MiB). CI also builds the external flavour to exercise that path
  (`-D VITA_ASSETS_MODE=external`, data in `ux0:data/LumenDrift/assets/`).
- Conversion: the atlas is copied as is; sound effects 44.1 kHz stereo -> 22.05 kHz mono WAV (a quarter of the size).

### Target frame rate
60 fps (light fixed-function 2D). Logic steps at a fixed 60 Hz regardless.

### App identity
- Title ID: **LMDR00001** (4 letters + 5 digits, no reserved prefix). Known-ID check: VitaDB's list API answered
  empty on 2026-10-07 and nothing else was checked; a real release would check VitaDB by hand first. **Declined:** LMND65762 (`vita scan`'s derived proposal,
  fine but less readable).
- Display name: Lumen Drift. Version: 01.00.

### Other decisions flagged by `vita scan`
- Audio: SDL audio callback mixer kept (SDL2's Vita port drives SceAudio); WAV effects.
- Saves: `settings.txt` (best score, Dash binding) in `ux0:data/LumenDrift/`.
- Quit: hidden on the Vita (see UI).
- Online, text input, videos, languages: none.

## Defaults (not asked)
- The confirm button follows the system setting (`vp_confirm_button()`, SCE_SYSTEM_PARAM_ID_ENTER_BUTTON).
- Button glyphs are original drawings (`tools/make_art.py`), never Sony's.
- Saves and config go in `ux0:data/LumenDrift/`.

## Technical plan
- Platform backend: `src/platform/platform_vita.cpp` behind the existing `platform.h`: **vitaGL** for OpenGL
  (`vglInit(0x80000)`, `vglSwapBuffers`), the **vitaport kit** for controls/touch/paths/logs, **SDL2 for audio only**
  (never SDL video: builds with vdpm `sdl2` and with the Docker image's `sdl2_vitagl`).
- Shared input mapping (`src/platform/vita_input.h`) used by the Vita backend and the PC simulation profile.
- Vita target: `cmake/VitaPort.cmake` (`vitaport_link_vita`, `vitaport_package`), `vitaport_link_sim` with `-DVITA_SIM=ON`.

### Dependencies without a Vita build
| Dependency | vdpm package? | Replacement / plan |
|---|---|---|
| SDL2 | yes (`sdl2` / `sdl2_vitagl`) | audio only |
| OpenGL 2.1 (desktop) | `vitaGL` | `#include <vitaGL.h>` on the Vita (`src/gl.h`) |
| Win32 `windows.h` (for desktop GL headers on Windows) | n/a | PC only, behind `#if defined(_WIN32)` |

### Shaders
The game has no shaders of its own (fixed function), but vitaGL generates fixed-function shaders at runtime:
**`libshacccg.suprx` is a user prerequisite** (handoff README, checklist). vitaGL's shader cache in
`ux0:data/shader_cache/` makes later boots faster.

### Memory budget
| Pool | Budget | Estimate (vita scan / simulation) |
|---|---|---|
| newlib heap (main RAM) | 128 MiB (default) | peak 6.6 MiB in `vita sim` |
| vitaGL RAM / CDRAM / phycont | defaults (`vglInit`) | one 256 KiB texture + 512 KiB legacy pool |

### Heap extension, extended memory, overclocking, unsafe
None: the numbers above leave a wide margin. Safe eboot (`unsafe = false`).

## Hardware test checklist
In README.md ("Install on a PS Vita" and "Hardware test checklist"), derived from this plan.
