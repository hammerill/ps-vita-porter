# ps-vita-porter

Skills, the `vita` CLI and a shared knowledge base for AI coding agents: Claude Code, Codex, Cursor, Gemini CLI,
GitHub Copilot, OpenCode and anything else that reads `AGENTS.md`. When someone opens an agent with this toolkit,
they almost always want to **port a game whose full C/C++ source they have to the PS Vita as a .vpk**, typically
the reconstruction universal-decompiler (`ud`) produced. ps-vita-porter **never decompiles**: if the source isn't
complete and buildable, say so and point to universal-decompiler.

## Start here
1. **Read `skills/port-to-vita/SKILL.md` and follow its loop:** prerequisites -> prior art -> recon and tools
   (`vita init`, `vita scan`, `vita tools check`) -> **intake** (the one planned conversation, `PORT_PLAN.md`) ->
   technical plan -> port (Vita target next to the PC one) -> verify without a Vita (static checks, `vita sim`,
   `vita emu`) -> handoff (.vpk, external assets, hardware checklist) -> hardware iteration (only when the user
   says a Vita is connected) -> field note.
2. **Search the knowledge base first:** `vita kb search "<game, library or topic>"` (`knowledge/INDEX.md`).
3. **At the end, share what you learned:** `vita kb new ...`, `vita kb check`, and with your human's OK,
   `vita kb pr <note> --yes`. See `knowledge/README.md` and `CONTRIBUTING.md`.

## The user's port repo
The user's game repo (normally a ud repo: `data/` holds the original binary and extracted assets, gitignored).
`vita init` adds `vita.toml`, `PORT_PLAN.md` (intake answers, done criterion, technical plan), `PORTLOG.md` (the
journal), a `.gitignore` block (`build-vita/`, `build-sim/`, `*.vpk`) and a pre-push hook that runs
`vita publish check` (chained after ud's own). `vita init --kit` adds the vitaport kit (`platform/vita/vitaport/`)
and `cmake/VitaPort.cmake`. The PC build keeps working at every commit.

## Tools
- **`bin/vita`** is the Python CLI (Python >= 3.12); it sets itself up with `uv`.
  - On PATH: plugin installs and the SessionStart hook do it; otherwise `export PATH="$PWD/bin:$PATH"`, or
    `uv tool install git+https://github.com/hammerill/ps-vita-porter`.
  - Commands (every one has `--help` with examples; reporting commands take `--json`; exit codes 0 ok,
    1 problem found, 2 usage error): `init`, `scan`, `tools`, `build`, `livearea`, `vpk`, `assets`, `sim`, `emu`,
    `deploy`, `launch`, `kill`, `logs`, `core`, `publish`, `kb`.
  - The name `vita` doesn't clash with VitaSDK: its binaries are all `vita-*`, `arm-vita-eabi-*`, `vdpm`, `psp2rela`.
- **No MCP server of our own.**
- **Skills** (`skills/*/SKILL.md`, Agent Skills format) are copied where agents look for them in a clone:
  `.agents/skills` (Codex, Gemini CLI, Copilot, Cursor, OpenCode) and `.claude/skills` (Claude Code). Edit
  `skills/`, then run `python scripts/sync_skills.py`; a test fails while the copies differ.
- **References:** `skills/port-to-vita/references/` (hardware, livearea, vitagl, memory, controls, scaling, audio,
  filesystem, unsafe, testing, safety).
- **Worked example:** `examples/lumen-drift/` (PC + simulation + Vita, both asset modes, every step run).

## Rules (reasons in `skills/port-to-vita/references/safety.md`)
- **Only software the user owns.** Never download games, assets, firmware, keys or `libshacccg.suprx`.
- **Never bypass DRM or ownership checks.**
- **Never commit or publish `.vpk` files containing game assets, extracted assets, or the original binary.**
  `vita publish check` enforces it; in a ud repo `ud publish check` applies too.
- **Ask before installing or deleting anything, and before deploying to the console.** `vita tools check` prints
  install steps; it never installs. `vita deploy` needs `--yes`.
- **Kill processes by exact PID only** (`vita sim`, `vita emu` do). Never `pkill -f`.
- **Keep the journal** (`PORTLOG.md`): anything not in it is lost at the next context compaction.
- **Circuit breaker:** the same failure 3 times -> stop, write down what you know, change approach or ask.
- **Never ask the user to test an intermediate build on hardware.** The user tests a real build at the end.

## Working on the toolkit itself
- **Python:** 3.12+, one runtime dependency (PyYAML), managed with `uv`. Code lives in `vita_porter/`, one module per
  command group (`device.py` holds deploy/launch/kill/logs/core), each with `register(sub)` and a docstring that
  doubles as `--help`. Registries: `vita_porter/tools.toml` (tools), `vita_porter/deps.toml` (libraries vs vdpm).
  Templates in `vita_porter/templates/`, the C kit in `vita_porter/kit/`.
- **Tests:** `uv run pytest`. Lint: `uv run ruff check`. CI (Windows + Ubuntu) also runs `vita kb check --index`,
  the skills-sync check, every help screen, a `uv tool install`, and the example (PC builds; both `.vpk` flavours
  in the `vitasdk/vitasdk` Docker image).
- **Journal:** `DEVLOG.md` records every non-obvious decision and tool substitution.
- **Wording:** keep skills and docs agent-neutral ("the agent") except in sections about one agent.
