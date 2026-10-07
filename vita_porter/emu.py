"""Run the .vpk in Vita3K, if it's installed: install + launch, capture its log and the app's own log, take a
screenshot, stop at the timeout (by PID). Vita3K's compatibility limits are not port bugs: log what you see.

    vita emu                               # the .vpk from the last `vita build`: install and run it (Vita3K <vpk>)
    vita emu --shot --timeout 40           # one window screenshot (after 15 s, or --shot-at)
    vita emu --installed                   # run the already installed title (Vita3K -r <TITLEID>), no reinstall
    vita emu --vpk build-vita-ext/lumen-drift.vpk --renderer vulkan
    vita emu --json

Vita3K's command line (checked against vita3k/config/src/config.cpp, 2026-10-07): a positional .vpk/.zip path
installs and runs it; -r/--installed-path <TITLEID> runs an installed app; -B/--backend-renderer OpenGL|Vulkan;
-F fullscreen; -c config location. Vita3K needs the firmware and the font firmware installed once by the user.
Where Vita3K is: [emu] vita3k in vita.toml, $VITA3K, PATH (Vita3K, vita3k), ~/Applications/Vita3K*.AppImage,
%LOCALAPPDATA%/Vita3K/Vita3K.exe.
Output in build-vita/vita-emu/<time>/: stdout.txt (Vita3K logs there too), stderr.txt, copies of vita3k.log and of
the app's ux0:data/<data_folder>/vitaport.log from Vita3K's virtual ux0, screenshots.
Not installed: prints SKIPPED and exits 0 (the emulator level is optional).
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import shutil
import time
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, is_mac, is_windows, is_wsl, load_config, project_root, rel, to_posix, to_win, usage
from vita_porter.proc import os_shot, run_bounded
from vita_porter.tools import find_vita3k


def pref_dirs(exe: str) -> list[Path]:
    """Where Vita3K keeps vita3k.log and its virtual ux0 (pref path), most likely first."""
    out = [Path(exe).resolve().parent]
    if is_windows():
        out.append(Path(os.environ.get("APPDATA", "")) / "Vita3K" / "Vita3K")
    elif is_wsl() and exe.lower().endswith(".exe"):
        appdata = os.popen("cmd.exe /c echo %APPDATA% 2>/dev/null").read().strip()
        if appdata and "%" not in appdata:
            out.append(Path(to_posix(appdata)) / "Vita3K" / "Vita3K")
    elif is_mac():
        out.append(Path.home() / "Library" / "Application Support" / "Vita3K")
    else:
        out += [Path.home() / ".local" / "share" / "Vita3K" / "Vita3K", Path.home() / ".local" / "share" / "Vita3K"]
    return [p for p in out if p.is_dir()]


def pick_vpk(root: Path, cfg: dict, override: str | None) -> Path:
    if override:
        p = Path(override) if Path(override).is_absolute() else root / override
    elif cfg.get("build", {}).get("vpk"):
        p = root / cfg["build"]["vpk"]
    else:
        out = root / cfg.get("build", {}).get("build_dir", "build-vita")
        cands = sorted(out.glob("*.vpk"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not cands:
            usage(f"no .vpk in {rel(root, out)}: run `vita build` first (or pass --vpk)")
        p = cands[0]
    if not p.exists():
        usage(f"no such .vpk: {p}")
    return p


def emu(root: Path, cfg: dict, vpk_arg: str | None, timeout: float, shot: bool, shot_at: float | None, installed: bool,
        renderer: str | None, extra: list[str]) -> dict:
    exe = find_vita3k(cfg)
    if not exe:
        return dict(ok=True, skipped=True, reason="Vita3K is not installed (optional): the emulator level is skipped; see `vita tools show vita3k`")
    app = cfg.get("app", {})
    tid = app.get("title_id")
    win_exe = exe.lower().endswith(".exe") and is_wsl()
    if installed:
        if not tid:
            usage("--installed needs [app] title_id in vita.toml")
        cmd = [exe, "-r", tid]
        vpk = None
    else:
        vpk = pick_vpk(root, cfg, vpk_arg)
        cmd = [exe, to_win(vpk) if win_exe else str(vpk)]
    if renderer:
        cmd += ["-B", {"opengl": "OpenGL", "vulkan": "Vulkan"}[renderer]]
    cmd += list(cfg.get("emu", {}).get("args", [])) + extra
    run_dir = root / cfg.get("build", {}).get("build_dir", "build-vita") / "vita-emu" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    t0 = time.time()
    r = run_bounded(cmd, root, run_dir, timeout, shot_at=(shot_at if shot_at is not None else min(15.0, timeout / 2)) if shot else None,
                    shot=lambda f, pid: os_shot(f, pid, Path(exe)))
    logs = []
    for d in pref_dirs(exe):
        for pat in ("vita3k*.log", "logs/vita3k*.log"):
            for m in glob.glob(str(d / pat)):
                mp = Path(m)
                if mp.stat().st_mtime >= t0 - 1:
                    dst = run_dir / mp.name
                    shutil.copy2(mp, dst)
                    logs.append(rel(root, dst))
        folder = app.get("data_folder")
        if folder:
            vl = d / "ux0" / "data" / folder / "vitaport.log"
            if vl.exists() and vl.stat().st_mtime >= t0 - 1:
                shutil.copy2(vl, run_dir / "vitaport.log")
                logs.append(rel(root, run_dir / "vitaport.log"))
    text = "\n".join(r.get("stdout_tail", []) + r.get("stderr_tail", []))
    for lg in logs:
        try:
            text += "\n" + (root / lg).read_text(encoding="utf-8", errors="replace")[-20000:]
        except OSError:
            pass
    markers = {k: (k.lower() in text.lower()) for k in ("Installation succeeded", "Failed to install", "Firmware", "unimplemented", "error")}
    r.update(vita3k=exe, vpk=rel(root, vpk) if vpk else None, logs=logs, markers=markers, run_dir=rel(root, run_dir),
             screenshots=[rel(root, Path(s["file"])) for s in r.get("screenshots", []) if Path(s["file"]).exists()],
             shot_results=[s["result"] for s in r.get("screenshots", [])])
    r["note"] = "Vita3K's compatibility limits are not port bugs: log what you see in PORTLOG.md; the hardware decides."
    return r


def main(a):
    root = project_root()
    cfg = load_config(root)
    extra = a.args[1:] if a.args and a.args[0] == "--" else a.args
    r = emu(root, cfg, a.vpk, a.timeout, a.shot, a.shot_at, a.installed, a.renderer, extra or [])
    if a.json:
        emit_json(r)
        return OK if r.get("ok") else PROBLEM
    if r.get("skipped"):
        print(f"SKIPPED: {r['reason']}")
        return OK
    if r.get("error"):
        print(f"Vita3K: {r['error']}")
        return PROBLEM
    state = f"stopped at the {r['seconds']} s timeout" if r["timed_out"] else f"exited {r['exit_code']} after {r['seconds']} s"
    print(f"Vita3K {r['vita3k']} (pid {r['pid']}): {state}{'  CRASHED' if r.get('crashed') else ''}")
    print(f"  output: {r['run_dir']}/")
    for lg in r["logs"]:
        print(f"  log: {lg}")
    for s, res in zip(r["screenshots"], r["shot_results"], strict=False):
        print(f"  screenshot: {s}  [{res}]")
    seen = [k for k, v in r["markers"].items() if v]
    if seen:
        print(f"  log mentions: {', '.join(seen)}")
    for ln in r.get("stdout_tail", [])[-15:]:
        print(f"    {ln}")
    print(f"note: {r['note']}")
    return OK if r.get("ok") else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("emu", help="install and run the .vpk in Vita3K (if installed): logs, screenshots, stop at the timeout",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--vpk", help="the .vpk (default: [build] vpk, else the newest in the build folder)")
    p.add_argument("--installed", action="store_true", help="run the installed title (-r TITLEID) instead of installing")
    p.add_argument("--renderer", choices=["opengl", "vulkan"])
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--shot", action="store_true")
    p.add_argument("--shot-at", type=float)
    p.add_argument("--json", action="store_true")
    p.add_argument("args", nargs=argparse.REMAINDER, help="extra Vita3K arguments (after --)")
    p.set_defaults(func=main)
