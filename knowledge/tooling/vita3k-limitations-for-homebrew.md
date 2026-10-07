---
kind: topic
title: "Vita3K as a test level for homebrew ports: what it can and can't tell you"
family: tooling
tags: [vita3k, emulator, testing]
tools: ["Vita3K continuous build 4134 (2026-10-06)", "vita 0.1.0"]
status: in-progress
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://vita3k.org/quickstart.html", "https://github.com/Vita3K/Vita3K/releases/tag/continuous"]
---

# Vita3K as a test level for homebrew ports: what it can and can't tell you

> Vita3K is a high-level emulator: it implements system modules itself. It's the third verification level of a
> port (after static checks and the PC simulation) and optional. Its failures are not port bugs. The command line
> below was read from Vita3K's source; booting a vitaGL homebrew in it was **not verified** for this note (no
> Vita3K on the machine that wrote it).

## When to use it
After `vita sim` reaches the agreed state, if Vita3K is installed: `vita emu --shot`.

## How
- Command line (`vita3k/config/src/config.cpp`, 2026-10-07): a positional `.vpk`/`.zip` path installs and runs
  it; `-r <TITLEID>` runs an installed app; `-B OpenGL|Vulkan`; `-F` fullscreen; `-c` config location;
  `-l 0-6` log level.
- Builds: `Vita3K-x86_64.AppImage`, `windows-latest.zip`, `macos-latest.dmg` from the `continuous` release. The
  firmware and the font firmware must be installed once (File > Install Firmware).
- Its virtual `ux0:` lives in the pref path (Linux `~/.local/share/Vita3K/Vita3K`, Windows
  `%APPDATA%/Vita3K/Vita3K`): `vita emu` copies `vita3k.log` and the app's `ux0:data/<name>/vitaport.log` from there.

## Gotchas
1. **A vitaGL homebrew doesn't boot or renders wrongly in Vita3K.** **Cause:** HLE gaps around the runtime shader
   compiler and GXM; older vitaGL forks even had a dedicated `HAVE_VITA3K_SUPPORT` build flag (TheOfficialFloW's
   fork README); the current vitaGL README doesn't mention Vita3K. **Fix:** log it in PORTLOG.md and move on: the
   hardware is the authority. Not verified here.
2. **Nothing happens on the first run.** **Cause:** firmware or font firmware not installed. **Fix:** the user
   installs both once (the quickstart page).

## Open questions
Whether the vdpm vitaGL (r1448/r1488) + `libshacccg.suprx` path boots in the current Vita3K, and where Vita3K
expects `libshacccg.suprx` if it loads it: the first agent with Vita3K installed should run `vita emu` on
`examples/lumen-drift` and update this note.
