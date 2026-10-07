"""Make and check the LiveArea files in sce_sys/ (what the Vita shows for the app's bubble and gate).

    vita livearea make data/title.png                          # one image for everything
    vita livearea make --icon art/icon.png --pic art/key.png --bg art/key.png --startup art/logo.png
    vita livearea make data/title.png data/logo.png --pixel-art # nearest-neighbour scaling for pixel art
    vita livearea make art/key.png --style psmobile --out sce_sys
    vita livearea check                                        # sce_sys/ of this repo (or [livearea] dir in vita.toml)
    vita livearea check build-vita/sce_sys --json

Layout (the spec in hammerill's "LiveArea Specs" gist, with its colour bug fixed):
    sce_sys/icon0.png                      128x128, no alpha, indexed (pngquant)
    sce_sys/pic0.png                       960x544, no alpha, indexed, exactly 256-colour palette (ffmpeg palettegen)
    sce_sys/livearea/contents/bg0.png      840x500, no alpha, indexed (pngquant)
    sce_sys/livearea/contents/startup.png  280x158, alpha allowed (the only one), indexed (pngquant)
    sce_sys/livearea/contents/template.xml style a1 (startup image centred) or psmobile (on the right)

Pipeline: ffmpeg scales with lanczos (neighbor for --pixel-art) to `-pix_fmt rgb24` (rgba for startup), then
pngquant; pic0 gets palettegen + paletteuse instead (never pngquant). The gist's `-pix_fmt ya8` is grayscale +
alpha and turns every image gray: never use it. pngquant writes 1/2/4-bit PNGs for images with few colours;
`make` re-expands them to 8 bits. Wrong sizes, 16-bit channels, missing palettes or alpha where it isn't allowed
are what makes the Vita refuse the install with error 0x8010113D: `check` rejects all of them.

Positional sources are assigned in order: icon0, pic0, bg0, startup. Missing ones reuse pic0 (bg0) and icon0
(startup); one image is used for all four. Sources are cropped to fill (--fit cover, default) or padded
(--fit pad). In a universal-decompiler repo, pick the sources from the game's own title screen, logo or key art
in data/: the result then contains game art, so it stays local like the rest of data/.

CMake: vita_create_vpk(... FILE sce_sys sce_sys). The destination name sce_sys is fixed.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from vita_porter.common import OK, PROBLEM, TEXT, emit_json, find_project, load_config, rel, usage
from vita_porter.images import expand_indexed_to_8bit, png_info

SPEC = {
    "icon0.png": dict(size=(128, 128), alpha=False, palette=None),
    "pic0.png": dict(size=(960, 544), alpha=False, palette=256),
    "livearea/contents/bg0.png": dict(size=(840, 500), alpha=False, palette=None),
    "livearea/contents/startup.png": dict(size=(280, 158), alpha=True, palette=None),
}
STYLES = ("a1", "psmobile")
TEMPLATE = """<?xml version="1.0" encoding="utf-8"?>
<livearea style="{style}" format-ver="01.00" content-rev="1">
    <livearea-background><image>bg0.png</image></livearea-background>
    <gate><startup-image>startup.png</startup-image></gate>
</livearea>
"""


def ffmpeg(args: list[str]):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"ffmpeg failed: {(r.stderr or r.stdout).strip()[-600:]}")


def scale_filter(w: int, h: int, flags: str, fit: str, alpha: bool) -> str:
    if fit == "pad":
        color = "black@0" if alpha else "black"
        return (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags={flags},"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={color}")
    if fit == "stretch":
        return f"scale={w}:{h}:flags={flags}"
    return f"scale={w}:{h}:force_original_aspect_ratio=increase:flags={flags},crop={w}:{h}"


def make_one(src: Path, dst: Path, name: str, flags: str, fit: str, tmp: Path):
    spec = SPEC[name]
    w, h = spec["size"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    t = tmp / (Path(name).stem + "-scaled.png")
    if name == "pic0.png":
        ffmpeg(["-i", str(src), "-vf", scale_filter(w, h, flags, fit, False), "-frames:v", "1", "-pix_fmt", "rgb24", str(t)])
        # exactly 256 colours, no transparent entry (palettegen reserves one by default -> tRNS)
        ffmpeg(["-i", str(t), "-vf", "split[a][b];[a]palettegen=max_colors=256:reserve_transparent=0[p];[b][p]paletteuse",
                "-frames:v", "1", str(dst)])
        return
    fmt = "rgba" if spec["alpha"] else "rgb24"
    ffmpeg(["-i", str(src), "-vf", scale_filter(w, h, flags, fit, spec["alpha"]), "-frames:v", "1", "-pix_fmt", fmt, str(t)])
    r = subprocess.run(["pngquant", "--force", "--output", str(dst), "--", str(t)], capture_output=True, text=True)
    if r.returncode not in (0, 99):
        raise RuntimeError(f"pngquant failed (exit {r.returncode}): {(r.stderr or r.stdout).strip()[-400:]}")
    if r.returncode == 99 or not dst.exists():     # quality limit: shouldn't happen without --quality; keep the quantised copy
        raise RuntimeError("pngquant could not meet its quality target")
    expand_indexed_to_8bit(dst)


def make(sources: list[str], out: Path, icon=None, pic=None, bg=None, startup=None, pixel_art=False, fit="cover", style="a1") -> dict:
    if style not in STYLES:
        usage(f"style must be one of {', '.join(STYLES)}")
    for tool in ("ffmpeg", "pngquant"):
        if not shutil.which(tool):
            usage(f"{tool} is not on PATH (see `vita tools check`)")
    pos = list(sources)
    pick = {
        "icon0.png": icon or (pos[0] if pos else None),
        "pic0.png": pic or (pos[1] if len(pos) > 1 else pos[0] if pos else None),
    }
    pick["livearea/contents/bg0.png"] = bg or (pos[2] if len(pos) > 2 else pick["pic0.png"])
    pick["livearea/contents/startup.png"] = startup or (pos[3] if len(pos) > 3 else pick["icon0.png"])
    missing = [k for k, v in pick.items() if not v]
    if missing:
        usage("give at least one source image (or --icon/--pic/--bg/--startup)")
    for v in pick.values():
        if not Path(v).is_file():
            usage(f"no such image: {v}")
    flags = "neighbor" if pixel_art else "lanczos"
    made = {}
    with tempfile.TemporaryDirectory(prefix="vita-livearea-") as td:
        for name, src in pick.items():
            make_one(Path(src), out / name, name, flags, fit, Path(td))
            made[name] = str(src)
    xml = out / "livearea" / "contents" / "template.xml"
    xml.write_text(TEMPLATE.format(style=style), **TEXT)
    made["livearea/contents/template.xml"] = f"style {style}"
    return dict(out=str(out), sources=made, scale=flags, fit=fit)


def check(path: Path) -> dict:
    fails, warns, files = [], [], {}
    if not path.is_dir():
        return dict(path=str(path), ok=False, fails=[f"{path} is not a folder (expected sce_sys/)"], warnings=[], files={})
    for name, spec in SPEC.items():
        p = path / name
        if not p.exists():
            fails.append(f"{name}: missing")
            continue
        try:
            i = png_info(p)
        except ValueError as e:
            fails.append(f"{name}: {e}")
            continue
        files[name] = {k: i[k] for k in ("width", "height", "bit_depth", "color", "palette_entries", "has_trns", "size")}
        w, h = spec["size"]
        if (i["width"], i["height"]) != (w, h):
            fails.append(f"{name}: {i['width']}x{i['height']}, must be exactly {w}x{h}")
        if i["bit_depth"] != 8:
            fails.append(f"{name}: {i['bit_depth']} bits per channel, must be 8"
                         + (" (pngquant wrote a low bit depth: re-run `vita livearea make`)" if i["bit_depth"] < 8 else ""))
        if i["color_type"] == 4:
            fails.append(f"{name}: grayscale+alpha (the gist's `-pix_fmt ya8` bug: turns images gray); use rgb24/rgba then quantise")
        elif i["color_type"] == 0:
            fails.append(f"{name}: grayscale; must be an indexed colour image")
        elif i["color_type"] != 3:
            fails.append(f"{name}: {i['color']}, must be indexed (palette)")
        if i["alpha"] and not spec["alpha"]:
            fails.append(f"{name}: has alpha/transparency ({'tRNS chunk' if i['has_trns'] else i['color']}); only startup.png may")
        if spec["palette"] and i["color_type"] == 3 and i["palette_entries"] != spec["palette"]:
            fails.append(f"{name}: palette has {i['palette_entries']} colours, must have exactly {spec['palette']}")
        if i.get("interlaced"):
            warns.append(f"{name}: interlaced PNG; re-encode without interlacing")
    xml = path / "livearea" / "contents" / "template.xml"
    if not xml.exists():
        fails.append("livearea/contents/template.xml: missing")
    else:
        try:
            root = ET.parse(xml).getroot()
            if root.tag != "livearea":
                fails.append(f"template.xml: root element is <{root.tag}>, must be <livearea>")
            style = root.get("style")
            if style not in STYLES:
                fails.append(f"template.xml: style {style!r}, must be one of {', '.join(STYLES)}")
            if root.get("format-ver") != "01.00":
                warns.append(f"template.xml: format-ver {root.get('format-ver')!r} (expected 01.00)")
            refs = [e.text.strip() for e in root.iter() if e.tag in ("image", "startup-image") and e.text]
            if not refs:
                fails.append("template.xml: references no image")
            for r in refs:
                if not (xml.parent / r).exists():
                    fails.append(f"template.xml references {r}, which doesn't exist in livearea/contents/")
            files["livearea/contents/template.xml"] = dict(style=style, images=refs)
        except ET.ParseError as e:
            fails.append(f"template.xml: not valid XML ({e})")
    return dict(path=str(path), ok=not fails, fails=fails, warnings=warns, files=files)


def default_dir(root: Path | None) -> Path:
    if root is None:
        return Path("sce_sys")
    cfg = load_config(root).get("livearea", {})
    return root / cfg.get("dir", "sce_sys")


def main(a):
    root = find_project()
    if a.cmd == "make":
        out = Path(a.out) if a.out else default_dir(root)
        try:
            r = make(a.sources, out, a.icon, a.pic, a.bg, a.startup, a.pixel_art, a.fit, a.style)
        except RuntimeError as e:
            r = dict(ok=False, error=str(e))
            if a.json:
                emit_json(r)
            else:
                print(f"FAILED: {e}")
            return PROBLEM
        c = check(out)
        r.update(ok=c["ok"], check=c)
        if a.json:
            emit_json(r)
        else:
            for name, src in r["sources"].items():
                print(f"  {name:32} <- {src}")
            print(f"wrote {rel(root, out) if root else out}/ (scale {r['scale']}, fit {r['fit']}); check: {'PASS' if c['ok'] else 'FAIL'}")
            for f in c["fails"]:
                print("  FAIL", f)
        return OK if c["ok"] else PROBLEM
    path = Path(a.path) if a.path else default_dir(root)
    r = check(path)
    if a.json:
        emit_json(r)
    else:
        for name, i in r["files"].items():
            if "width" in i:
                print(f"  {name:32} {i['width']}x{i['height']} {i['bit_depth']}-bit {i['color']}"
                      + (f", {i['palette_entries']} colours" if i["palette_entries"] else "") + (", tRNS" if i["has_trns"] else ""))
        for f in r["fails"]:
            print("FAIL", f)
        for w in r["warnings"]:
            print("WARN", w)
        print(f"{'PASS' if r['ok'] else 'FAIL'}: {r['path']}" + ("" if r["ok"] else "  (these would fail the install with 0x8010113D)"))
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("livearea", help="make and check sce_sys/ (icon0, pic0, bg0, startup, template.xml)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("make", help="build sce_sys/ from source images", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("sources", nargs="*", help="images in the order icon0, pic0, bg0, startup (fewer is fine)")
    q.add_argument("--icon")
    q.add_argument("--pic")
    q.add_argument("--bg")
    q.add_argument("--startup")
    q.add_argument("--pixel-art", action="store_true", help="scale with nearest neighbour (pixel-art sources)")
    q.add_argument("--fit", choices=["cover", "pad", "stretch"], default="cover", help="crop to fill (default), pad, or stretch")
    q.add_argument("--style", choices=list(STYLES), default="a1", help="a1: startup image centred; psmobile: on the right")
    q.add_argument("--out", help="output folder (default: sce_sys, or [livearea] dir in vita.toml)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("check", help="validate every LiveArea image and template.xml", description=__doc__,
                      formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("path", nargs="?", help="the sce_sys folder (default: sce_sys, or [livearea] dir in vita.toml)")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
