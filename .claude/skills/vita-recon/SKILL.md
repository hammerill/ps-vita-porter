---
name: vita-recon
description: Decide whether and how a game can be ported to PS Vita before writing any port code - the prerequisite check (complete C/C++ source, a working PC build, a supported engine; universal-decompiler repos get first-class handling), prior art (existing Vita ports on VitaDB/GitHub, field notes), `vita scan` (dependencies vs vdpm, graphics API and GL features, input and the original control scheme, resolutions, 64-bit/SIMD, threads, paths, assets and memory), `vita tools check`, and the intake - the grouped practical questions with a recommendation grounded in the game for each - recorded in PORT_PLAN.md. Use at the start of any Vita port, or when the user asks "can this run on a Vita?", "what would a Vita port need?", "is there already a Vita port of X?".
---

# Vita recon and intake

Goal: know in minutes whether the port can proceed, what it will take, and agree every practical decision with
the user in **one** conversation. Everything lands in `PORT_PLAN.md` (decisions + declined alternatives +
reasons) and `vita.toml` (what the tools need).

## 1. Prerequisites (stop conditions)
| Check | How | If it fails |
|---|---|---|
| Complete source, PC build works | build it as the repo says; ud repo: `ud build`, `DECOMP_PLAN.md` done criterion, `decomp/progress.json` all ported | stop; point to universal-decompiler |
| C/C++ | `vita scan` (languages, engine markers) | refuse (exit 1); best effort only if the user explicitly insists, logged |
| Engine with a Vita runtime | `vita scan` engine markers (Unity, Unreal, Godot, GameMaker, .NET, Java, Ren'Py, RPG Maker MV) | refuse, explain why |
| CMake | `vita scan` build systems | add a CMake build of the PC target first |
| Not already ported | step 2 | stop and tell the user, with links |
| Tools | `vita tools check` | stop with the printed install steps; never install |

**universal-decompiler repos** (`ud.toml`, `DECOMP_PLAN.md`, `decomp/progress.json`): read the plan and the
journal, reuse `src/platform/` (the Vita is one more backend), use `data/` (gitignored, extracted from the user's
copy) as the asset source, recommend **external** assets, and remember the repo stays private (`ud publish check`).

## 2. Prior art
- `vita kb search "<game>"`, `vita kb search "<engine/library>"`.
- Current sources, not memory: VitaDB, GitHub ("<game> vita", "<game> psvita", "<engine> vita"), Vita homebrew
  forums/wikis. A complete port of the same game: stop and tell the user. Partial ports and engine notes: log
  them in PORT_PLAN.md and reuse.
- VitaDB's API (`https://www.rinnegatamante.eu/vitadb/list_hbs_json.php`) answered `[]` on 2026-10-07: if it's
  empty or down, check the website by hand and say so.

## 3. Scan
`vita init` then `vita scan` (`--json` for parsing, `--assets <dir>` if the assets aren't in `data/`/`assets/`).
Read every section; the **FINDING** and **BLOCKER** lines feed the technical plan, the intake list feeds step 4.

## 4. Intake: the questions and how the recommendations are made
`vita scan --questions` drafts them (logic in `vita_porter/intake.py`). Ask them **grouped, once**, each with its
recommendation and reason; offer the alternatives. Every optional feature has an **off** choice. Nothing that
clashes with the spirit of the game.

### Controls
| Question | Recommendation logic |
|---|---|
| Mapping of every action | From the game's action enum if it has one (ud platform layers do: `enum class Key {...}`), else from the keys it reads: WASD/arrows -> left stick + D-pad, Space -> Cross, Enter -> confirm, Escape -> Start/cancel, Shift -> L, Ctrl -> R/Circle, Tab/M -> Select, E/F -> Square, Q -> Triangle/L, digits -> D-pad cycling or touch hotbar, F-keys -> options menu. Face buttons by frequency of use. |
| Actions that don't fit / L2-R2-L3-R3 | <= 12 actions: physical buttons only. More: L/R + button combos for rare actions, front-touch virtual buttons for menu-like ones, rear zones only if the user wants them. |
| Front touch | Mouse-driven games (strategy, point-and-click, puzzle, or mouse without movement keys): direct interaction + a stick cursor. Mouse used for UI only: menus only. No mouse: off. |
| Rear touch | Off unless more than 12 actions; then two half-pad zones, deliberate hold only, with an option to disable. |
| Gyro | Only for shooters with mouse aiming: optional fine aim, off by default. Everything else: off. |
| Character/camera/cursor | Relative mouse (mouse look) -> right stick camera with sensitivity/invert. Pointer without movement keys -> right-stick cursor. Keys for movement + mouse for UI -> sticks/D-pad move, taps replace clicks. |

### In-game UI
Glyphs: original or CC0 drawings, following the confirm-button setting. Remapping: in the game's options menu,
else a Start+Select overlay. Touch hints: only for touch zones that aren't visible elements.

### Resolution and scaling
From the hard-coded resolution `vita scan` found: pixel art (median texture side <= 256 and nearest filtering)
-> integer scale if it fills >= 90% of 544 lines, else fit-to-height with nearest. Non-pixel art at or below
960x544 -> its own resolution scaled to fit, linear. Larger -> native 960x544 (lower internal resolution only if
profiling demands). Non-1.76:1 content -> pillarbox/letterbox (stretch distorts, crop hides UI). UI/text: smallest
text >= ~16 px at 544 lines. Filtering: nearest for pixel art, else linear.

### Textures and memory
From the asset estimate (decoded RGBA vs 112 MiB CDRAM; other data vs the 128 MiB heap): pixel art -> no
downscaling, no compression. > 90 MiB decoded or textures > 2048 px -> halve textures over 1024 px (UI at full
size). > 60 MiB -> DXT1 (opaque) / DXT5 (alpha) for world textures, UI/text uncompressed. Total resident
> 100 MiB -> stream levels and music; else preload.

### Assets
ud repo or > 500 MiB of data -> **external** (`ux0:data/<name>/`): the .vpk carries no game data and the user copies
their own. A small original game -> **embedded**.

### Frame rate
Shader-heavy GL/D3D or > 300 textures -> 30 fps locked (60 if profiling allows); light 2D/fixed function -> 60.

### App identity
Title ID: 4 uppercase letters from the name + 5 digits (CRC of the name), never a reserved prefix (PCS*, NP**,
VLJ*, VCJ*, VSDK...), checked against known IDs (VitaDB) before release. Name: short enough for the bubble.
Version `01.00`.

### Flagged by the scan
Audio APIs/formats (replace FMOD/BASS/XAudio; music OGG streamed, effects WAV 22050 Hz mono), saves
(ux0:data/<name>/, same format), quitting (hide "Quit": apps close from LiveArea; or a clean exit), online
features (strip platform services; keep Wi-Fi play only if essential), text input (IME dialog), videos (re-encode
the user's own for SceAvPlayer, or skip), language (follow the system language when available).

### Not asked (defaults)
Confirm button follows the system setting; glyphs are original/CC0, never Sony's; saves in `ux0:data/<name>/`.

## 5. Write it down
`PORT_PLAN.md`: prerequisites with evidence, prior art, the done criterion (with the agreed playable state),
every intake answer with **declined alternatives and why**, the technical plan. `vita.toml`: title ID, name,
version, data folder, assets mode, unsafe (false unless justified), `[build] vdpm`, `[[assets.rule]]` entries.
`PORTLOG.md`: first entries. Then the port starts (port-to-vita, step 4).
