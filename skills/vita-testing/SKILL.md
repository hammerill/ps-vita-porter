---
name: vita-testing
description: Verify a PS Vita port without a Vita and then on one - static checks (vita build with the unresolved-import check, vita vpk check, vita livearea check), the PC Vita-simulation profile (vita sim - 960x544, Vita controls on keyboard/gamepad/mouse, memory cap with OOM detection, scripted input, screenshots, stats), Vita3K runs (vita emu), the done criterion evidence, the real-hardware checklist, and hardware iteration through vitacompanion (vita deploy, launch, kill, logs, core with vita-parse-core), plus the 3-strike circuit breaker. Use whenever the port must be built, run, checked, compared, debugged on a console, or when something fails repeatedly.
---

# Vita testing

Reference: `port-to-vita/references/testing.md` (levels, checklist template). Never ask the user to test an
intermediate build on hardware.

## Static
```bash
vita build && vita vpk check build-vita/<game>.vpk && vita livearea check
```
`vita build --json` gives `{ok, vpk, elf, unresolved, errors}`; fix the first error, rebuild.
Compile jobs are bounded by available memory (about 1 GiB per heavy C++ job); `vita build` prints the
count and why. On WSL or a small machine, a first build of big libraries can still run out of memory: lower it
(`-j 2`, `[build] jobs`), or ask the user to raise WSL's memory (`%UserProfile%\.wslconfig`: `[wsl2]`
`memory=12GB`, `swap=8GB`, then `wsl --shutdown`). Never run a bare `cmake --build --parallel` yourself: that's
an unbounded `make -j`. A build killed by its timeout/stall watchdog says so (`killed` in `--json`); the next
build cleans up the precompiled headers it may have left half-written.

## PC simulation
```bash
vita sim --shot --timeout 30                       # does it boot? look at the screenshot
vita sim --input sim/<scenario>.txt --timeout 120  # the agreed path, screenshots from the script
vita sim --enter circle --memory 96                # other confirm button, tighter memory
```
Read `build-sim/vita-sim/<time>/`: screenshots (open them), `stats.json` (`mem_peak` vs `mem_budget`, `oom`,
`fps`), `vitaport.log`, stderr. `VITASIM OOM` = the game would run out of heap on the Vita: shrink assets,
stream, or (plan decision) raise the heap. The game must be linked with `vitaport_link_sim` and call `vp_init`,
`vp_poll`, `vp_frame` (and `vp_set_readback` for kit screenshots; `--os-shot` captures the window instead).

## Vita3K
```bash
vita emu --shot --timeout 90
```
Skipped (exit 0) when Vita3K isn't installed. Logs: `vita3k.log`, the app's `vitaport.log` from Vita3K's
virtual ux0. Vita3K's compatibility limits are not port bugs; record what you saw.

## Hardware (only after the user says a Vita is connected)
```bash
vita tools check                     # with [device] ip set: vitacompanion reachable?
vita deploy --vpk --yes              # first install (asks the user first: deploying needs permission); a
                                     # vitacompanion without `promote` (<= 1.07) gets ux0:<name>.vpk -> VitaShell
vita deploy --eboot --yes && vita launch     # fast iterations
vita logs --timeout 120              # UDP log (build with -D VITA_LOG_HOST=<this PC's IP>)
vita core                            # newest crash dump -> vita-parse-core (VITA_PARSE_CORE, python2)
vita kill
```
User reports ("crashes at level 2"): reproduce in `vita sim` with a script if possible, read the dump, fix,
redeploy.

## Evidence and the circuit breaker
Each done-criterion item gets its command, result and screenshot paths in PORTLOG.md. **The same failure 3 times
-> stop, write down what you know in PORTLOG.md, then change approach or ask the user.**
