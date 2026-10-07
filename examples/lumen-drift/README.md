# Lumen Drift (ps-vita-porter's worked example)

A small original arcade game (C++20, SDL2, OpenGL 2.1 fixed function): steer a glowing orb, collect sparks,
dodge drifting shards, dash out of trouble. Every asset is drawn by `tools/make_art.py`; no third-party art.
It was written as a PC game and then ported to the PS Vita with ps-vita-porter's workflow, in the same repo:
`PORT_PLAN.md` (the intake and the plan), `PORTLOG.md` (the journal and the evidence), `vita.toml`, the vitaport
kit in `platform/vita/vitaport/` and `cmake/VitaPort.cmake`, LiveArea in `sce_sys/` made from its own art.

## Build on PC
```bash
cmake -S . -B build && cmake --build build        # SDL2 is fetched and built if it isn't installed
./build/bin/lumen-drift                           # play (run from this folder: it reads assets/)
./build/bin/lumen-drift --selftest                # 2 minutes of scripted play, no window
```
Controls: WASD/arrows move, Space dash (remappable), Esc pause, Enter/click in menus; a gamepad works too.

## The Vita port, as the agent ran it
```bash
vita scan                                  # intake questions with recommendations
vita tools check
vita livearea make --icon art/icon.png --pic art/keyart.png --bg art/keyart.png --startup art/logo.png
vita sim --input sim/title-to-play.txt     # PC "Vita simulation": 960x544, Vita controls, memory cap, screenshots
vita build                                 # embedded assets -> build-vita/lumen-drift.vpk
vita vpk check build-vita/lumen-drift.vpk
vita build --build-dir build-vita-ext -D VITA_ASSETS_MODE=external      # external assets flavour
vita vpk check build-vita-ext/lumen-drift.vpk --assets external
vita emu --shot                            # Vita3K, if installed
```
CI (`.github/workflows/test.yml`, job `example`) builds the PC target on Ubuntu and Windows and both `.vpk`
flavours in the `vitasdk/vitasdk` Docker image, then runs `vita vpk check` and `vita livearea check`.

## Install on a PS Vita
Prerequisites on the console:
- HENkaku/Ensō and VitaShell (or another .vpk installer).
- **`libshacccg.suprx`** extracted on your own Vita: vitaGL compiles its shaders at runtime. Current method:
  install PSM Runtime 1.00, 2.00 and 2.01, then run ShaRKF00D; it writes `ur0:data/libshacccg.suprx`.

Install:
1. Copy `lumen-drift.vpk` to the Vita (USB or FTP in VitaShell) and install it.
2. External-assets flavour only: copy the contents of `build-vita/assets/` to `ux0:data/LumenDrift/assets/`.
3. Launch "Lumen Drift" from LiveArea. The first boot compiles shaders (slower); later boots use the cache in
   `ux0:data/shader_cache/`.

Vita controls: left stick/D-pad move, Square dash (remappable in Controls), Start pause, the system's confirm
and cancel buttons in menus, tap menu items on the touchscreen. Settings and the best score are in
`ux0:data/LumenDrift/settings.txt`; the log is `ux0:data/LumenDrift/vitaport.log`.

## Hardware test checklist
Derived from PORT_PLAN.md. Tick each item on a real console.
- [ ] `libshacccg.suprx` present in `ur0:data/`
- [ ] the .vpk installs without an error (0x8010113D would mean a bad LiveArea image)
- [ ] LiveArea: the bubble shows the orb icon; the LiveArea page shows the key art with the "LUMEN DRIFT" logo;
      colours match `art/` (not gray); the name under the bubble is "Lumen Drift"
- [ ] boots to the title screen; the game sits in a 4:3 area with black bars left and right
- [ ] title menu: D-pad/stick up-down moves the selection; confirm starts; "QUIT" isn't shown
- [ ] confirm/cancel follow the system setting: try with Cross as enter, then Circle (Settings > System)
- [ ] touch: tapping START/CONTROLS works; the rear pad does nothing; tilting does nothing
- [ ] play: the orb follows the left stick and the D-pad; Square dashes; sparks score; shards cost lives
- [ ] Start pauses; the pause menu resumes, opens Controls, returns to the title
- [ ] Controls: Dash cycles SQUARE -> R -> L -> TRIANGLE -> CROSS -> CIRCLE with matching glyphs; the choice is
      used in play and survives a restart
- [ ] the best score survives a restart
- [ ] sound effects play (pickup, hit, dash, menu), no crackle
- [ ] holds 60 fps during play
- [ ] suspend with the power button mid-run, resume: game and sound continue
- [ ] a 30-minute session: no slowdown or crash
- [ ] external flavour: with `ux0:data/LumenDrift/assets/` missing, the log names the missing file (no silent hang)
If something fails: `vita logs --ftp` (fetches the log) or `vita core` (crash dump), and hand them to the agent.

## Files
| Path | What |
|---|---|
| `src/` | the game: `game.cpp` (logic), `render.cpp` (GL), `audio.cpp` (SDL mixer), `platform/` (PC/sim and Vita backends) |
| `tools/make_art.py` | draws `assets/` and `art/` (font, sprites, button glyphs, sounds, key art) |
| `sim/title-to-play.txt` | the simulation script for the done criterion |
| `sce_sys/` | LiveArea, made by `vita livearea make` from `art/` |
| `platform/vita/vitaport/`, `cmake/VitaPort.cmake` | the vitaport kit (`vita init --kit`) |
