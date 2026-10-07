# PORTLOG

The journal of the Lumen Drift Vita port. Anything that isn't written here is lost at the next context
compaction.

## Status
- Phase: handoff done (hardware iteration waits for a console)
- Done criterion: see PORT_PLAN.md; evidence below
- Next step: hardware test checklist on a real Vita (README.md), then `vita kb new` if anything new is learned
- Circuit breaker: no repeated failure

## Facts (keep current)
| What | Value | Source |
|---|---|---|
| Project kind | cmake (original game) | vita init |
| PC build | `cmake -S . -B build && cmake --build build`; `./build/bin/lumen-drift --selftest` | 2026-10-07 |
| Title ID / name / data folder | LMDR00001 / Lumen Drift / ux0:data/LumenDrift/ | vita.toml |
| Assets mode | embedded (CI also builds external) | PORT_PLAN.md |
| Toolchain | VitaSDK 2026.08 native (vitaGL r1488, sdl2 2.32.8); Docker image vitasdk/vitasdk:latest (vitaGL r1448, sdl2_vitagl) | vita tools check |

## Done criterion evidence
| Item | Evidence (command, output, date) |
|---|---|
| `.vpk` builds | `vita build` -> `build OK (native, Release, 0 warning lines)`, `build-vita/lumen-drift.vpk`; `vita build --docker --build-dir build-vita-docker` -> `build OK (docker ...)` (2026-10-07) |
| Static checks | `vita vpk check build-vita/lumen-drift.vpk` -> PASS (TITLE_ID LMDR00001, APP_VER 01.00, safe 0x2F00000000000002, 5 asset files); `vita vpk check build-vita-ext/lumen-drift.vpk --assets external` -> PASS (no game files); `vita livearea check` -> PASS; `unresolved imports: none` (arm-vita-eabi-nm -u) |
| PC simulation reaches the agreed state | `vita sim --input sim/title-to-play.txt --timeout 40` -> exited 0 after ~10 s, quit by the script; screenshots title, playing, paused, controls, controls-remapped inspected (pillarbox 725x544, Vita glyphs, Dash remapped to R); peak memory 6.6 MiB of 128 MiB |
| Vita3K | not installed on the build machine (`vita tools check`: optional, missing) -> `vita emu` skipped |
| Handoff package | `build-vita/lumen-drift.vpk` (embedded), `build-vita-ext/lumen-drift.vpk` + `build-vita/assets/` (external), README.md install section + hardware checklist |

## Log
### 2026-10-07
- `vita init --kit --no-hook` (the example lives inside the toolkit's repo: no hook in the toolkit's .git).
- `vita scan`: C++/CMake, SDL2 + OpenGL 2.x fixed function (client arrays), keyboard + mouse (menus) + gamepad,
  640x480, nearest filtering, no portability findings, 0.4 MiB of assets. Intake answers in PORT_PLAN.md.
- `vita tools check`: all required tools; Vita3K, vita-parse-core optional and absent.
- Port: `src/platform/platform_vita.cpp` (vitaGL + vitaport + SDL2 audio), `src/platform/vita_input.h` (shared with
  the simulation), `src/gl.h` (vitaGL.h on the Vita), CMake `if(VITA)` branch with `vitaport_package`.
- First Vita build failed: `'vglEnd' was not declared` -> vitaGL has no shutdown call (r1448, r1488); removed.
- First simulation screenshots: no background, no pause dimming -> solid quads sampled the atlas's transparent
  space glyph; added an opaque 8x8 block to the atlas (`tools/make_art.py`, `atlas::kSolidX/Y`).
- One-shot inputs could be dropped on frames without a 60 Hz logic step -> buffered until a step consumes them.
- `vita livearea make --icon art/icon.png --pic art/keyart.png --bg art/keyart.png --startup art/logo.png` -> PASS.
- `vita assets convert`: atlas copied, 4 WAVs -> 22050 Hz mono.
- Builds and checks as in the evidence table; external flavour in `build-vita-ext/`.
