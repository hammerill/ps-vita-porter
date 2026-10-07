"""Small helpers shared by the commands: platform checks, WSL paths, git, output, exit codes, vita.toml.

Derived from universal-modder's um/common.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors),
via universal-decompiler's ud/common.py.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

OK, PROBLEM, USAGE = 0, 1, 2
# Text files we write are UTF-8 with \n line ends on every OS (Windows would otherwise use its ANSI code page).
TEXT = {"encoding": "utf-8", "newline": "\n"}
CONFIG = "vita.toml"

# Title IDs: 4 uppercase letters + 5 digits. Prefixes used by Sony's own retail, PSN and system software, plus
# the SDK samples' VSDK: a homebrew must not reuse them (it would replace or collide with the real app).
TITLE_ID_RX = re.compile(r"^[A-Z]{4}[0-9]{5}$")
RESERVED_PREFIXES = ("PCSA", "PCSB", "PCSC", "PCSD", "PCSE", "PCSF", "PCSG", "PCSH", "PCSI", "PCSJ", "PCSK", "PCSL",
                     "NPXS", "NPXX", "NPEA", "NPEB", "NPEE", "NPEG", "NPEH", "NPJA", "NPJB", "NPJG", "NPJH", "NPUA", "NPUB",
                     "NPUG", "NPUH", "NPUX", "NPHA", "NPHB", "NPHG", "NPHH", "VCAS", "VCJS", "VCKS", "VLAS", "VLJM", "VLJS",
                     "VLKS", "VSDK")


def is_windows() -> bool:
    return os.name == "nt"


def is_mac() -> bool:
    return sys.platform == "darwin"


def is_wsl() -> bool:
    if sys.platform != "linux":
        return False
    return "microsoft" in platform.release().lower() or os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop")


def os_key() -> str:
    """windows | linux | macos: the key used for per-OS install steps in tools.toml."""
    return "windows" if is_windows() else "macos" if is_mac() else "linux"


def ps_exe() -> str:
    """Windows PowerShell. Falls back to its full path: an agent's PATH often lacks System32\\WindowsPowerShell\\v1.0."""
    name = "powershell.exe" if is_wsl() else "powershell"
    found = shutil.which(name)
    if found:
        return found
    if is_wsl():
        full = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
    else:
        full = os.path.join(os.environ.get("SystemRoot") or r"C:\Windows", "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return full if os.path.exists(full) else name


def to_win(path: str | Path) -> str:
    """/mnt/c/Games/x -> C:\\Games\\x (WSL); paths that are already Windows paths pass through."""
    p = str(path)
    if len(p) > 1 and p[1] == ":":
        return p
    if p.startswith("/mnt/") and len(p) > 6 and p[6] == "/" and p[5].isalpha():
        return p[5].upper() + ":\\" + p[7:].replace("/", "\\")
    if is_wsl() and shutil.which("wslpath"):
        return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True).stdout.strip()
    return p


def to_posix(path: str | Path) -> str:
    """C:\\Games\\x -> /mnt/c/Games/x under WSL; unchanged elsewhere."""
    p = str(path)
    if is_wsl() and len(p) > 1 and p[1] == ":":
        return "/mnt/" + p[0].lower() + p[2:].replace("\\", "/")
    return p


def data_dir() -> Path:
    """Per-user state (the knowledge-base cache). Override with VITA_PORTER_HOME."""
    d = Path(os.environ.get("VITA_PORTER_HOME", Path.home() / ".ps-vita-porter"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def die(msg: str, code: int = PROBLEM) -> NoReturn:
    print(f"vita: {msg}", file=sys.stderr)
    sys.exit(code)


def usage(msg: str) -> NoReturn:
    die(msg, USAGE)


def emit_json(obj):
    print(json.dumps(obj, indent=2, default=str, ensure_ascii=False))


def git(args: list[str], cwd: str | Path | None = None, check: bool = False) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        die("git is not installed or not on PATH")
    if check and r.returncode:
        die(f"git {' '.join(args[:3])} failed: {(r.stderr or r.stdout).strip()[-800:]}")
    return r


def find_repo(start: str | Path | None = None) -> Path | None:
    """Top of the git work tree that contains `start` (default: cwd), or None."""
    r = git(["rev-parse", "--show-toplevel"], cwd=start or Path.cwd())
    return Path(r.stdout.strip()) if r.returncode == 0 else None


def repo_root(start: str | Path | None = None) -> Path:
    """Like find_repo, but a missing repo ends the command with instructions."""
    root = find_repo(start)
    if root is None:
        die("not inside a git repository: run vita from the game's source repo (the one with its CMakeLists.txt)")
    return root


def project_root(start: str | Path | None = None) -> Path:
    """The port's root: the nearest folder (from `start`, default cwd, up to the git top level) holding vita.toml,
    else the git top level. Lets a project live in a sub-folder of a bigger repo (e.g. examples/)."""
    top = repo_root(start)
    here = Path(start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        if (d / CONFIG).exists():
            return d
        if d == top.resolve():
            break
    return top


def find_project(start: str | Path | None = None) -> Path | None:
    """Like project_root, but None outside a git repository."""
    return project_root(start) if find_repo(start) else None


def load_config(root: Path) -> dict:
    """vita.toml at the project root (written by `vita init`); {} if absent."""
    import tomllib
    p = root / CONFIG
    if not p.exists():
        return {}
    try:
        return tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        die(f"{p} is not valid TOML: {e}")


def is_ud_repo(root: Path) -> bool:
    """A universal-decompiler reconstruction: ud.toml or DECOMP_PLAN.md + decomp/progress.json."""
    return (root / "ud.toml").exists() or ((root / "DECOMP_PLAN.md").exists() and (root / "decomp" / "progress.json").exists())


def title_id_problems(tid: str) -> list[str]:
    """Format and reserved-prefix problems of a title ID ([] = fine)."""
    out = []
    if not TITLE_ID_RX.match(tid or ""):
        out.append(f"title ID {tid!r} must be 4 uppercase letters + 5 digits (e.g. ABCD00001)")
    elif tid.startswith(RESERVED_PREFIXES):
        out.append(f"title ID {tid!r} uses the reserved prefix {tid[:4]} (Sony retail/PSN/system or SDK samples)")
    return out


def rel(root: Path, p: Path) -> str:
    """Path relative to the repo when possible, posix style."""
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def human(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB"):
        if abs(n) < 1024 or unit == "GiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GiB"
