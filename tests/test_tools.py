"""vita tools check with a mocked PATH (fake executables), the registry, and Vita3K being optional."""
from __future__ import annotations

import json
import os
import stat
import sys

import pytest
from conftest import vita

from vita_porter import tools


def fake_bin(d, name, out=""):
    d.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        p = d / f"{name}.bat"
        p.write_text(f"@echo off\necho {out}\n")
    else:
        p = d / name
        p.write_text(f"#!/bin/sh\necho '{out}'\n")
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def test_registry_is_consistent():
    reg = tools.registry()
    g = reg["groups"]["check"]
    for tid in g["required"] + g["optional"] + [t for grp in g["one_of"] for t in grp]:
        assert tid in reg["tools"], tid
    for tid, spec in reg["tools"].items():
        assert spec.get("homepage") and spec.get("install"), tid
        if spec.get("kind", "bin") == "bin":
            assert spec.get("bin"), tid
        for osk in spec.get("platforms", ["windows", "linux", "macos"]):
            if osk in ("windows", "linux"):
                assert spec["install"].get(osk), (tid, osk)
    assert "vita3k" in g["optional"], "Vita3K is optional"


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script fakes")
def test_mocked_path_everything_missing(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = tools.check_all({}, path=str(empty))
    assert not r["ok"] and r["toolchain"]["chosen"] is None
    assert {"cmake", "git", "ffmpeg", "pngquant"} <= set(r["missing"]) and "vita3k" not in r["missing"]
    text = tools.format_check(r)
    assert "MISSING: stop here" in text and "never installs" in text and "docker pull vitasdk/vitasdk:latest" in text
    assert "Vita3K is not installed: optional" in text


@pytest.mark.skipif(sys.platform == "win32", reason="shell-script fakes")
def test_mocked_path_with_fakes(tmp_path):
    b = tmp_path / "bin"
    fake_bin(b, "cmake", "cmake version 3.10.2")       # too old
    fake_bin(b, "git", "git version 2.43.0")
    fake_bin(b, "g++", "g++ (GCC) 13.3.0")
    fake_bin(b, "ffmpeg", "ffmpeg version 6.1.1")
    fake_bin(b, "pngquant", "2.18.0 (January 2023)")
    fake_bin(b, "Vita3K", "Vita3K 0.2.0")
    r = tools.check_all({}, path=str(b))
    by = {t["id"]: t for t in r["required"] + r["optional"]}
    assert by["git"]["ok"] and by["ffmpeg"]["version"] == "6.1.1" and by["pngquant"]["ok"]
    assert not by["cmake"]["ok"] and "older than" in by["cmake"]["note"]
    assert by["vita3k"]["ok"]
    assert "cmake" in r["missing"] and not r["ok"]


def test_vitacompanion_only_checked_with_an_ip(tmp_path):
    r = tools.check_all({}, path=str(tmp_path))
    assert r["device"].get("skipped")
    r2 = tools.check_all({"device": {"ip": "127.0.0.1", "ftp_port": 1, "cmd_port": 2}}, path=str(tmp_path))
    assert not r2["device"].get("skipped") and not r2["device"]["ok"] and "vitacompanion" in r2["missing"]


def test_vdpm_packages_from_the_pacman_db(tmp_path, monkeypatch):
    sdk = tmp_path / "vitasdk"
    (sdk / "bin").mkdir(parents=True)
    (sdk / "bin" / "arm-vita-eabi-gcc").write_text("")
    (sdk / "share").mkdir()
    (sdk / "share" / "vita.toolchain.cmake").write_text("")
    db = sdk / "var" / "lib" / "pacman" / "local"
    for n in ("vitaGL-0.0.0.r1488.g2bdbe89-1", "sdl2_vitagl-2.32.8-1"):
        (db / n).mkdir(parents=True)
    monkeypatch.setenv("VITASDK", str(sdk))
    have = tools.vdpm_installed_native(sdk)
    assert have["vitaGL"] == "0.0.0.r1488.g2bdbe89-1" and "sdl2_vitagl" in have
    r = tools.check_all({"build": {"vdpm": ["sdl2", "freetype"]}})
    pk = {p["name"]: p for p in r["packages"]}
    assert pk["vitaGL"]["ok"] and pk["sdl2"]["ok"] and pk["sdl2"]["installed_as"] == "sdl2_vitagl"
    assert not pk["freetype"]["ok"] and "vdpm:freetype" in r["missing"]


def test_cli(tmp_path):
    r = vita("tools", "check", "--mock-path", str(tmp_path), "--json", cwd=tmp_path)
    assert r.returncode == 1 and json.loads(r.stdout)["missing"]
    assert vita("tools", "list", cwd=tmp_path).returncode == 0
    assert "vita3k" in vita("tools", "show", "vita3k", cwd=tmp_path).stdout.lower()
    assert vita("tools", "show", "nope", cwd=tmp_path).returncode == 2
