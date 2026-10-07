"""Convert the game's assets for the Vita per PORT_PLAN.md, into build-vita/assets, and check the result.
`vita build` then embeds that folder in the .vpk (assets = "embedded"), or the user copies it to
ux0:data/<data_folder>/<vpk_dir>/ on the console (assets = "external").

    vita assets convert                # every file under [assets] source, first matching rule wins
    vita assets convert --force        # redo everything (otherwise up-to-date outputs are kept)
    vita assets convert --dry-run --json
    vita assets check                  # missing, stale or oversized outputs; memory estimate vs the budget

Rules in vita.toml (first match wins; globs are relative to [assets] source, `**/` matches any depth):
    [[assets.rule]]
    glob = "textures/**/*.png"
    action = "texture"          # texture | audio | copy | skip
    max_size = 1024             # longest side in pixels (downscale only)
    scale = 0.5                 # optional factor applied before max_size
    filter = "lanczos"          # lanczos | neighbor (pixel art)
    format = "dds-dxt5"         # keep | png | tga | dds-dxt1 | dds-dxt5 | command
    command = ""                # format = "command": e.g. "etcpak --etc1 {in} {out}" (ETC1/PVRTC via external tools)
    out_ext = ""                # with format = "command": the output extension, e.g. ".pvr"

    [[assets.rule]]
    glob = "**/*.wav"
    action = "audio"
    format = "ogg"              # keep | wav | ogg
    rate = 22050                # Hz (optional)
    channels = 1                # optional
    quality = 4                 # ogg vorbis quality (optional)

Textures: the Vita samples DXT1/DXT5 (S3TC/UBC), PVRTC and ETC1 natively; vita encodes DXT1/DXT5 itself (dds-*),
ETC1 and PVRTC go through an external encoder (`format = "command"`). Keep pixel art, UI and text uncompressed
(png/tga + filter = "neighbor"). The GPU's maximum texture size is 4096x4096.
Exit code 1 (check) when outputs are missing, stale or oversized, or the estimate exceeds the budget.
"""
from __future__ import annotations

import fnmatch
import shlex
import shutil
import subprocess
import time
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, human, load_config, rel, project_root, usage
from vita_porter.images import sniff
from vita_porter.texture import dds, decode_rgba, encode

MAX_TEXTURE = 4096
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".gif", ".webp", ".dds", ".ktx"}
AUDIO_EXT = {".wav", ".ogg", ".mp3", ".flac", ".opus", ".aiff", ".aif"}
# A rough RAM+VRAM budget for game assets resident at once (see skills/port-to-vita/references/memory.md):
# the default newlib heap is 128 MiB, vitaGL keeps textures in its own pools; keep resident assets well under this.
DEFAULT_BUDGET_MB = 160


def match(rel_path: str, glob: str) -> bool:
    if fnmatch.fnmatch(rel_path, glob):
        return True
    if glob.startswith("**/") and fnmatch.fnmatch(rel_path, glob[3:]):
        return True
    return False


def rule_for(rel_path: str, rules: list[dict]) -> dict:
    for r in rules:
        if match(rel_path, r.get("glob", "**/*")):
            return r
    ext = Path(rel_path).suffix.lower()
    return {"action": "copy"} if ext not in IMAGE_EXT | AUDIO_EXT else {"action": "copy", "_default": True}


def out_name(rel_path: str, rule: dict) -> str:
    p = Path(rel_path)
    act, fmt = rule.get("action", "copy"), rule.get("format", "keep")
    if act == "texture":
        if fmt in ("png", "tga"):
            return p.with_suffix("." + fmt).as_posix()
        if fmt.startswith("dds-"):
            return p.with_suffix(".dds").as_posix()
        if fmt == "command":
            return p.with_suffix(rule.get("out_ext") or p.suffix).as_posix()
    if act == "audio" and fmt in ("wav", "ogg"):
        return p.with_suffix("." + fmt).as_posix()
    return p.as_posix()


def target_size(w: int, h: int, rule: dict) -> tuple[int, int]:
    s = float(rule.get("scale", 1.0))
    w, h = max(1, round(w * s)), max(1, round(h * s))
    m = int(rule.get("max_size", 0) or 0)
    if m and max(w, h) > m:
        f = m / max(w, h)
        w, h = max(1, round(w * f)), max(1, round(h * f))
    return w, h


def ffmpeg(args: list[str]):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[-400:])


def mem_estimate(w: int, h: int, fmt: str) -> int:
    if fmt == "dds-dxt1":
        return max(4, w) * max(4, h) // 2
    if fmt == "dds-dxt5":
        return max(4, w) * max(4, h)
    return w * h * 4


def convert_one(src: Path, dst: Path, rule: dict) -> dict:
    act, fmt = rule.get("action", "copy"), rule.get("format", "keep")
    dst.parent.mkdir(parents=True, exist_ok=True)
    info: dict = dict(action=act, format=fmt)
    if act == "texture":
        s = sniff(src) or {}
        w, h = s.get("width"), s.get("height")
        if not w or not h:
            raise RuntimeError("can't read the image size")
        tw, th = target_size(w, h, rule)
        flt = "neighbor" if rule.get("filter") == "neighbor" else "lanczos"
        info.update(src_size=[w, h], size=[tw, th], memory=mem_estimate(tw, th, fmt))
        if fmt == "keep" and (tw, th) == (w, h):
            shutil.copyfile(src, dst)
        elif fmt in ("keep", "png", "tga"):
            ffmpeg(["-i", str(src), "-vf", f"scale={tw}:{th}:flags={flt}", "-frames:v", "1", "-pix_fmt", "rgba", str(dst)])
        elif fmt in ("dds-dxt1", "dds-dxt5"):
            px = decode_rgba(src, tw, th, f"scale={tw}:{th}:flags={flt}")
            kind = fmt[4:]
            dst.write_bytes(dds(tw, th, kind, encode(px, tw, th, kind)))
        elif fmt == "command":
            cmd = rule.get("command") or ""
            if "{in}" not in cmd or "{out}" not in cmd:
                raise RuntimeError('format = "command" needs command = "... {in} ... {out}"')
            tmp = src
            if (tw, th) != (w, h):
                tmp = dst.with_name(dst.stem + ".scaled.png")
                ffmpeg(["-i", str(src), "-vf", f"scale={tw}:{th}:flags={flt}", "-frames:v", "1", str(tmp)])
            argv = [a.replace("{in}", str(tmp)).replace("{out}", str(dst)) for a in shlex.split(cmd)]
            r = subprocess.run(argv, capture_output=True, text=True)
            if tmp != src:
                tmp.unlink(missing_ok=True)
            if r.returncode or not dst.exists():
                raise RuntimeError(f"{argv[0]} failed: {(r.stderr or r.stdout).strip()[-300:]}")
        else:
            raise RuntimeError(f"unknown texture format {fmt!r}")
    elif act == "audio":
        if fmt == "keep" and not rule.get("rate") and not rule.get("channels"):
            shutil.copyfile(src, dst)
        else:
            args = ["-i", str(src), "-vn"]
            if rule.get("rate"):
                args += ["-ar", str(int(rule["rate"]))]
            if rule.get("channels"):
                args += ["-ac", str(int(rule["channels"]))]
            if fmt == "ogg":
                args += ["-c:a", "libvorbis", "-q:a", str(rule.get("quality", 4))]
            elif fmt == "wav":
                args += ["-c:a", "pcm_s16le"]
            ffmpeg([*args, str(dst)])
    elif act == "copy":
        shutil.copyfile(src, dst)
    else:
        raise RuntimeError(f"unknown action {act!r}")
    info["bytes"] = dst.stat().st_size
    return info


def plan(root: Path, cfg: dict) -> tuple[Path, Path, list[tuple[str, dict, str]]]:
    a = cfg.get("assets", {})
    src = root / (a.get("source") or "data")
    out = root / (a.get("out") or "build-vita/assets")
    rules = list(a.get("rule", []))
    items = []
    if src.is_dir():
        for p in sorted(src.rglob("*")):
            if p.is_file():
                r = p.relative_to(src).as_posix()
                rule = rule_for(r, rules)
                if rule.get("action") != "skip":
                    items.append((r, rule, out_name(r, rule)))
    return src, out, items


def convert(root: Path, force: bool = False, dry_run: bool = False) -> dict:
    cfg = load_config(root)
    src, out, items = plan(root, cfg)
    if not src.is_dir():
        usage(f"[assets] source {rel(root, src)} doesn't exist (vita.toml)")
    if not dry_run and any(r.get("action") in ("texture", "audio") for _, r, _ in items) and not shutil.which("ffmpeg"):
        usage("ffmpeg is not on PATH (see `vita tools check`)")
    done, kept, failed, defaulted = [], 0, [], 0
    t0 = time.time()
    for r, rule, o in items:
        s, d = src / r, out / o
        defaulted += bool(rule.get("_default"))
        if dry_run:
            done.append(dict(src=r, out=o, action=rule.get("action"), format=rule.get("format", "keep")))
            continue
        if not force and d.exists() and d.stat().st_mtime >= s.stat().st_mtime:
            kept += 1
            continue
        try:
            info = convert_one(s, d, rule)
            done.append(dict(src=r, out=o, **info))
        except (RuntimeError, OSError) as e:
            failed.append(dict(src=r, error=str(e)))
    res = dict(ok=not failed, source=rel(root, src), out=rel(root, out), files=len(items), converted=len(done), kept=kept, failed=failed,
               items=done[:200], seconds=round(time.time() - t0, 1), dry_run=dry_run)
    if defaulted:
        res["note"] = f"{defaulted} image/audio file(s) matched no rule and were copied unchanged: add [[assets.rule]] entries from PORT_PLAN.md"
    return res


def check(root: Path) -> dict:
    cfg = load_config(root)
    src, out, items = plan(root, cfg)
    app = cfg.get("app", {})
    budget = int(cfg.get("assets", {}).get("budget_mb", DEFAULT_BUDGET_MB)) << 20
    missing, stale, oversized, problems = [], [], [], []
    total, mem = 0, 0
    if not src.is_dir():
        problems.append(f"[assets] source {rel(root, src)} doesn't exist")
    for r, rule, o in items:
        s, d = src / r, out / o
        if not d.exists():
            missing.append(o)
            continue
        if d.stat().st_mtime < s.stat().st_mtime:
            stale.append(o)
        total += d.stat().st_size
        ext = d.suffix.lower()
        if ext in IMAGE_EXT:
            i = sniff(d) or {}
            w, h = i.get("width") or 0, i.get("height") or 0
            if w and h:
                fmt = rule.get("format", "keep") if ext == ".dds" else "rgba"
                mem += mem_estimate(w, h, fmt)
                limit = int(rule.get("max_size", 0) or 0) or MAX_TEXTURE
                if max(w, h) > min(limit, MAX_TEXTURE):
                    oversized.append(f"{o}: {w}x{h} (limit {min(limit, MAX_TEXTURE)})")
        elif d.stat().st_size > 64 << 20:
            oversized.append(f"{o}: {human(d.stat().st_size)} in one file (stream it or split it)")
    if mem > budget:
        problems.append(f"textures decoded all at once would take {human(mem)}, over the {human(budget)} budget: "
                        "downscale, compress, or stream (PORT_PLAN.md)")
    mode = app.get("assets", "embedded")
    where = (f"embedded in the .vpk under {cfg.get('assets', {}).get('vpk_dir', 'assets')}/ (app0:)" if mode == "embedded" else
             f"copy {rel(root, out)}/ to ux0:data/{app.get('data_folder', '<data_folder>')}/{cfg.get('assets', {}).get('vpk_dir', 'assets')}/ on the Vita")
    ok = not (missing or stale or oversized or problems)
    return dict(ok=ok, source=rel(root, src), out=rel(root, out), files=len(items), missing=missing, stale=stale, oversized=oversized,
                problems=problems, total_bytes=total, texture_memory_estimate=mem, budget=budget, mode=mode, destination=where)


def main(a):
    root = project_root()
    if a.cmd == "convert":
        r = convert(root, a.force, a.dry_run)
        if a.json:
            emit_json(r)
        else:
            for it in r["items"][:40]:
                extra = f" {it['src_size'][0]}x{it['src_size'][1]} -> {it['size'][0]}x{it['size'][1]}" if it.get("size") else ""
                print(f"  {it['src']} -> {it['out']} [{it.get('action')}/{it.get('format', 'keep')}]{extra}")
            if len(r["items"]) > 40:
                print(f"  ... {len(r['items']) - 40} more")
            for f in r["failed"]:
                print(f"  FAILED {f['src']}: {f['error']}")
            print(f"{'planned' if r['dry_run'] else 'converted'} {r['converted']}, up to date {r['kept']}, failed {len(r['failed'])} "
                  f"of {r['files']} files: {r['source']} -> {r['out']} ({r['seconds']} s)")
            if r.get("note"):
                print(f"note: {r['note']}")
        return OK if r["ok"] else PROBLEM
    r = check(root)
    if a.json:
        emit_json(r)
    else:
        for k in ("missing", "stale", "oversized", "problems"):
            for x in r[k][:30]:
                print(f"{k.upper().rstrip('S') if k != 'problems' else 'PROBLEM'}: {x}")
        print(f"{'OK' if r['ok'] else 'PROBLEMS'}: {r['files']} files, {human(r['total_bytes'])} on disk, textures ~{human(r['texture_memory_estimate'])} "
              f"decoded (budget {human(r['budget'])}); {r['destination']}")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("assets", help="convert assets per the plan into build-vita/assets (textures, audio); check them",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("convert", help="convert per vita.toml [[assets.rule]]", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("--force", action="store_true", help="redo up-to-date outputs too")
    q.add_argument("--dry-run", action="store_true", help="only show what would happen")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("check", help="missing, stale or oversized outputs; memory estimate", description=__doc__,
                      formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
