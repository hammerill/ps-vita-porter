---
# Field note: how a game was ported to the Vita, written so the next agent can repeat it. Keep the keys; delete the comments.
kind: title                                               # title (one game) | topic (a tool, technique or family)
title: "Porting the Foo Racer reconstruction to PS Vita"  # what you ported, in plain words
subject: "Foo Racer"                                      # the game's usual name
subject_version: "ud repo at commit abc1234 (Foo Racer 1.2 GOG)"   # exact source state you ported
family: ud                                                # ud | cmake | other-build | other-language
route: sdl2-vitagl                                        # sdl2-vitagl | sdl3-vitagl | sdl2-gxm | sdl3-gxm | vitagl-only | native-gxm | other
assets_mode: external                                     # embedded | external
tools: ["VitaSDK 2026.08", "vitaGL r1488", "SDL 2.32.8", "vita 0.1.0"]
status: working                                           # idea | in-progress | working | complete | abandoned
agents: ["Claude Code (Opus 5.5)"]                        # agent + model that did the work
humans: []                                                # handles of the humans involved, if they want credit
date: 2026-10-07
links: []                                                 # public links only (never a private repo or a .vpk)
tags: []                                                  # free-form: vitagl, shaders, memory, controls, ...
---

# Porting the Foo Racer reconstruction to PS Vita

> Two to four sentences: what you ported, by which route, how far it got, and how you know it works.

## Setup
Exact versions: the game's source state, VitaSDK, vdpm packages (vitaGL, SDL...), Vita3K build, console firmware
and HENkaku/Ensō if hardware was used. The versions that worked are the most useful thing you can write down.

## Route and why
How it renders (vitaGL, GXM...), how input and audio work, what `vita scan` flagged, what you considered.

## What worked
The platform backend, dependency replacements, shader approach, memory and texture decisions, the control scheme
and UI changes, LiveArea. Your own words; no decompiled code, no assets.

## Verification
Static checks, the simulation scripts and what they reached, Vita3K's result, the hardware checklist results.
Say what you did NOT verify.

## Gotchas
The most valuable section. Numbered; each one symptom -> cause -> fix.
1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.

## Open questions
What's unresolved, and the next step.
