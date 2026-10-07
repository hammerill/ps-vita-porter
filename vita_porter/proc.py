"""Run a program for a bounded time: capture stdout/stderr, take window screenshots, kill it by its exact PID.
Shared by `vita sim` and `vita emu`. Never kills by name pattern: only the PID (and process group/tree) it started.

Screenshot code adapted from universal-decompiler's ud/run.py (MIT, same author).
"""
from __future__ import annotations

import base64
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

from vita_porter.common import is_mac, is_windows, is_wsl, ps_exe, to_win

PS1 = Path(__file__).resolve().parent / "ps1" / "WinShot.ps1"


def shot_windows(out: Path, pid: int | None, name: str | None) -> str:
    target = to_win(out) if is_wsl() else str(out)
    pre = f"$TargetPid = {int(pid or 0)}; $Name = '{(name or '').replace(chr(39), '')}'; $Out = '{target.replace(chr(39), chr(39) * 2)}';\n"
    enc = base64.b64encode((pre + PS1.read_text(encoding="utf-8")).encode("utf-16-le")).decode()
    try:
        r = subprocess.run([ps_exe(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", enc],
                           capture_output=True, text=True, timeout=60, cwd="/mnt/c" if is_wsl() else None)
    except (OSError, subprocess.TimeoutExpired) as e:
        return f"error: {e}"
    msg = (r.stdout or r.stderr).strip().splitlines()
    return msg[-1] if msg else f"error: powershell exit {r.returncode}"


def shot_posix(out: Path, pid: int) -> str:
    if is_mac():
        r = subprocess.run(["screencapture", "-x", str(out)], capture_output=True)
        return "ok (whole screen, screencapture)" if r.returncode == 0 else "error: screencapture failed"
    if os.environ.get("DISPLAY") and shutil.which("xdotool") and shutil.which("import"):
        wins = subprocess.run(["xdotool", "search", "--onlyvisible", "--pid", str(pid)], capture_output=True, text=True).stdout.split()
        if wins:
            r = subprocess.run(["import", "-window", wins[-1], str(out)], capture_output=True, text=True)
            if r.returncode == 0:
                return f"ok (X11 window {wins[-1]})"
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("grim"):
        r = subprocess.run(["grim", str(out)], capture_output=True)
        if r.returncode == 0:
            return "ok (whole screen, grim)"
    if os.environ.get("DISPLAY") and shutil.which("import"):
        r = subprocess.run(["import", "-window", "root", str(out)], capture_output=True)
        if r.returncode == 0:
            return "ok (whole X11 screen)"
    return "error: no screenshot tool (install xdotool + imagemagick, or grim on Wayland)"


def os_shot(out: Path, pid: int, exe: Path) -> str:
    if is_windows() or (is_wsl() and exe.suffix.lower() == ".exe"):
        return shot_windows(out, pid if is_windows() else None, exe.stem if is_wsl() else None)
    return shot_posix(out, pid)


def kill_tree(p: subprocess.Popen, exe: Path, started: float):
    """Exact-PID kill: the process (Windows: its tree via taskkill /T; POSIX: the session/group we created)."""
    if p.poll() is not None:
        return
    if is_windows():
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            p.terminate()
        try:
            p.wait(3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                p.kill()
        if is_wsl() and exe.suffix.lower() == ".exe":
            # the Windows side of a WSL-launched .exe has its own PID: find exactly the one we started (name + start time)
            import datetime as dt
            ps = (f"Get-Process -Name '{exe.stem}' -ErrorAction SilentlyContinue | Where-Object {{ $_.StartTime -ge "
                  f"[DateTime]::Parse('{dt.datetime.fromtimestamp(started - 2).isoformat()}') }} | ForEach-Object {{ $_.Id }}")
            r = subprocess.run([ps_exe(), "-NoProfile", "-Command", ps], capture_output=True, text=True, cwd="/mnt/c")
            for wpid in r.stdout.split():
                if wpid.isdigit():
                    subprocess.run(["taskkill.exe", "/PID", wpid, "/T", "/F"], capture_output=True, cwd="/mnt/c")
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        pass


def tail(path: Path, n: int = 40) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def run_bounded(cmd: list[str], cwd: Path, outdir: Path, timeout: float, env: dict | None = None, shot_at: float | None = None,
                shot: Callable[[Path, int], str] | None = None, done: Callable[[], bool] | None = None) -> dict:
    """Start `cmd`, take one screenshot at `shot_at` seconds through `shot(path, pid)`, stop at `timeout` (or when
    `done()` turns true), kill by PID. stdout/stderr land in outdir. A crash = death by signal or an NTSTATUS code."""
    outdir.mkdir(parents=True, exist_ok=True)
    so, se = open(outdir / "stdout.txt", "wb"), open(outdir / "stderr.txt", "wb")
    kw: dict = {}
    if is_windows():
        kw["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kw["start_new_session"] = True
    t0 = time.time()
    try:
        p = subprocess.Popen(cmd, cwd=cwd, stdout=so, stderr=se, stdin=subprocess.DEVNULL, env=env, **kw)
    except OSError as e:
        so.close()
        se.close()
        return dict(ok=False, cmd=cmd, error=f"could not start: {e}", run_dir=str(outdir))
    shots, timed_out, stopped = [], False, False
    shot_done = shot is None or shot_at is None
    while True:
        if p.poll() is not None:
            break
        el = time.time() - t0
        if not shot_done and el >= (shot_at or 0):
            f = outdir / f"shot-{int(el)}s.png"
            shots.append(dict(file=str(f), result=shot(f, p.pid)))  # type: ignore[misc]
            shot_done = True
        if done and done():
            stopped = True
            kill_tree(p, Path(cmd[0]), t0)
            break
        if el >= timeout:
            timed_out = True
            kill_tree(p, Path(cmd[0]), t0)
            break
        time.sleep(0.1)
    so.close()
    se.close()
    rc = p.returncode
    killed = timed_out or stopped
    crashed = not killed and rc is not None and (rc < 0 or (rc & 0xFFFFFFFF) >= 0xC0000000)
    return dict(ok=not crashed, crashed=crashed, cmd=cmd, cwd=str(cwd), pid=p.pid, exit_code=None if killed else rc,
                timed_out=timed_out, stopped=stopped, seconds=round(time.time() - t0, 2), run_dir=str(outdir),
                stdout_tail=tail(outdir / "stdout.txt"), stderr_tail=tail(outdir / "stderr.txt"), screenshots=shots)
