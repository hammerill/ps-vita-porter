# ps-vita-porter

**Skills, the `vita` CLI and a shared knowledge base that let an AI coding agent take a game whose full C/C++
source you have and port it, on its own, to the PS Vita as a `.vpk`.** It handles everything Vita-specific on a
best-effort basis without a Vita: project analysis, VitaSDK builds, LiveArea assets, `.vpk` validation, asset
conversion, a PC "Vita simulation" profile, Vita3K runs, and deployment and logs once a real Vita is available.

Inspired by universal-modder. Not affiliated with its authors.
([universal-modder](https://github.com/rehan-remade/universal-modder) by rehan-remade, MIT; this project mirrors
its architecture: skills + CLI + knowledge base + journal + circuit breaker. See [`NOTICE`](NOTICE).)

## Where it fits: universal-decompiler -> ps-vita-porter
[universal-decompiler](https://github.com/hammerill/universal-decompiler) (CLI `ud`) turns a binary you own into
a full C++/CMake source reconstruction that builds on Windows and Linux. **ps-vita-porter takes a project whose
full source is available, typically that `ud` repo, and ports it to the Vita.** It **never decompiles**: an
earlier project under the same name tried to decompile a PC game and port it to the Vita at the same time, and
failed. If the source isn't complete and buildable, the agent says so and points you to universal-decompiler.
A `ud` repo gets first-class handling: the agent reads its `DECOMP_PLAN.md` and `decomp/progress.json`, reuses
its platform layer, uses the assets extracted in `data/`, and keeps the repo private (`ud publish check`).
Any other C/C++ project with CMake works too (other build systems get a CMake build first). Other languages and
engines without a Vita runtime (C#/Unity, Java, Unreal...) are refused unless you explicitly insist.

## How you use it
1. Have a git repo with the full source of the game, building on PC. Normally the repo `ud` produced, with the
   original binary and extracted assets in the gitignored `data/`.
2. Start your agent in that repo with the ps-vita-porter skill loaded and `vita` on PATH (see Install).
3. Say what you want:
   > Port this game to my PS Vita.
4. The agent runs `vita init`, `vita scan` and `vita tools check`. **If a tool is missing it stops and gives you
   exact install steps; it never installs anything itself.**
5. **Intake, the one planned conversation:** the agent asks the practical questions once, grouped, each with a
   recommendation grounded in your game: how every action maps to the Vita's buttons and sticks, front touch,
   rear touchpad and gyro (each with an "off"), button glyphs and a remapping menu, resolution and scaling,
   textures and memory, embedded or external assets, frame rate, the title ID. Answers, declined alternatives
   and reasons go into `PORT_PLAN.md`.
6. Then it ports autonomously in the same repo, adding a Vita target next to the PC one (the PC build keeps
   working at every commit), and verifies without a Vita: static checks, the PC simulation (`vita sim`), Vita3K
   if you have it. Its journal is `PORTLOG.md`. **It never stops to ask you to test intermediate builds.**
7. You get a `.vpk`, the external asset folder if you chose external assets, install steps and a test checklist
   for the real console. When you connect a Vita (vitacompanion), the agent can deploy, read logs and crash
   dumps, and iterate.

## What you need
On the PC:
- **VitaSDK** (native, `$VITASDK`; Linux, macOS, or WSL2 on Windows) **or Docker** with the `vitasdk/vitasdk` image
  (`docker pull vitasdk/vitasdk:latest`, ~1.6 GB). The vdpm packages your game needs (`vitaGL` at least).
- CMake 3.20+, Git, a PC C++ compiler (the PC build and the simulation profile), **FFmpeg** and **pngquant**
  (LiveArea, asset conversion), Python 3.12+ (`uv` recommended).
- Optional: **[Vita3K](https://vita3k.org)** (with its firmware installed) for the emulator test level;
  [vita-parse-core](https://github.com/xyzz/vita-parse-core) (Python 2) to read crash dumps.

`vita tools check` checks all of this and prints install steps for Windows, Linux and macOS.

On the PS Vita (for the real test at the end):
- HENkaku/Ensō and a `.vpk` installer (VitaShell).
- **`libshacccg.suprx`** extracted on your own console: vitaGL compiles shaders at runtime with it. Current method:
  PSM Runtime 1.00, 2.00, 2.01, then ShaRKF00D (writes `ur0:data/libshacccg.suprx`).
- **[vitacompanion](https://github.com/devnoname120/vitacompanion)** (FTP 1337, commands 1338) if you want the
  agent to deploy, launch, read logs and fetch crash dumps over Wi-Fi.

## Install

Pick your agent. Each gets the same skills (Agent Skills format) and the `vita` CLI. ps-vita-porter ships no MCP
server.

| Agent | Install |
|---|---|
| **Claude Code** | `/plugin marketplace add hammerill/ps-vita-porter`<br>`/plugin install ps-vita-porter@ps-vita-porter` |
| **Codex** | `codex plugin marketplace add hammerill/ps-vita-porter`<br>`codex plugin add ps-vita-porter@ps-vita-porter` |
| **Gemini CLI** | `gemini extensions install https://github.com/hammerill/ps-vita-porter` |
| **VS Code / Copilot** | Enable `chat.plugins.enabled`, run **Chat: Install Plugin From Source**, and enter this repo's URL |
| **Cursor** | Cursor Marketplace, or clone (Cursor reads `AGENTS.md` and `.agents/skills`) |
| **OpenCode** | Clone and run `opencode` inside it (`opencode.json` points it at `skills/`) |
| **Skills only**<br>(any agent) | `npx skills add https://github.com/hammerill/ps-vita-porter` |
| **Anything else** | `git clone https://github.com/hammerill/ps-vita-porter` and start your agent with it |

Inside a clone, agents find the skills where they look for them: `.agents/skills` (Codex, Gemini CLI, Copilot,
Cursor, OpenCode) and `.claude/skills` (Claude Code) are copies of `skills/`. Instructions are in `AGENTS.md`,
which `CLAUDE.md` and `GEMINI.md` point to.

**The `vita` CLI.** Plugin installs and clones put it on PATH (a SessionStart hook adds `bin/`). Anywhere else:
```bash
uv tool install git+https://github.com/hammerill/ps-vita-porter      # or: pipx install git+...
```
The command is `vita`; VitaSDK's own tools are all named `vita-*` (and `arm-vita-eabi-*`, `vdpm`), so nothing clashes.

## What's inside

**Skills** (`skills/`, Agent Skills format)

| Skill | What it does |
|---|---|
| [`port-to-vita`](skills/port-to-vita) | The whole loop (prerequisites, prior art, recon and tools, intake, technical plan, port, verification without a Vita, handoff, hardware iteration, field note), the autonomy rules, hard rules, and 11 references: hardware, LiveArea, vitaGL, memory, controls, scaling, audio, filesystem, unsafe, testing, safety |
| [`vita-recon`](skills/vita-recon) | Prerequisite check, `vita scan`, prior art, and the intake questions with their recommendation logic -> `PORT_PLAN.md` |
| [`vita-controls-ui`](skills/vita-controls-ui) | Control schemes, touch/rear touch/gyro, the system confirm button, glyphs, remapping |
| [`vita-graphics`](skills/vita-graphics) | vitaGL, shaders (runtime, libshacccg), resolution and scaling, textures and memory |
| [`vita-packaging`](skills/vita-packaging) | LiveArea, `param.sfo`, the `.vpk`, embedded vs external assets, the handoff package |
| [`vita-testing`](skills/vita-testing) | Static checks, the PC simulation, Vita3K, hardware deploy and debugging, the circuit breaker |
| [`share-field-notes`](skills/share-field-notes) | Search and write field notes; PRs with your OK |

**The `vita` CLI** (`bin/vita`, Python 3.12+; every command has `--help` with examples, reporting commands take `--json`;
exit codes 0 ok, 1 problem found, 2 usage error)

| Command | What it does |
|---|---|
| `vita init [--kit]` | `vita.toml`, `PORT_PLAN.md`, `PORTLOG.md`, `.gitignore` (`build-vita/`, `*.vpk`), a pre-push guard; detects a ud repo; idempotent. `--kit`: the vitaport C kit + `cmake/VitaPort.cmake` |
| `vita scan` | Language and build system; dependencies vs vdpm (76 libraries known); graphics API and GL features; input APIs and the original control scheme; hard-coded resolutions; 64-bit and SIMD assumptions; threads; file paths; asset inventory with a RAM/VRAM estimate vs the Vita budget; network features; blockers; **the intake questions with recommended answers** |
| `vita tools check` | VitaSDK or Docker + image, vdpm packages, vitaGL, CMake, compiler, ffmpeg, pngquant, Vita3K (optional), vitacompanion (once an IP is set). Never installs. Registry: `vita_porter/tools.toml` |
| `vita build [--docker\|--native] [--config ...]` | Builds the `.vpk`; full log in `build-vita/vita-build.log`, short error summary, unresolved-import check (`nm -u`) |
| `vita livearea make <images...>` / `check` | `sce_sys/` per the LiveArea spec (the gist's `ya8` grayscale bug fixed; pngquant's low bit depths re-expanded) and its validation |
| `vita vpk check <file.vpk>` | Structure, title ID, `param.sfo`, safe/unsafe vs `vita.toml`, LiveArea, size, assets present/absent vs the assets mode |
| `vita assets convert\|check` | Textures (resize, nearest for pixel art, DXT1/DXT5 DDS, external encoders) and audio (rate, channels, OGG) into `build-vita/assets/`; missing/oversized items and the memory estimate |
| `vita sim [--shot] [--input script] [--timeout S]` | The PC "Vita simulation": 960x544, Vita controls on keyboard/gamepad/mouse (touch, rear touch, gyro), Vita paths, a memory cap enforced by an allocator wrapper, scripted input, screenshots, stats; kill by PID |
| `vita emu [--shot] [--timeout S]` | Vita3K, if installed: installs and runs the `.vpk`, collects its log and the app's log, screenshots, stops by PID |
| `vita deploy\|launch\|kill\|logs\|core` | Real hardware through vitacompanion: FTP upload (unpacked `.vpk` + promote, or the `.vpk` to `ux0:` for VitaShell when vitacompanion has no promote; `eboot.bin`, external assets), launch/quit, UDP network log or the log file, crash dumps through vita-parse-core |
| `vita publish check` | Fails if tracked files include `.vpk` files, Vita build outputs, converted or extracted assets, or the original binary; runs `ud publish check` in a ud repo. The pre-push hook |
| `vita kb search\|show\|new\|check\|index\|sync\|pr` | The knowledge base |

**The vitaport kit** (`vita_porter/kit/`, copied by `vita init --kit`): one C API (`vitaport.h`) for controls,
touch, motion, the system confirm button, `app0:`/`ux0:data` paths, logging (file + UDP), scaling rectangles and
memory stats, with a Vita backend (SceCtrl, SceTouch, SceMotion, SceAppUtil) and a PC simulation backend (SDL2 or
SDL3) + `vitaport_alloc.cpp` (the memory cap). `cmake/VitaPort.cmake` adds the Vita target
(`vita_create_self`/`vita_create_vpk` with LiveArea and embedded assets) and the simulation profile.

## Worked example
[`examples/lumen-drift`](examples/lumen-drift): a small original game (C++20, SDL2, OpenGL fixed function, all
art drawn by a script) ported with the workflow: its `PORT_PLAN.md` (intake answers and reasons), `PORTLOG.md`
(evidence), LiveArea generated from its own art, a simulation script, and both asset modes. CI builds its PC
target and both `.vpk` flavours in the `vitasdk/vitasdk` Docker image and runs `vita vpk check` and
`vita livearea check` on them.

## A knowledge base that agents write for agents
[`knowledge/`](knowledge/) holds field notes: how specific games were ported, one note per game or topic, with
exact versions, the route and why, what worked, how it was verified, and gotchas (symptom -> cause -> fix). It
starts with tooling notes: LiveArea images that install, VitaSDK in Docker, vitaGL shaders and
`libshacccg.suprx`, Vita3K for homebrew, memory budgeting.
```bash
vita kb search "vitagl"
vita kb new --subject "Foo Racer" --title "Porting the Foo Racer reconstruction to PS Vita" --family ud --route sdl2-vitagl
vita kb check knowledge/foo-racer/porting-the-foo-racer-reconstruction-to-ps-vita.md
vita kb pr knowledge/foo-racer/porting-the-foo-racer-reconstruction-to-ps-vita.md --yes   # only after you say OK
```

## Legal and safety posture
- ps-vita-porter is for **software you own**. It never downloads games, assets, firmware, keys or
  `libshacccg.suprx`, and never bypasses DRM or ownership checks.
- **A `.vpk` with game assets is a copy of the game: it's never committed or published.** `vita publish check`
  runs before every push. External assets keep the `.vpk` free of game data; LiveArea images made from game art
  are still game art.
- It asks before installing or deleting anything and before deploying to a console, and kills processes by exact
  PID only.

This is not legal advice. Reasons: [`skills/port-to-vita/references/safety.md`](skills/port-to-vita/references/safety.md).

## Contributing and development
```bash
uv run pytest                     # tests (synthetic fixtures generated in-test)
uv run ruff check                 # lint
python scripts/sync_skills.py     # after editing skills/
./bin/vita kb check --index       # knowledge base
```
Decisions, tool substitutions and what failed along the way are in [`DEVLOG.md`](DEVLOG.md).

## Credits
- Inspired by [universal-modder](https://github.com/rehan-remade/universal-modder) (not affiliated); companion of
  [universal-decompiler](https://github.com/hammerill/universal-decompiler).
- Standing on VitaSDK, vdpm, vitaGL, vitaShaRK, SDL's Vita ports, Vita3K, vitacompanion, vita-parse-core,
  VitaShell, HENkaku/Ensō, FFmpeg and pngquant, and hammerill's LiveArea spec gist.

MIT licensed ([`LICENSE`](LICENSE)).
