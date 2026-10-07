# PORTLOG

The journal of this PS Vita port. **Anything that isn't written here is lost at the next context
compaction.** Log paths, decisions, what failed and why, and the next step. Progress reports go here too;
they are not a reason to stop.

## Status
- Phase: intake <!-- prerequisites | prior art | recon | tools | intake | plan | port | verify | handoff | hardware -->
- Done criterion: see PORT_PLAN.md
- Next step: `vita scan`, `vita tools check`
- Circuit breaker: <!-- "<failure>" x<count>; at 3 identical failures: stop, write down what you know, change approach or ask -->

## Facts (keep current)
| What | Value | Source |
|---|---|---|
| Project kind | cmake | vita init |
| PC build | <!-- command + result --> | |
| Title ID / name / data folder | LMND65762 / lumen-drift / ux0:data/lumen-drift/ | vita.toml |
| Assets mode | embedded | vita.toml (confirm at intake) |

## Done criterion evidence
| Item | Evidence (command, output, screenshot, date) |
|---|---|
| `.vpk` builds | |
| Static checks pass (`vita vpk check`, `vita livearea check`, no unresolved imports) | |
| PC simulation reaches the agreed state (`vita sim`) | |
| Vita3K reaches it too (if installed and able to boot it) | |
| Handoff package complete (.vpk, external assets, README section, hardware checklist) | |

## Log
### 2026-10-07
- `vita init` run (cmake project).
