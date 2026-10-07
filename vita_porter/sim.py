"""Build and run the PC "Vita simulation" profile: the PC build with -DVITA_SIM=ON, which links the vitaport kit's
simulation backend (`vita init --kit`, cmake/VitaPort.cmake: vitaport_link_sim).

    vita sim                                   # convert assets, build build-sim/, run it until it exits (or 60 s)
    vita sim --shot --timeout 20               # one screenshot after 5 s (or --shot-at 12), kill at 20 s
    vita sim --input sim/menu-to-level.txt --timeout 30   # scripted input (see below), screenshots from the script
    vita sim --memory 96 --enter circle        # a tighter memory cap; Circle as the system's confirm button
    vita sim --no-build --json -- --some-game-arg

What the profile does (vitaport_sim.c / vitaport_alloc.cpp):
  - the game window is 960x544 and the game scales into it exactly as on the Vita;
  - controls use the Vita layout: D-pad arrows, left stick WASD, right stick IJKL, Cross X, Circle C, Square Z,
    Triangle V, L Q, R E, Start Enter, Select Backspace; front touch = left mouse button, rear touch = left mouse
    button + Left Alt, gyro = numpad; a gamepad maps by position (no L2/R2/L3/R3, like the Vita);
  - app0: and ux0: are folders: build-sim/app0/ (embedded assets) and build-sim/ux0/ (data folder, saves, logs,
    external assets), staged from [assets] out;
  - a memory cap ([sim] memory_mb, default 128 = the Vita's default newlib heap) enforced by an allocator wrapper:
    exceeding it logs "VITASIM OOM" and aborts (or returns NULL with --oom null);
  - scripted input (--input): one "<ms> <command> [args]" per line: press|release|tap <button> [ms], lstick|rstick
    <x> <y> (0-255), touch|rtouch <x> <y> (960x544 pixels), untouch|unrtouch, gyro <x> <y> <z>, shot <name>, quit.

Output in build-sim/vita-sim/<time>/: stdout.txt, stderr.txt, vitaport.log, stats.json (frames, fps, peak memory,
budget, OOM), screenshots. A crash or an OOM gives exit code 1; being killed at the timeout doesn't.
Never kills by name: only the PID it started.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import time
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, load_config, project_root, rel, usage
from vita_porter.proc import os_shot, run_bounded

DEFAULT_MEM_MB = 128


def mirror(src: Path, dst: Path) -> int:
    """Copy src/ into dst/ (only changed files; files gone from src are removed). Returns files copied."""
    n = 0
    if not src.is_dir():
        return 0
    dst.mkdir(parents=True, exist_ok=True)
    want = set()
    for p in src.rglob("*"):
        if p.is_file():
            r = p.relative_to(src)
            want.add(r.as_posix())
            d = dst / r
            if not d.exists() or d.stat().st_size != p.stat().st_size or d.stat().st_mtime < p.stat().st_mtime:
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, d)
                n += 1
    for p in list(dst.rglob("*")):
        if p.is_file() and p.relative_to(dst).as_posix() not in want:
            p.unlink()
    return n


def build_sim(root: Path, cfg: dict, config: str, extra: list[str]) -> dict:
    from vita_porter.build import defines, parse_errors, run_logged
    s = cfg.get("sim", {})
    out = root / s.get("build_dir", "build-sim")
    out.mkdir(parents=True, exist_ok=True)
    src = root / (cfg.get("project", {}).get("source_dir") or ".")
    if not (src / "CMakeLists.txt").exists():
        usage(f"no CMakeLists.txt in {rel(root, src)}")
    logp = out / "vita-sim-build.log"
    gen = cfg.get("build", {}).get("generator") or ""
    opts = list(s.get("options", ["-DVITA_SIM=ON"])) + [f"-D{x}" if not x.startswith("-D") else x for x in extra]
    dfs = [d for d in defines(root, cfg, root.as_posix()) if d.split("=")[0][2:] in ("VITA_DATA_FOLDER", "VITA_ASSETS_MODE", "VITA_ASSETS_VPK_DIR")]
    t0 = time.time()
    with open(logp, "w", encoding="utf-8", newline="\n") as log:
        rc = run_logged(["cmake", "-S", str(src), "-B", str(out), f"-DCMAKE_BUILD_TYPE={config}", *(["-G", gen] if gen else []), *dfs, *opts],
                        root, log)
        stage = "configure"
        if rc == 0:
            stage = "build"
            rc = run_logged(["cmake", "--build", str(out), "--config", config, "--parallel"], root, log)
    errors, nerr, _ = parse_errors(logp.read_text(encoding="utf-8", errors="replace"))
    return dict(ok=rc == 0, stage=stage, exit_code=rc, seconds=round(time.time() - t0, 1), errors=errors, error_count=nerr, log=rel(root, logp))


def find_exe(root: Path, cfg: dict, override: str | None) -> Path:
    s = cfg.get("sim", {})
    val = override or s.get("exe")
    if val:
        p = Path(val) if Path(val).is_absolute() else root / val
        if not p.exists() and os.name == "nt" and p.suffix == "":
            p = p.with_suffix(".exe")
        if not p.exists():
            usage(f"simulation executable not found: {p} (build it: vita sim without --no-build)")
        return p
    out = root / s.get("build_dir", "build-sim")
    cands = []
    for d in (out / "bin", out / "Debug", out / "RelWithDebInfo", out / "Release", out):
        if d.is_dir():
            cands += [p for p in d.iterdir() if p.is_file() and (p.suffix.lower() == ".exe" or (not p.suffix and os.access(p, os.X_OK)))]
    if len(cands) == 1:
        return cands[0]
    usage("set [sim] exe in vita.toml (the simulation build's executable)" + (f"; candidates: {', '.join(map(str, cands[:5]))}" if cands else ""))


def run_sim(root: Path, cfg: dict, exe: Path, args: list[str], timeout: float, shot: bool, shot_at: float | None, memory: int | None,
            enter: str, script: str | None, oom: str, os_screenshot: bool) -> dict:
    s, app, a = cfg.get("sim", {}), cfg.get("app", {}), cfg.get("assets", {})
    out = root / s.get("build_dir", "build-sim")
    folder = app.get("data_folder") or "game"
    vpk_dir = a.get("vpk_dir", "assets")
    converted = root / a.get("out", "build-vita/assets")
    app0, ux0 = out / "app0", out / "ux0"
    if app.get("assets", "embedded") == "external":
        staged = mirror(converted, ux0 / "data" / folder / vpk_dir)
        shutil.rmtree(app0 / vpk_dir, ignore_errors=True)
    else:
        staged = mirror(converted, app0 / vpk_dir)
        shutil.rmtree(ux0 / "data" / folder / vpk_dir, ignore_errors=True)
    app0.mkdir(parents=True, exist_ok=True)
    ux0.mkdir(parents=True, exist_ok=True)
    run_dir = out / "vita-sim" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    mem = memory or int(s.get("memory_mb") or 0) or DEFAULT_MEM_MB
    env = {**os.environ, "VITASIM_APP0": str(app0), "VITASIM_UX0": str(ux0), "VITASIM_MEM_MB": str(mem), "VITASIM_OOM": oom,
           "VITASIM_ENTER": enter, "VITASIM_SHOT_DIR": str(run_dir), "VITASIM_STATS": str(run_dir / "stats.json")}
    if script:
        sp = Path(script) if Path(script).is_absolute() else root / script
        if not sp.exists():
            usage(f"no such input script: {script}")
        env["VITASIM_INPUT"] = str(sp)
        shutil.copy2(sp, run_dir / "input.txt")
    when = shot_at if shot_at is not None else min(5.0, timeout / 2)
    if shot and not os_screenshot:
        env["VITASIM_SHOT_AT"] = f"{when:g}"
    r = run_bounded([str(exe), *args], root, run_dir, timeout, env=env, shot_at=when if (shot and os_screenshot) else None,
                    shot=(lambda f, pid: os_shot(f, pid, exe)) if os_screenshot else None)
    log = ux0 / "data" / folder / "vitaport.log"
    if log.exists() and log.stat().st_mtime >= time.time() - r.get("seconds", 0) - 5:
        shutil.copy2(log, run_dir / "vitaport.log")
    stats = {}
    if (run_dir / "stats.json").exists():
        try:
            stats = json.loads((run_dir / "stats.json").read_text(encoding="utf-8"))
        except ValueError:
            stats = {}
    stderr = "\n".join(r.get("stderr_tail", []))
    oom_hit = "VITASIM OOM" in stderr or bool(stats.get("oom"))
    shots = sorted(rel(root, p) for p in run_dir.glob("*.png"))
    r.update(run_dir=rel(root, run_dir), stats=stats, oom=oom_hit, memory_budget_mb=mem, staged_assets=staged, screenshots=shots,
             vitaport_log=rel(root, run_dir / "vitaport.log") if (run_dir / "vitaport.log").exists() else None)
    r["ok"] = r.get("ok", False) and not oom_hit and not r.get("error")
    if not stats:
        r["note"] = "no stats.json: is the game linked with the vitaport simulation backend (vitaport_link_sim) and calling vp_init/vp_frame?"
    return r


def main(a):
    root = project_root()
    cfg = load_config(root)
    if not cfg:
        usage("no vita.toml here: run `vita init` first")
    res: dict = {}
    if not a.no_convert and (root / (cfg.get("assets", {}).get("source") or "data")).is_dir():
        from vita_porter.assets import convert
        c = convert(root)
        res["assets"] = dict(ok=c["ok"], converted=c["converted"], kept=c["kept"], failed=c["failed"])
        if not c["ok"]:
            res["ok"] = False
    if not a.no_build:
        if not shutil.which("cmake"):
            usage("cmake is not on PATH (see `vita tools check`)")
        b = build_sim(root, cfg, a.config, a.define or [])
        res["build"] = b
        if not b["ok"]:
            res["ok"] = False
            return _report(res, a.json)
    args = a.args[1:] if a.args and a.args[0] == "--" else (a.args or list(cfg.get("sim", {}).get("args", [])))
    exe = find_exe(root, cfg, a.exe)
    r = run_sim(root, cfg, exe, args, a.timeout, a.shot, a.shot_at, a.memory, a.enter, a.input, a.oom, a.os_shot)
    res["run"] = r
    res["ok"] = res.get("ok", True) and r["ok"]
    return _report(res, a.json)


def _report(res: dict, as_json: bool) -> int:
    res.setdefault("ok", False)
    if as_json:
        emit_json(res)
        return OK if res["ok"] else PROBLEM
    if "assets" in res:
        x = res["assets"]
        print(f"assets: converted {x['converted']}, up to date {x['kept']}, failed {len(x['failed'])}")
    b = res.get("build")
    if b:
        if b["ok"]:
            print(f"simulation build OK ({b['seconds']} s). Log: {b['log']}")
        else:
            print(f"simulation {b['stage']} FAILED (exit {b['exit_code']}). Full log: {b['log']}")
            for e in b["errors"]:
                print(f"  {(e.get('file') or '') + (':' + str(e['line']) if e.get('line') else '')}: {e['message']}")
    r = res.get("run")
    if r:
        if r.get("error"):
            print(f"run: {r['error']}")
        else:
            state = f"killed at the {r['seconds']} s timeout" if r["timed_out"] else f"exited {r['exit_code']} after {r['seconds']} s"
            print(f"{r['cmd'][0]} (pid {r['pid']}): {state}{'  CRASHED' if r.get('crashed') else ''}{'  OUT OF MEMORY' if r.get('oom') else ''}")
            st = r.get("stats") or {}
            if st:
                print(f"  frames {st.get('frames')}, {st.get('fps')} fps, peak memory {st.get('mem_peak', 0) / 1048576:.1f} MiB of "
                      f"{st.get('mem_budget', 0) / 1048576:.0f} MiB" + (", quit by the input script" if st.get("quit_by_script") else ""))
            print(f"  output: {r['run_dir']}/" + (f"  (log: {r['vitaport_log']})" if r.get("vitaport_log") else ""))
            for s in r.get("screenshots", []):
                print(f"  screenshot: {s}")
            for s in r.get("stderr_tail", [])[-12:]:
                print(f"    {s}")
            if r.get("note"):
                print(f"  note: {r['note']}")
    print("PASS" if res["ok"] else "FAIL")
    return OK if res["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("sim", help="build and run the PC Vita-simulation profile (960x544, Vita controls, memory cap)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--timeout", type=float, default=60.0, help="seconds before the process is killed (default 60)")
    p.add_argument("--shot", action="store_true", help="one screenshot (by the kit's readback; --os-shot for a window capture)")
    p.add_argument("--shot-at", type=float, help="seconds after start for the screenshot (default min(5, timeout/2))")
    p.add_argument("--os-shot", action="store_true", help="capture the window with OS tools instead of the kit's readback")
    p.add_argument("--input", help="scripted input file (see above)")
    p.add_argument("--memory", type=int, help="memory cap in MiB (default [sim] memory_mb, else 128)")
    p.add_argument("--oom", choices=["abort", "null"], default="abort", help="over the cap: abort (default) or return NULL")
    p.add_argument("--enter", choices=["cross", "circle"], default="cross", help="the simulated system confirm button")
    p.add_argument("--config", default="RelWithDebInfo", choices=["Debug", "Release", "RelWithDebInfo"])
    p.add_argument("-D", "--define", action="append", help="extra CMake cache entry for the simulation build")
    p.add_argument("--exe", help="executable to run instead of [sim] exe")
    p.add_argument("--no-build", action="store_true", help="run the existing build")
    p.add_argument("--no-convert", action="store_true", help="don't run `vita assets convert` first")
    p.add_argument("--json", action="store_true")
    p.add_argument("args", nargs=argparse.REMAINDER, help="arguments for the game (after --)")
    p.set_defaults(func=main)
