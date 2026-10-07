"""vita livearea make/check (ya8, 16-bit and wrong-size images rejected) and vita vpk check on crafted .vpk files."""
from __future__ import annotations

import json
import zipfile

import pytest
from conftest import good_sce_sys, have, indexed_png, make_vpk, vita

from vita_porter import livearea, sfo, vpk
from vita_porter.images import expand_indexed_to_8bit, png_info, write_png


def test_good_sce_sys_passes(tmp_path):
    r = livearea.check(good_sce_sys(tmp_path))
    assert r["ok"], r["fails"]


def test_ya8_is_rejected(tmp_path):
    s = good_sce_sys(tmp_path)
    write_png(s / "icon0.png", 128, 128, b"\x80\xff" * 128 * 128, color_type=4)    # gray + alpha: the gist's bug
    r = livearea.check(s)
    assert not r["ok"] and any("grayscale+alpha" in f and "ya8" in f for f in r["fails"])


def test_16_bit_is_rejected(tmp_path):
    s = good_sce_sys(tmp_path)
    write_png(s / "livearea" / "contents" / "bg0.png", 840, 500, b"\x00\x10" * 3 * 840 * 500, color_type=2, bit_depth=16)
    r = livearea.check(s)
    assert any("bg0.png: 16 bits per channel" in f for f in r["fails"])


def test_wrong_size_alpha_and_palette_are_rejected(tmp_path):
    s = good_sce_sys(tmp_path)
    indexed_png(s / "pic0.png", 960, 540, 256)                      # wrong size
    indexed_png(s / "icon0.png", 128, 128, 16, trns=True)           # alpha where it isn't allowed
    r = livearea.check(s)
    assert any("pic0.png: 960x540, must be exactly 960x544" in f for f in r["fails"])
    assert any("icon0.png: has alpha" in f for f in r["fails"])
    indexed_png(s / "pic0.png", 960, 544, 200)                      # not exactly 256 colours
    assert any("exactly 256" in f for f in livearea.check(s)["fails"])
    write_png(s / "pic0.png", 960, 544, b"\x01\x02\x03" * 960 * 544)  # RGB, not indexed
    assert any("must be indexed" in f for f in livearea.check(s)["fails"])


def test_template_xml_checks(tmp_path):
    s = good_sce_sys(tmp_path)
    t = s / "livearea" / "contents" / "template.xml"
    t.write_text(t.read_text().replace('style="a1"', 'style="b2"').replace("bg0.png", "missing.png"))
    fails = livearea.check(s)["fails"]
    assert any("style 'b2'" in f for f in fails) and any("missing.png" in f for f in fails)
    t.write_text("<livearea")
    assert any("not valid XML" in f for f in livearea.check(s)["fails"])


def test_low_bit_depth_is_reexpanded(tmp_path):
    # a 4-bit indexed PNG (what pngquant writes for few colours) becomes 8-bit with the same pixels
    import struct
    import zlib
    w, h = 10, 3
    rows = b""
    for y in range(h):
        nib = [(x + y) % 4 for x in range(w)] + [0]
        rows += b"\x00" + bytes((nib[i] << 4) | nib[i + 1] for i in range(0, w, 2))
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    p = tmp_path / "q.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 4, 3, 0, 0, 0))
                  + chunk(b"PLTE", bytes(range(12))) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    assert png_info(p)["bit_depth"] == 4
    assert expand_indexed_to_8bit(p)
    i = png_info(p)
    assert i["bit_depth"] == 8 and i["palette_entries"] == 4 and (i["width"], i["height"]) == (w, h)
    from vita_porter.images import _chunks, _unfilter
    raw = zlib.decompress(b"".join(b for t, b in _chunks(p.read_bytes()) if t == b"IDAT"))
    px = _unfilter(raw, h, w, 1)
    assert list(px[:w]) == [x % 4 for x in range(w)] and list(px[w:2 * w]) == [(x + 1) % 4 for x in range(w)]


@pytest.mark.skipif(not have("ffmpeg", "pngquant"), reason="needs ffmpeg and pngquant")
def test_make_from_rgb_sources_then_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_png(tmp_path / "art.png", 400, 300, b"".join(bytes((x % 256, y % 256, (x + y) % 256)) for y in range(300) for x in range(400)))
    write_png(tmp_path / "flat.png", 64, 64, b"\x20\x40\x80" * 64 * 64)                 # few colours -> pngquant goes 1-bit
    write_png(tmp_path / "logo.png", 200, 100, b"\xff\xff\xff\x80" * 200 * 100, color_type=6)
    r = livearea.make([], tmp_path / "sce_sys", icon=str(tmp_path / "flat.png"), pic=str(tmp_path / "art.png"),
                      bg=str(tmp_path / "art.png"), startup=str(tmp_path / "logo.png"))
    c = livearea.check(tmp_path / "sce_sys")
    assert c["ok"], c["fails"]
    assert c["files"]["pic0.png"]["palette_entries"] == 256 and not c["files"]["pic0.png"]["has_trns"]
    assert c["files"]["icon0.png"]["bit_depth"] == 8
    assert r["scale"] == "lanczos"
    out = vita("livearea", "check", str(tmp_path / "sce_sys"), "--json")
    assert out.returncode == 0 and json.loads(out.stdout)["ok"]


def test_cli_check_exit_codes(tmp_path):
    s = good_sce_sys(tmp_path)
    assert vita("livearea", "check", str(s)).returncode == 0
    (s / "icon0.png").unlink()
    r = vita("livearea", "check", str(s))
    assert r.returncode == 1 and "icon0.png: missing" in r.stdout


# --------------------------------------------------------------------------- vpk

def test_sfo_roundtrip():
    vals = {"TITLE_ID": "ABCD00001", "TITLE": "Some Game", "APP_VER": "01.00", "ATTRIBUTE2": 12}
    assert sfo.parse(sfo.build(vals)) == vals


def test_vpk_good(tmp_path):
    p = make_vpk(tmp_path / "g.vpk", tmp_path, extra={"assets/a.tga": b"x" * 10})
    r = vpk.check(p, {"app": {"title_id": "TEST00001", "assets": "embedded", "unsafe": False, "version": "01.00", "name": "Test"}})
    assert r["ok"], r["fails"]
    assert r["eboot"]["mode"] == "safe" and r["eboot"]["elf_machine"] == "ARM" and r["param_sfo"]["TITLE_ID"] == "TEST00001"


def test_vpk_problems(tmp_path):
    p = make_vpk(tmp_path / "b.vpk", tmp_path, title_id="PCSE00001", unsafe=True, extra={"assets/a.tga": b"x"})
    r = vpk.check(p, {"app": {"title_id": "TEST00001", "assets": "external", "unsafe": False}})
    f = " | ".join(r["fails"])
    assert not r["ok"]
    assert "reserved prefix PCSE" in f and "differs from vita.toml title_id" in f
    assert "unsafe" in f and "external but the .vpk contains" in f
    p2 = make_vpk(tmp_path / "c.vpk", tmp_path, title_id="abc", version="1.0", skip=("eboot.bin",))
    f2 = " | ".join(vpk.check(p2, {"app": {"assets": "embedded"}})["fails"])
    assert "eboot.bin: missing" in f2 and "4 uppercase letters" in f2 and "##.##" in f2 and "nothing under assets/" in f2


def test_vpk_livearea_inside_and_not_a_zip(tmp_path):
    p = make_vpk(tmp_path / "l.vpk", tmp_path)
    bad = tmp_path / "bad.vpk"      # the same package with a gray+alpha icon0
    with zipfile.ZipFile(p) as zin, zipfile.ZipFile(bad, "w") as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "sce_sys/icon0.png":
                tmp = tmp_path / "ya8.png"
                write_png(tmp, 128, 128, b"\x80\xff" * 128 * 128, color_type=4)
                data = tmp.read_bytes()
            zout.writestr(n, data)
    r = vpk.check(bad, {})
    assert any("LiveArea: icon0.png: grayscale+alpha" in f for f in r["fails"])
    (tmp_path / "not.vpk").write_bytes(b"hello")
    assert not vpk.check(tmp_path / "not.vpk", {})["ok"]


def test_vpk_cli_flags(tmp_path):
    p = make_vpk(tmp_path / "e.vpk", tmp_path)
    assert vita("vpk", "check", str(p), "--assets", "external", "--title-id", "TEST00001", "--safe", cwd=tmp_path).returncode == 0
    r = vita("vpk", "check", str(p), "--assets", "external", "--unsafe", cwd=tmp_path)
    assert r.returncode == 1 and "eboot.bin is safe" in r.stdout
    j = json.loads(vita("vpk", "check", str(p), "--json", cwd=tmp_path).stdout)
    assert j["ok"] and any("assets mode unknown" in w for w in j["warnings"])
