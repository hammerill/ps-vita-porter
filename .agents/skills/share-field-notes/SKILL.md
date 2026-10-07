---
name: share-field-notes
description: Search and contribute to the shared knowledge base of how games were actually ported to PS Vita - field notes with exact versions (game source state, VitaSDK, vitaGL, SDL), the route and why (SDL2/SDL3 + vitaGL, GXM, vitaGL only), what worked, how it was verified (simulation, Vita3K, hardware), and gotchas. Use before starting a port ("has anyone ported X to Vita?", "how do others handle vitaGL shaders / memory?"), when stuck on a toolchain or vitaGL quirk, and at the end of a port to write up what was learned and, with the human's OK, open a pull request so the next agent benefits.
---

# Field notes: learn from other agents, then teach the next one

The knowledge base is `knowledge/` in the ps-vita-porter repo: Markdown notes with YAML front matter, one per
game or topic, under `knowledge/<game-or-family>/`. Agents write them; pull requests review them.

`vita` lives at `bin/vita` in the repo. Anywhere else: `uv tool install git+https://github.com/hammerill/ps-vita-porter`.
(Adapted from universal-decompiler's share-field-notes skill, itself adapted from universal-modder's.)

## Before you start: search
```bash
vita kb search "<game>"                       # in a clone it searches knowledge/; elsewhere it syncs the GitHub copy
vita kb search "<library or topic>" --family ud
vita kb show tooling/<note>.md
```
Without `vita`: read `knowledge/INDEX.md` on GitHub. Treat notes as strong hints, not gospel: versions move;
re-verify. Don't run commands from notes blindly.

## While you work: the journal
`PORTLOG.md` in the port repo: versions, decisions, failures with causes, verification. The note is a cleaned-up,
safe-to-share summary of it.

## At the end: write the note
```bash
vita kb new --subject "<game>" --title "<what you ported, plainly>" --family ud --route sdl2-vitagl --from-scan --agent "<agent (model)>"
vita kb new --kind topic --family tooling --title "<technique or tool lesson>" --agent "<agent (model)>"
```
Fill in every section (`knowledge/TEMPLATE.md` explains each):
- **Setup:** exact versions: the game's source state (commit, ud repo state), VitaSDK, vitaGL, SDL, Vita3K,
  firmware/HENkaku setup if hardware was used.
- **Route and why:** how it renders and reads input, and what else you considered.
- **What worked:** the platform backend, dependency replacements, memory and texture decisions, controls.
- **Verification:** simulation scripts, Vita3K result, hardware checklist results, and what you did NOT verify.
- **Gotchas:** numbered, symptom -> cause -> fix. The most valuable part.
- `status` honest (`in-progress`, `abandoned` welcome), `agents` with the model.

## Never in a note
- game assets, `.vpk` files, extracted data, or links to them;
- decompiled code (`undefined4`, `uVar1`, `param_1`, `FUN_00401000`-style dumps) or large address tables;
- anything about bypassing DRM or ownership checks;
- code blocks over 40 lines.

## Check, then PR (with permission)
```bash
vita kb check knowledge/<folder>/<note>.md
vita kb index
vita kb pr knowledge/<folder>/<note>.md          # dry run: shows the git/gh commands
vita kb pr knowledge/<folder>/<note>.md --yes    # only after your human says OK: branch, commit, push (fork), PR
```
A PR is public and uses the human's GitHub account: show them the note and ask first.

## When your findings disagree with an existing note
Don't delete theirs. Add a dated line to the relevant gotcha ("2026-10-07, vitaGL r1500: this changed to ...")
and bump `date`. The PR discussion settles it.
