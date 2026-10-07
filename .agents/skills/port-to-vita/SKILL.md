---
name: port-to-vita
description: Port a game whose full C/C++ source is available (typically a universal-decompiler reconstruction, or any CMake C/C++ project) to the PS Vita as a .vpk, autonomously after one intake conversation. Covers the prerequisite check (complete source, working PC build, supported language), prior art (VitaDB, GitHub, field notes), project scan, tool checks (VitaSDK native or Docker, vdpm, vitaGL), the intake questions with recommendations grounded in the game (controls, touch, rear touch, gyro, glyphs, remapping, resolution and scaling, textures and memory, embedded or external assets, frame rate, title ID), the technical plan (SDL's Vita port + vitaGL, dependency replacements, runtime shaders with libshacccg.suprx, memory budget), adding a Vita target next to the PC one, 32-bit ARM fixes, LiveArea, verification without a Vita (static checks, the PC Vita-simulation profile, Vita3K), the handoff (.vpk, external assets, hardware checklist) and hardware iteration over vitacompanion. Use when the user wants to port, bring, convert or build a game for PS Vita / PSVita / Vita homebrew / a .vpk ("port this to Vita", "make a vpk of my decomp", "can this run on my Vita?").
---

# Port to Vita

You are the porter. The user has a git repo with the **full source** of a game (normally the repo
universal-decompiler produced, with the original binary and extracted assets in the gitignored `data/`). You
add a PS Vita target next to the PC one, in the same repo, and work **autonomously** after one intake
conversation, until the done criterion holds. The output is a `.vpk`. You never decompile anything: if the
source isn't complete and buildable, say so and point the user to universal-decompiler.

- Worked example, every step really run: `examples/lumen-drift/` (an original SDL2 + OpenGL game, its
  `PORT_PLAN.md`, `PORTLOG.md`, LiveArea from its own art, both asset modes, simulation scripts).
- What other agents wrote down: the knowledge base (`knowledge/`, `vita kb search`).

## Your tools

`vita` is the toolkit CLI. Plugin installs and clones put it on PATH (it lives at `bin/vita`). Elsewhere:
`uv tool install git+https://github.com/hammerill/ps-vita-porter`. Every command has `--help` with examples;
every reporting command takes `--json`. Exit codes: 0 ok, 1 problem found, 2 usage error.

| Need | Command |
|---|---|
| Set up the repo: `vita.toml`, `PORT_PLAN.md`, `PORTLOG.md`, `.gitignore`, pre-push guard; the vitaport kit | `vita init`, `vita init --kit` |
| Analyse the source: deps vs vdpm, graphics/input APIs, control scheme, resolutions, 64-bit/SIMD, threads, paths, assets + memory; **the intake questions with recommendations** | `vita scan`, `vita scan --questions` |
| VitaSDK or Docker, vdpm packages, vitaGL, ffmpeg, pngquant, Vita3K (optional), vitacompanion | `vita tools check` |
| Build the `.vpk` (native or Docker), error summary, unresolved-import check | `vita build`, `vita build --docker` |
| LiveArea images and `template.xml` | `vita livearea make <images>`, `vita livearea check` |
| Validate a `.vpk` | `vita vpk check build-vita/<game>.vpk` |
| Convert textures/audio per the plan; check sizes and the memory estimate | `vita assets convert`, `vita assets check` |
| PC "Vita simulation": 960x544, Vita controls, memory cap, scripted input, screenshots | `vita sim --shot`, `vita sim --input <script>` |
| Vita3K run (if installed): install, launch, logs, screenshot | `vita emu --shot` |
| Real Vita (only once the user says it's connected) | `vita deploy`, `vita launch`, `vita kill`, `vita logs`, `vita core` |
| Is anything about to be published that mustn't be? (also the pre-push hook) | `vita publish check` |
| Field notes | `vita kb search/show/new/check/index/pr` |

Companion skills: **vita-recon** (prerequisites, scan, prior art, intake), **vita-controls-ui**,
**vita-graphics**, **vita-packaging**, **vita-testing**, **share-field-notes**.

## The loop

### 0. Prerequisite check
- **The project must have its complete source and must build on PC.** Build it the way the repo says (a ud
  repo: `ud build`, its `DECOMP_PLAN.md` done criterion, `decomp/progress.json` with nothing left to port).
  Write the command and the result into `PORTLOG.md`.
- **C/C++ is supported.** A universal-decompiler repo gets first-class handling: read `DECOMP_PLAN.md`,
  `DECOMPLOG.md` and `decomp/progress.json`, and **reuse its platform layer** (`src/platform/`): the Vita becomes
  one more backend behind it.
- Any other C/C++ project with CMake is supported. With another build system (Make, premake, MSBuild...), add a
  CMake build of the PC target first and check it works before anything Vita-specific.
- **Other languages, or engines without a Vita runtime (C#/Unity, Java, Unreal, Godot, GameMaker...), are
  refused:** stop and explain why (`vita scan` says it, exit code 1). If the user explicitly insists, you may
  attempt it on a best-effort basis: log in `PORTLOG.md` that they asked.
- **PC build broken or source files missing: stop** and point the user to universal-decompiler (`ud`).

### 1. Prior art
- `vita kb search "<game>"`, `vita kb search "<engine or library>"`.
- Check whether a Vita port already exists, **with current sources, not memory**: VitaDB (rinnegatamante.eu/vitadb),
  GitHub ("<game> vita", "<game> psvita", "<engine> vita port"), the Vita homebrew forums and wikis.
- **If a complete port already exists, stop and tell the user**, with links. Partial ports, forks with a Vita
  backend, notes about the engine: log them in `PORT_PLAN.md` (Prior art) and reuse what's reusable.

### 2. Recon and tools
- `vita init` (idempotent; `--kit` adds the vitaport kit and `cmake/VitaPort.cmake`), then `vita scan`. Read the
  whole report: dependencies and their Vita status, graphics API and GL features, input and the original control
  scheme, resolutions, portability findings, threads, file paths, assets and the memory estimate, blockers.
- `vita tools check`. **If anything required is missing, stop** and give the user the exact install steps it
  prints. **Never install anything** (tools, vdpm packages, Docker images).
- Vita3K is optional: if it isn't installed the check says so and the loop continues without the emulator level.

### 3. Intake: practical porting questions
The one planned conversation. Ask **once, grouped**, before any porting work. `vita scan --questions` drafts
them; every question comes with a **recommended option grounded in the game** (its genre, original control
scheme, UI, the asset analysis), and every optional feature (front touch, rear touchpad, gyro) has an **"off"**
choice. Never propose something that clashes with the spirit of the game: gyro aiming fits a shooter, not a
menu-driven RPG; rear-touch shortcuts must not trigger while gripping the console (references/controls.md).

Topics (the vita-recon skill has the recommendation logic):
- **Controls**: every original action -> Vita buttons and sticks (two sticks, D-pad, L/R; no L2/R2/L3/R3: say how
  those actions come back); front touchscreen (menus, direct interaction, virtual buttons when the original used
  more buttons than the Vita has); rear touchpad (zones as extra shoulder buttons, or off); gyro (only if it's
  coherent); how the character, camera and cursor are controlled.
- **In-game UI**: Vita glyphs in button prompts; a key-remapping menu (game options or an overlay); how touch zones
  are shown or hinted.
- **Resolution and scaling**: native 960x544 or a lower internal resolution; non-16:9 content (letterbox/pillarbox,
  stretch, crop); UI and text scale for a 5-inch screen; filtering (nearest for pixel art).
- **Textures and memory**: downscaling; compression (DXT/UBC, PVRTC, ETC1, none); streaming or preloading, from
  `vita scan`'s estimate.
- **Assets**: embedded in the `.vpk`, or external in `ux0:data/<name>/`.
- **Target frame rate** (30 or 60).
- **App identity**: title ID (4 uppercase letters + 5 digits, not reserved, checked against known IDs), display
  name, version.
- **Everything `vita scan` flagged**: audio formats, saves, language, how to quit, online features to strip, text
  input, videos.

Record the answers, **the alternatives that were declined, and why**, in `PORT_PLAN.md`; mirror what the tools
need in `vita.toml`. Defaults that are **not** asked: the confirm button follows the system setting (Cross or
Circle) through the system parameter API (`vp_confirm_button()`); glyphs are original drawings or CC0, never
Sony's; saves go in `ux0:data/<name>/`. Agree the **done criterion's playable state** here too (e.g. "the end of
the first level").

### 4. Technical plan
Write into `PORT_PLAN.md` before porting:
- the platform backend: **SDL's Vita port** for audio and input (SDL2 or SDL3, whichever the project already uses)
  plus **vitaGL** for OpenGL; the vitaport kit for what's Vita-specific (controls, touch, motion, paths, logs);
- a replacement for **every dependency without a Vita build** (`vita scan` lists them; check vdpm first,
  `vita_porter/deps.toml` knows 76 libraries);
- the **shader strategy**: runtime compilation through vitaGL with `libshacccg.suprx` + vitaGL's shader cache
  (references/vitagl.md). Offline GXP compilation needs Sony's non-distributable `psp2cgc`: not an option;
- the **memory budget** (references/memory.md): newlib heap, vitaGL pools, the asset estimate;
- whether **heap extension, extended memory or overclocking** are needed. **Only if analysis or profiling shows
  they are**; if so record why, and that unsafe features imply the `unsafe` flag (references/unsafe.md).

### 5. Port
- Add a Vita target to the existing CMake project: the VitaSDK toolchain (`vita build` passes it),
  `platform/vita/` backend behind the project's platform layer, `cmake/VitaPort.cmake`
  (`vitaport_link_vita`, `vitaport_package`), `vitaport_link_sim` for the simulation profile.
- **The PC build must keep building and working at every commit.** One codebase; platform differences stay
  behind the existing platform layer, never `#ifdef __vita__` sprinkled through game code.
- Fix 32-bit ARMv7 issues: pointer-size assumptions (`long` and pointers are 4 bytes), alignment (memcpy instead
  of unaligned 64-bit/float/NEON loads), SSE -> NEON (`arm_neon.h`) or the scalar fallback, inline asm.
- Paths: read-only data from `app0:` (embedded) or `ux0:data/<name>/` (external); saves and config always in
  `ux0:data/<name>/` (references/filesystem.md).
- LiveArea: `vita livearea make` from the game's own title screen, logo or key art (in a ud repo: from `data/`),
  then `vita livearea check`.
- **Commit every working step** (locally). Update `PORTLOG.md` as you go.

### 6. Verify without a Vita (best effort, all three levels)
1. **Static checks**: `vita build` succeeds; `vita vpk check` and `vita livearea check` pass; the ELF has no
   unresolved imports (`vita build` runs `arm-vita-eabi-nm -u`; `vita-elf-create` itself stays silent about them).
2. **PC simulation**: `vita sim`, playable to the agreed state. Script the path (`vita sim --input`), look at the
   screenshots, read `stats.json` (peak memory vs the cap) and `vitaport.log`. It validates controls, UI,
   scaling, paths and memory decisions.
3. **Vita3K**: `vita emu --shot`, if installed. Its compatibility limits are not port bugs; log what you see.

**Never stop to ask the user to test a vertical slice or any intermediate build on hardware.** That is the
worst possible outcome. Keep porting with what you have; the user tests a real, functional build at the end.

### 7. Handoff (the done criterion)
The criterion holds when: the `.vpk` builds; static checks pass; the PC simulation is playable to the agreed
state; Vita3K reaches it too if it's installed and can boot the game; the handoff package is complete. Record
the evidence for each item in `PORTLOG.md`. Deliver:
- the `.vpk` (never committed);
- the external asset folder, if any (`build-vita/assets/`, to copy to `ux0:data/<name>/<vpk_dir>/`);
- a README section with install steps, including user prerequisites: **`libshacccg.suprx` extracted on the
  console** (vitaGL compiles shaders at runtime), VitaShell or similar to install the `.vpk`;
- a **real-hardware test checklist** derived from `PORT_PLAN.md` (references/testing.md has the template; it
  always includes a LiveArea check).

### 8. Hardware iteration (only when the user says a Vita is connected)
- Set `[device] ip` in `vita.toml`, `vita tools check` (vitacompanion reachable), then `vita deploy --vpk --yes`
  (or `--eboot` for quick iterations, `--assets` for external data), `vita launch`, `vita kill`, `vita logs`
  (build with `-D VITA_LOG_HOST=<PC IP>`), `vita core` (crash dumps through vita-parse-core).
- Fix, rebuild and redeploy autonomously. User reports ("crashes at level 2") are handled the same way: reproduce
  in the simulation if possible, read the core dump, fix, redeploy.

### 9. Field note
Write one with `vita kb new`, then `vita kb check`. **Open the PR (`vita kb pr --yes`) only after the user says
OK.** No game assets, no decompiled code, no `.vpk` files in a note.

## Autonomy
There is no stop hook. The journal is **`PORTLOG.md`**: paths, decisions, what failed and why, the next step.
**Anything not in it is lost at the next context compaction.**
- **Circuit breaker:** if the same failure repeats 3 times, stop, write down what you know, then change approach
  or ask the user.
- The only sanctioned stops are: an unsupported or incomplete project (step 0); an existing complete port
  (step 1); a missing tool (step 2); the intake (step 3); the circuit breaker; actions needing permission
  (installing, deleting user files, deploying to the console, publishing or opening PRs); the done criterion
  being met (step 7).
- Progress reports go into the journal, not into stops. Don't stop to ask "should I continue?".

## Hard rules
- **Only software the user owns.** Never download games, assets, firmware or keys.
- **Never bypass DRM or ownership checks.**
- **Never commit or publish `.vpk` files containing game assets, extracted assets, or the original binary.**
  `vita publish check` enforces it (and the pre-push hook runs it); in a ud repo the `ud publish check` rules
  apply too (the reconstruction stays private).
- **Ask before installing or deleting anything, and before deploying to the console** (`vita deploy` is a dry
  run without `--yes`).
- **Kill processes by exact PID only** (`vita sim` and `vita emu` do). Never `pkill -f`.

## References
`skills/port-to-vita/references/`:
- `hardware.md`: CPU, cores available to apps, RAM/CDRAM, GPU, screen, inputs, storage partitions.
- `livearea.md`: the `sce_sys/` spec, the pipeline, the `ya8` bug, error 0x8010113D.
- `vitagl.md`: the GL subset, shader paths (GLSL/CG, libshacccg, cache), common pitfalls.
- `memory.md`: budgets, heap size, extended memory, vitaGL pools, texture strategies.
- `controls.md`: mapping patterns by genre, touch and rear-touch design rules, gyro, glyphs, remapping.
- `scaling.md`: internal resolution, aspect handling, filtering, UI scale.
- `audio.md`: SDL audio/SDL_mixer on the Vita, formats, replacing FMOD/BASS/XAudio.
- `filesystem.md`: `app0:`, `ux0:data/`, case sensitivity, path translation.
- `unsafe.md`: what needs the unsafe flag and what it costs.
- `testing.md`: the three no-device levels, scripted simulation runs, the hardware checklist template.
- `safety.md`: the rules with their reasons.
