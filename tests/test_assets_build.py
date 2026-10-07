"""vita assets convert/check (copy, resize, DXT, audio), the DXT encoder, and vita build's pieces that don't
need a VitaSDK (error parsing, -D values, output discovery, backend choice). A real build runs when $VITASDK is set."""
from __future__ import annotations

import json
import os
import struct
import wave

import pytest
from conftest import ROOT, have, make, vita

from vita_porter import build, texture
from vita_porter.images import sniff, write_png

RULES = """
[[assets.rule]]
glob = "tex/*.png"
action = "texture"
max_size = 64
format = "dds-dxt5"

[[assets.rule]]
glob = "ui/*.png"
action = "texture"
format = "png"
scale = 0.5
filter = "neighbor"

[[assets.rule]]
glob = "**/*.wav"
action = "audio"
format = "wav"
rate = 22050
channels = 1

[[assets.rule]]
glob = "junk/*"
action = "skip"

[[assets.rule]]
glob = "**/*"
action = "copy"
"""


def project(repo):
    vita("init", "--no-hook", cwd=repo)
    t = (repo / "vita.toml").read_text()
    t = t.replace('[[assets.rule]]\nglob = "**/*"\naction = "copy"\n', RULES).replace('source = "assets"', 'source = "assets"')
    (repo / "vita.toml").write_text(t)
    (repo / "assets" / "tex").mkdir(parents=True)
    (repo / "assets" / "ui").mkdir()
    write_png(repo / "assets" / "tex" / "wall.png", 128, 96, b"".join(bytes((x * 2, y * 2, 128, 255)) for y in range(96) for x in range(128)),
              color_type=6)
    write_png(repo / "assets" / "ui" / "font.png", 32, 16, b"\xff\x00\x00" * 32 * 16)
    with wave.open(str(repo / "assets" / "jump.wav"), "wb") as w:
        w.setnchannels(2), w.setsampwidth(2), w.setframerate(44100)
        w.writeframes(b"\x00\x10" * 2 * 4410)
    make(repo, {"assets/levels/1.map": "0101\n", "assets/junk/x.tmp": "x"})
    return repo


def test_dxt_roundtrip():
    w, h = 8, 8
    rgba = bytes(c for y in range(h) for x in range(w) for c in ((255, 0, 0, 255) if x < 4 else (0, 0, 255, 128)))
    for fmt in ("dxt1", "dxt5"):
        blocks = texture.encode(rgba, w, h, fmt)
        assert len(blocks) == (w // 4) * (h // 4) * (8 if fmt == "dxt1" else 16)
        out = texture.decode_dxt(blocks, w, h, fmt)
        for i in range(0, len(out), 4):
            assert all(abs(a - b) <= 8 for a, b in zip(out[i:i + 3], rgba[i:i + 3], strict=True))
            if fmt == "dxt5":
                assert abs(out[i + 3] - rgba[i + 3]) <= 2
    d = texture.dds(w, h, "dxt5", texture.encode(rgba, w, h, "dxt5"))
    assert d[:4] == b"DDS " and struct.unpack("<II", d[12:20]) == (h, w) and d[84:88] == b"DXT5"


@pytest.mark.skipif(not have("ffmpeg"), reason="needs ffmpeg")
def test_convert_and_check(repo):
    project(repo)
    r = vita("assets", "convert", "--json", cwd=repo)
    assert r.returncode == 0, r.stdout + r.stderr
    j = json.loads(r.stdout)
    assert j["converted"] == 4 and not j["failed"]
    out = repo / "build-vita" / "assets"
    dds = sniff(out / "tex" / "wall.dds")
    assert dds["format"] == "dds" and (dds["width"], dds["height"]) == (64, 48) and dds["compressed"] == "DXT5"
    font = sniff(out / "ui" / "font.png")
    assert (font["width"], font["height"]) == (16, 8)
    with wave.open(str(out / "jump.wav")) as w:
        assert (w.getframerate(), w.getnchannels()) == (22050, 1)
    assert (out / "levels" / "1.map").read_text() == "0101\n" and not (out / "junk").exists()
    again = json.loads(vita("assets", "convert", "--json", cwd=repo).stdout)
    assert again["converted"] == 0 and again["kept"] == 4
    c = vita("assets", "check", "--json", cwd=repo)
    assert c.returncode == 0, c.stdout
    cj = json.loads(c.stdout)
    assert cj["ok"] and cj["texture_memory_estimate"] == 64 * 48 + 16 * 8 * 4 and "app0" in cj["destination"]
    (out / "levels" / "1.map").unlink()
    c2 = json.loads(vita("assets", "check", "--json", cwd=repo).stdout)
    assert not c2["ok"] and c2["missing"] == ["levels/1.map"]


def test_dry_run_and_unmatched_media(repo):
    vita("init", "--no-hook", cwd=repo)
    make(repo, {"assets/a.png": b"\x89PNG", "assets/b.ogg": b"OggS"})
    j = json.loads(vita("assets", "convert", "--dry-run", "--json", cwd=repo).stdout)
    assert j["dry_run"] and j["converted"] == 2 and "matched no rule" in j["note"]


def test_parse_errors():
    log = "\n".join([
        "/src/a.cpp:12:5: error: 'vglEnd' was not declared in this scope",
        "/usr/local/vitasdk/arm-vita-eabi/bin/ld: main.o: in function `main':",
        "main.cpp:(.text+0x6): undefined reference to `sceFooBar'",
        "CMake Error at CMakeLists.txt:7 (find_package):",
        "  Could not find SDL2",
        "Unable to relocate ELF sections",
        "warning: unused variable",
    ])
    errs, n, warns = build.parse_errors(log)
    msgs = " | ".join(e["message"] for e in errs)
    assert n == 4 and warns == 1
    assert "'vglEnd' was not declared" in msgs and "undefined reference to `sceFooBar'" in msgs and "Unable to relocate" in msgs
    assert errs[0]["line"] == 12


def test_defines_from_vita_toml(tmp_path):
    cfg = {"app": {"title_id": "ABCD00001", "name": "My Game", "version": "01.02", "data_folder": "MyGame", "assets": "external",
                   "unsafe": True, "extended_memory": False}, "assets": {"out": "build-vita/assets", "vpk_dir": "data"}}
    d = build.defines(tmp_path, cfg, "/src")
    assert "-DVITA_TITLEID=ABCD00001" in d and "-DVITA_APP_NAME=My Game" in d and "-DVITA_ASSETS_MODE=external" in d
    assert "-DVITA_UNSAFE=ON" in d and "-DVITA_EXTENDED_MEMORY=OFF" in d and "-DVITA_ASSETS_DIR=/src/build-vita/assets" in d
    assert "-DVITA_ASSETS_VPK_DIR=data" in d and "-DVITA_LIVEAREA_DIR=/src/sce_sys" in d


def test_find_outputs(tmp_path):
    out = tmp_path / "build-vita"
    (out / "CMakeFiles").mkdir(parents=True)
    elf = bytearray(4096)
    elf[0:4] = b"\x7fELF"
    elf[16:18] = b"\x02\x00"
    elf[18:20] = b"\x28\x00"
    (out / "game").write_bytes(bytes(elf))
    (out / "CMakeFiles" / "junk").write_bytes(bytes(elf))
    (out / "game.velf").write_bytes(b"\x7fELF" + b"\0" * 2000)
    (out / "game.vpk").write_bytes(b"PK")
    vpk, found, notes = build.find_outputs(out, {}, tmp_path, 0)
    assert vpk.name == "game.vpk" and found.name == "game" and not notes


def test_backend_choice(monkeypatch, tmp_path):
    monkeypatch.delenv("VITASDK", raising=False)
    assert build.pick_backend({}, None) == "docker"
    assert build.pick_backend({"build": {"backend": "docker"}}, None) == "docker"
    with pytest.raises(SystemExit):
        build.pick_backend({}, "native")


def test_build_without_cmakelists_is_a_usage_error(repo):
    vita("init", "--no-hook", cwd=repo)
    r = vita("build", "--native", cwd=repo, env={"VITASDK": os.environ.get("VITASDK", "/nonexistent")})
    assert r.returncode == 2


@pytest.mark.skipif(not (os.environ.get("VITASDK") and os.path.exists(os.path.join(os.environ.get("VITASDK", ""), "bin", "arm-vita-eabi-gcc"))),
                    reason="needs a native VitaSDK")
def test_native_build_of_a_minimal_project(repo):
    vita("init", "--kit", "--no-hook", "--title-id", "TEST00001", cwd=repo)
    make(repo, {"CMakeLists.txt": "cmake_minimum_required(VERSION 3.20)\nproject(mini C CXX)\ninclude(cmake/VitaPort.cmake)\n"
                                  "add_executable(mini main.c)\nif(VITA)\n  vitaport_link_vita(mini)\n  vitaport_package(mini)\nendif()\n",
                "main.c": "#include \"vitaport.h\"\n#include <psp2/kernel/processmgr.h>\nint main(void){ vp_config c = {0}; vp_init(&c);"
                          " vp_input in; vp_poll(&in); sceKernelExitProcess(0); return 0; }\n"})
    from conftest import good_sce_sys
    good_sce_sys(repo)
    r = vita("build", "--native", "--json", cwd=repo)
    j = json.loads(r.stdout)
    assert r.returncode == 0 and j["ok"], j
    assert j["vpk"].endswith("mini.vpk") and j["unresolved"] == []
    c = vita("vpk", "check", j["vpk"], "--assets", "external", "--json", cwd=repo)   # no assets in this project
    assert json.loads(c.stdout)["ok"], c.stdout


def test_example_vita_toml_matches_the_code():
    import tomllib
    cfg = tomllib.loads((ROOT / "examples" / "lumen-drift" / "vita.toml").read_text())
    assert cfg["app"]["title_id"] == "LMDR00001" and cfg["app"]["assets"] == "embedded"
    assert "VP_DATA_FOLDER" in (ROOT / "examples" / "lumen-drift" / "src" / "platform" / "vita_input.h").read_text()
