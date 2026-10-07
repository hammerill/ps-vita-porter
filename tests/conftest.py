"""Shared helpers: synthetic fixtures built in-test (no real games, no real .vpk files) and repo helpers.
Repo helpers adapted from universal-decompiler's tests/conftest.py (MIT, same author)."""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vita_porter import sfo  # noqa: E402
from vita_porter.images import write_png  # noqa: E402


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@localhost", "-c", "init.defaultBranch=main", *args],
                          cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An empty git repo as the cwd (a fresh game repo)."""
    d = tmp_path / "game"
    d.mkdir()
    git(d, "init", "-q")
    monkeypatch.chdir(d)
    monkeypatch.setenv("VITA_PUBLISH_OFFLINE", "1")
    monkeypatch.setenv("VITA_PORTER_HOME", str(tmp_path / "home"))
    return d


def vita(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run the CLI as a subprocess (python -m vita_porter) so exit codes and stdout are real."""
    e = {**os.environ, "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""), **(env or {})}
    return subprocess.run([sys.executable, "-m", "vita_porter", *args], cwd=cwd, capture_output=True, text=True, env=e,
                          encoding="utf-8", errors="replace")


def make(root: Path, files: dict) -> Path:
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
    return root


# --------------------------------------------------------------------------- LiveArea / .vpk fixtures

def indexed_png(path: Path, w: int, h: int, colours: int = 256, trns: bool = False, depth: int = 8):
    pal = bytes(c for i in range(colours) for c in (i % 256, (i * 7) % 256, (i * 13) % 256))
    idx = bytes((x + y) % colours for y in range(h) for x in range(w))
    if depth == 8:
        write_png(path, w, h, idx, color_type=3, palette=pal, trns=b"\x00" * min(colours, 4) if trns else None)
    else:
        raise ValueError("only 8-bit indexed fixtures")


def good_sce_sys(root: Path) -> Path:
    s = root / "sce_sys"
    (s / "livearea" / "contents").mkdir(parents=True, exist_ok=True)
    indexed_png(s / "icon0.png", 128, 128, 64)
    indexed_png(s / "pic0.png", 960, 544, 256)
    indexed_png(s / "livearea" / "contents" / "bg0.png", 840, 500, 128)
    indexed_png(s / "livearea" / "contents" / "startup.png", 280, 158, 32, trns=True)
    (s / "livearea" / "contents" / "template.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<livearea style="a1" format-ver="01.00" content-rev="1">\n'
        "    <livearea-background><image>bg0.png</image></livearea-background>\n"
        "    <gate><startup-image>startup.png</startup-image></gate>\n</livearea>\n", encoding="utf-8")
    return s


def fake_self(unsafe: bool = False, machine: int = 0x28) -> bytes:
    """Just enough of a SELF for `vita vpk check`: SCE header, appinfo offset at 0x38 -> authid, ELF at 0xA0."""
    b = bytearray(0x200)
    b[0:4] = b"SCE\0"
    struct.pack_into("<Q", b, 0x38, 0x80)
    struct.pack_into("<Q", b, 0x40, 0xA0)
    struct.pack_into("<Q", b, 0x80, 0x2F00000000000001 if unsafe else 0x2F00000000000002)
    b[0xA0:0xA4] = b"\x7fELF"
    struct.pack_into("<H", b, 0xA0 + 18, machine)
    return bytes(b)


def make_vpk(path: Path, root_for_sce: Path, title_id: str = "TEST00001", name: str = "Test", version: str = "01.00",
             unsafe: bool = False, extra: dict | None = None, attribute2: int = 0, skip: tuple = ()) -> Path:
    sce = good_sce_sys(root_for_sce)
    with zipfile.ZipFile(path, "w") as z:
        if "eboot.bin" not in skip:
            z.writestr("eboot.bin", fake_self(unsafe))
        vals = {"TITLE_ID": title_id, "TITLE": name, "APP_VER": version, "ATTRIBUTE2": attribute2, "CATEGORY": "gd"}
        z.writestr("sce_sys/param.sfo", sfo.build(vals))
        for p in sce.rglob("*"):
            if p.is_file() and p.relative_to(sce.parent).as_posix() not in skip:
                z.write(p, p.relative_to(sce.parent).as_posix())
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return path


def have(*tools: str) -> bool:
    return all(shutil.which(t) for t in tools)
