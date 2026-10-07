# Contributing

Humans and AI agents are both welcome. Two kinds of contributions:

## 1. Field notes (`knowledge/`)
How you ported a game to the Vita, or a tool/technique lesson. The usual path:
```bash
vita kb new --subject "<game>" --title "<what you ported>" --family ud --route sdl2-vitagl --agent "<agent (model)>"
vita kb check knowledge/<folder>/<note>.md
vita kb index
vita kb pr knowledge/<folder>/<note>.md --yes      # agents: only after your human says OK
```
Rules (`vita kb check` enforces most of them):
- **No game assets, no `.vpk` files, no extracted data**, no links to them.
- **No decompiled code** (Ghidra/IDA output, `undefined4`, `uVar1`, `param_1`...), no address tables large enough
  to rebuild code, no code blocks over 40 lines.
- Nothing about bypassing DRM or ownership checks.
- Exact versions (game source state, VitaSDK, vitaGL, SDL, Vita3K, firmware), what was verified where (simulation,
  Vita3K, hardware), what was NOT verified, an honest `status`, the agent and model in `agents`.
- Gotchas as symptom -> cause -> fix. When you disagree with an existing note, add a dated line; don't delete theirs.

## 2. The toolkit (CLI, kit, skills, docs)
```bash
uv run pytest                     # tests; synthetic fixtures are built in the tests (no real games anywhere)
uv run ruff check
python scripts/sync_skills.py     # skills/ is the source of truth; .claude/skills and .agents/skills are copies
./bin/vita kb check --index
```
- Python 3.12+, PyYAML only. One module per command group in `vita_porter/`, a docstring that doubles as `--help`
  **with examples**, `--json` on reporting commands, exit codes 0 / 1 problem / 2 usage.
- Tools go in `vita_porter/tools.toml`, libraries in `vita_porter/deps.toml` (with the vdpm snapshot date).
- The C kit (`vita_porter/kit/`) must compile with `-Wall -Wextra` on VitaSDK and on GCC/Clang/MSVC for the
  simulation; the example builds both.
- Facts about the Vita, vitaGL, Vita3K or vitacompanion come from current sources (headers, READMEs, source), with
  the date in `DEVLOG.md`; never from memory.
- Record non-obvious decisions and tool substitutions in `DEVLOG.md`.
- Agent-neutral wording in skills and docs ("the agent").
