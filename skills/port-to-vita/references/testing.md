# Testing without a Vita, then with one

Three levels before any hardware, all best effort, all automated. **Never stop to ask the user to test an
intermediate build on hardware.**

## Level 1: static checks
- `vita build` (native or `--docker`): exit 0, a `.vpk` produced, **no unresolved imports** (it runs
  `arm-vita-eabi-nm -u` on the ELF: every `U` symbol is an import nothing provides; `vita-elf-create` stays
  silent about them when the link allowed it).
- `vita vpk check build-vita/<game>.vpk`: structure, `param.sfo` (title ID, APP_VER, ATTRIBUTE2), safe/unsafe vs
  vita.toml, LiveArea images, assets present (embedded) or absent (external).
- `vita livearea check`.
- The PC build still builds and runs (every commit).

## Level 2: the PC simulation (`vita sim`)
The PC build with `-DVITA_SIM=ON` and the vitaport kit: 960x544, Vita controls, Vita paths, the memory cap.
- Script the agreed path: `vita sim --input sim/<scenario>.txt --timeout 120`. Commands:
  `press|release|tap <button> [ms]`, `lstick|rstick <x> <y>`, `touch|rtouch <x> <y>`, `untouch|unrtouch`,
  `gyro <x> <y> <z>`, `shot <name>`, `quit` (buttons: cross circle square triangle l r start select up down left
  right confirm cancel; `confirm`/`cancel` follow `--enter cross|circle`).
- **Look at the screenshots** (scaling, bars, text size, glyphs), read `stats.json` (frames, fps, `mem_peak` vs
  `mem_budget`, `oom`) and `vitaport.log`.
- Run once with `--enter circle` (Japanese-style confirm) and once with a tighter `--memory` to see the margin.
- Validates: control mapping, UI, scaling, file paths and saves, memory decisions. It does **not** validate
  vitaGL's shader compiler, GPU performance or Vita-only APIs.

## Level 3: Vita3K (`vita emu`), if installed
- `vita emu --shot --timeout 60`: installs and runs the `.vpk`; copies `vita3k.log` and the app's
  `vitaport.log` from Vita3K's virtual `ux0:`.
- Vita3K's compatibility limits are not port bugs: if it can't boot the game, log what you saw and move on. If it
  boots, it should reach the agreed state too (the done criterion).

## Done criterion evidence (PORTLOG.md)
One row per item: the command, the result (exit code, PASS line), screenshot paths, date.

## The real-hardware test checklist (handoff template)
Fill it from PORT_PLAN.md; one checkbox per decision.
```
Prerequisites on the console
- [ ] HENkaku/Ensō, VitaShell (or any .vpk installer)
- [ ] libshacccg.suprx extracted (PSM Runtime 1.00/2.00/2.01 + ShaRKF00D -> ur0:data/libshacccg.suprx)
- [ ] (external assets) <folder> copied to ux0:data/<data_folder>/<vpk_dir>/
- [ ] (unsafe build only) unsafe homebrew enabled in HENkaku settings
Install and LiveArea
- [ ] the .vpk installs without an error (0x8010113D = a bad LiveArea image)
- [ ] bubble icon, name and LiveArea page look right (colours, not gray; nothing cropped badly)
Boot and play
- [ ] boots to the title screen (first boot compiles shaders: may take longer; second boot is faster)
- [ ] reaches <the agreed state>
- [ ] every mapping in PORT_PLAN.md (one line each), confirm button follows the system setting (try both)
- [ ] front touch / rear touch / gyro behave as decided (or do nothing when off)
- [ ] glyphs match the buttons; the remapping menu works and persists
- [ ] scaling and text legibility on the real screen; frame rate holds <target>
- [ ] audio: levels, no crackle, music loops
- [ ] saves/settings persist across restarts (ux0:data/<data_folder>/)
- [ ] suspend (power button) and resume mid-game; closing from LiveArea
- [ ] a long session (30+ min): no slowdown or crash (memory)
If anything fails: `vita logs`, `vita core`, and send the agent the log/dump.
```

## Level 4: hardware (only once the user says a Vita is connected)
`vita deploy --vpk --yes` (or `--eboot` for quick iterations), `vita launch`, `vita logs`, `vita kill`,
`vita core`. Fix, rebuild, redeploy autonomously.
