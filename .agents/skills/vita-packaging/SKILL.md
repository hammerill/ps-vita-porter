---
name: vita-packaging
description: Package a PS Vita port as a .vpk - LiveArea (icon0, pic0, bg0, startup, template.xml) from the game's own art with `vita livearea make/check` (the ya8 grayscale bug fixed, 0x8010113D avoided), param.sfo fields (TITLE_ID, TITLE, APP_VER, ATTRIBUTE2), safe vs unsafe eboot, vita_create_self/vita_create_vpk through cmake/VitaPort.cmake, embedded (app0:) vs external (ux0:data/<name>/) assets with `vita assets convert`, `vita vpk check`, and the handoff package and README install steps (libshacccg.suprx prerequisite). Use when building, validating or shipping the .vpk, when an install fails, or when switching the assets mode.
---

# Vita packaging

References: `port-to-vita/references/livearea.md`, `filesystem.md`, `unsafe.md`.

## LiveArea
```bash
vita livearea make --icon <icon> --pic <key art> --bg <key art> --startup <logo with alpha>   # or positional, in that order
vita livearea make <one image> --pixel-art          # nearest scaling for pixel art
vita livearea check
```
Sources: the game's own title screen, logo, key art (ud repo: from `data/`, so the result stays local). The tool
fixes what makes installs fail (sizes, 8-bit indexed PNGs, alpha only in startup.png, 256 colours in pic0) and
never uses the `ya8` grayscale format.

## param.sfo and the eboot
From vita.toml via `vita build` -> `cmake/VitaPort.cmake`:
`vitaport_package(<target>)` = `vita_create_self(eboot.bin <target> [UNSAFE])` +
`vita_create_vpk(<target>.vpk <TITLEID> eboot.bin VERSION <##.##> NAME "<name>" FILE sce_sys sce_sys [FILE <assets> <vpk_dir>])`,
plus `-d ATTRIBUTE2=12` when `extended_memory = true`. Title ID: 4 uppercase letters + 5 digits, no reserved
prefix. Safe unless PORT_PLAN.md justifies unsafe.

## Assets
- `vita assets convert` (rules in vita.toml) -> `build-vita/assets/`; `vita assets check`.
- **embedded**: `vitaport_package` adds that folder as `<vpk_dir>/` (read from `app0:<vpk_dir>/`).
- **external**: the .vpk carries no game data; the user copies `build-vita/assets/` to
  `ux0:data/<data_folder>/<vpk_dir>/`. A second flavour next to the first:
  `vita build --build-dir build-vita-ext -D VITA_ASSETS_MODE=external`.

## Validate
```bash
vita build                   # native or Docker; unresolved imports checked
vita vpk check build-vita/<game>.vpk                 # against vita.toml
vita vpk check build-vita-ext/<game>.vpk --assets external
vita publish check           # .vpk files and game data never get committed
```

## Handoff package
- The `.vpk` (and the external asset folder) handed over locally, never committed or published when it holds
  game assets or art.
- README section: prerequisites (HENkaku/Ensō, VitaShell, **libshacccg.suprx** via PSM Runtime + ShaRKF00D,
  unsafe homebrew enabled only for unsafe builds), install (copy the .vpk, install with VitaShell), external
  assets (where to copy them), where saves live, how to report problems (`vitaport.log`).
- The hardware test checklist (testing.md template).
