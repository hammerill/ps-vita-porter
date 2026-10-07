"""Check a .vpk before anyone installs it: structure, eboot.bin, param.sfo, title ID, unsafe flag, LiveArea files,
size, and whether game assets are inside it or not, against the assets mode.

    vita vpk check build-vita/game.vpk                  # compares with vita.toml ([app] and [assets])
    vita vpk check game.vpk --assets external           # no vita.toml: say what to expect
    vita vpk check game.vpk --title-id ABCD00001 --safe --json

FAIL  missing eboot.bin / sce_sys/param.sfo / LiveArea files; eboot.bin that isn't a SELF for ARM; a title ID
      that isn't 4 uppercase letters + 5 digits, uses a reserved prefix, or differs from vita.toml; APP_VER not
      ##.##; the unsafe flag differs from vita.toml (eboot authid 0x2F00000000000001 = unsafe, ...02 = safe);
      LiveArea images that `vita livearea check` rejects; embedded mode without the asset folder, or external
      mode with game files inside the .vpk; a .vpk over 4 GiB
WARN  display name differs from vita.toml; ATTRIBUTE2 vs [app] extended_memory; a .vpk over 1 GiB
"""
from __future__ import annotations

import fnmatch
import struct
import tempfile
import zipfile
from pathlib import Path

from vita_porter import livearea, sfo
from vita_porter.common import OK, PROBLEM, emit_json, find_project, human, load_config, title_id_problems, usage

AUTHID = {0x2F00000000000001: "unsafe", 0x2F00000000000002: "safe", 0x2F00000000000003: "secret-safe"}
REQUIRED = ["eboot.bin", "sce_sys/param.sfo", "sce_sys/icon0.png", "sce_sys/pic0.png", "sce_sys/livearea/contents/bg0.png",
            "sce_sys/livearea/contents/startup.png", "sce_sys/livearea/contents/template.xml"]
GAME_EXT = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".dds", ".ktx", ".gxt", ".wav", ".ogg", ".mp3", ".flac", ".opus", ".at9",
            ".pak", ".pck", ".dat", ".bin", ".wad", ".mp4", ".bik", ".ttf", ".otf", ".fnt", ".json", ".xml", ".lua", ".txt",
            ".map", ".lvl", ".obj", ".fbx", ".gltf", ".glb", ".mdl", ".xnb", ".assets"}


def eboot_info(data: bytes) -> dict:
    if data[:4] != b"SCE\0":
        return dict(ok=False, error="eboot.bin is not a SELF (no SCE\\0 magic)")
    info: dict = dict(ok=True, size=len(data))
    try:
        appinfo = struct.unpack("<Q", data[0x38:0x40])[0]
        elf_off = struct.unpack("<Q", data[0x40:0x48])[0]
        authid = struct.unpack("<Q", data[appinfo:appinfo + 8])[0]
        info["authid"] = f"0x{authid:016X}"
        info["mode"] = AUTHID.get(authid, "custom authid")
        if data[elf_off:elf_off + 4] == b"\x7fELF":
            machine = struct.unpack("<H", data[elf_off + 18:elf_off + 20])[0]
            info["elf_machine"] = "ARM" if machine == 0x28 else f"0x{machine:x}"
            if machine != 0x28:
                info.update(ok=False, error=f"embedded ELF is for machine {info['elf_machine']}, not ARM")
        else:
            info["elf_machine"] = "compressed or unknown"
    except struct.error:
        info.update(ok=False, error="eboot.bin header is truncated")
    return info


def check(path: Path, cfg: dict | None = None, title_id: str | None = None, assets: str | None = None, unsafe: bool | None = None) -> dict:
    cfg = cfg or {}
    app, acfg = cfg.get("app", {}), cfg.get("assets", {})
    title_id = title_id or app.get("title_id") or None
    assets = assets or app.get("assets") or None
    if unsafe is None and "unsafe" in app:
        unsafe = bool(app["unsafe"])
    vpk_dir = (acfg.get("vpk_dir") or "assets").strip("/")
    allow = list(cfg.get("vpk", {}).get("allow", []))
    fails, warns = [], []
    res: dict = dict(vpk=str(path), ok=False)
    if not path.is_file():
        usage(f"no such file: {path}")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        res.update(fails=["not a zip archive (a .vpk is a zip)"], warnings=[])
        return res
    with z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        size_unpacked = sum(i.file_size for i in z.infolist())
        res.update(files=len(names), size=path.stat().st_size, size_unpacked=size_unpacked)
        lower = {n.lower(): n for n in names}
        for r in REQUIRED:
            if r not in names:
                alt = lower.get(r.lower())
                fails.append(f"{r}: missing" + (f" (found {alt}: names are case-sensitive in the package)" if alt else ""))
        if "eboot.bin" in names:
            e = eboot_info(z.read("eboot.bin"))
            res["eboot"] = e
            if not e["ok"]:
                fails.append(e["error"])
            elif unsafe is not None and e.get("mode") in ("safe", "unsafe"):
                want = "unsafe" if unsafe else "safe"
                if e["mode"] != want:
                    fails.append(f"eboot.bin is {e['mode']} ({e['authid']}) but vita.toml says unsafe = {str(unsafe).lower()}")
        if "sce_sys/param.sfo" in names:
            try:
                s = sfo.parse(z.read("sce_sys/param.sfo"))
            except (ValueError, struct.error) as ex:
                s = {}
                fails.append(f"param.sfo: {ex}")
            res["param_sfo"] = s
            tid = s.get("TITLE_ID", "")
            if not tid:
                fails.append("param.sfo has no TITLE_ID")
            else:
                fails += [f"param.sfo: {p}" for p in title_id_problems(tid)]
                if title_id and tid != title_id:
                    fails.append(f"param.sfo TITLE_ID {tid} differs from vita.toml title_id {title_id}")
            ver = str(s.get("APP_VER", ""))
            if ver and not (len(ver) == 5 and ver[2] == "." and ver.replace(".", "").isdigit()):
                fails.append(f"param.sfo APP_VER {ver!r} must be ##.##")
            if app.get("version") and ver and ver != app["version"]:
                warns.append(f"param.sfo APP_VER {ver} differs from vita.toml version {app['version']}")
            if app.get("name") and s.get("TITLE") and s["TITLE"] != app["name"]:
                warns.append(f"param.sfo TITLE {s['TITLE']!r} differs from vita.toml name {app['name']!r}")
            ext = s.get("ATTRIBUTE2", 0) == 12
            if "extended_memory" in app and bool(app["extended_memory"]) != ext:
                warns.append(f"param.sfo ATTRIBUTE2={s.get('ATTRIBUTE2', 0)} but vita.toml extended_memory = {str(bool(app['extended_memory'])).lower()}")
        # LiveArea images: run the same checks as `vita livearea check`
        sce = [n for n in names if n.startswith("sce_sys/")]
        if sce:
            with tempfile.TemporaryDirectory(prefix="vita-vpk-") as td:
                for n in sce:
                    dst = Path(td) / n
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(z.read(n))
                la = livearea.check(Path(td) / "sce_sys")
            res["livearea"] = dict(ok=la["ok"], fails=la["fails"])
            fails += [f"LiveArea: {f}" for f in la["fails"] if "missing" not in f]
        # assets vs the assets mode
        payload = [n for n in names if n != "eboot.bin" and not n.startswith("sce_sys/") and not any(fnmatch.fnmatch(n, g) for g in allow)]
        res["payload_files"] = len(payload)
        if assets == "embedded":
            inside = [n for n in payload if n.startswith(vpk_dir + "/")]
            if not inside:
                fails.append(f"assets mode is embedded but the .vpk has nothing under {vpk_dir}/ (did `vita assets convert` run before the build?)")
        elif assets == "external":
            game = [n for n in payload if Path(n).suffix.lower() in GAME_EXT or n.startswith(vpk_dir + "/")]
            if game:
                fails.append(f"assets mode is external but the .vpk contains {len(game)} game file(s), e.g. {', '.join(game[:3])}")
        elif assets:
            fails.append(f"unknown assets mode {assets!r} (embedded or external)")
        else:
            warns.append("assets mode unknown (no vita.toml, no --assets): presence of game files not checked")
    if res["size"] > 4 << 30:
        fails.append(f".vpk is {human(res['size'])}: over 4 GiB, which installers and FAT32-formatted storage can't handle")
    elif res["size"] > 1 << 30:
        warns.append(f".vpk is {human(res['size'])}: consider external assets")
    res.update(ok=not fails, fails=fails, warnings=warns, title_id=title_id, assets_mode=assets, unsafe_expected=unsafe)
    return res


def main(a):
    root = find_project()
    cfg = load_config(root) if root else {}
    unsafe = True if a.unsafe else False if a.safe else None
    r = check(Path(a.vpk), cfg, a.title_id, a.assets, unsafe)
    if a.json:
        emit_json(r)
        return OK if r["ok"] else PROBLEM
    s = r.get("param_sfo", {})
    e = r.get("eboot", {})
    print(f"{r['vpk']}: {human(r.get('size', 0))} ({r.get('files', 0)} files, {human(r.get('size_unpacked', 0))} unpacked)")
    if s:
        print(f"  TITLE_ID {s.get('TITLE_ID')}  TITLE {s.get('TITLE')!r}  APP_VER {s.get('APP_VER')}  ATTRIBUTE2 {s.get('ATTRIBUTE2', 0)}")
    if e.get("ok"):
        print(f"  eboot.bin {human(e['size'])}, {e.get('mode')} ({e.get('authid')}), ELF {e.get('elf_machine')}")
    print(f"  payload besides eboot.bin and sce_sys/: {r.get('payload_files', 0)} file(s); assets mode: {r.get('assets_mode') or 'unknown'}")
    for f in r["fails"]:
        print("FAIL", f)
    for w in r["warnings"]:
        print("WARN", w)
    print("PASS" if r["ok"] else "FAIL")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("vpk", help="check a .vpk: structure, param.sfo, title ID, unsafe flag, LiveArea, assets mode",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="validate a .vpk", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("vpk")
    q.add_argument("--title-id", help="expected title ID (default: vita.toml)")
    q.add_argument("--assets", choices=["embedded", "external"], help="expected assets mode (default: vita.toml)")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--unsafe", action="store_true", help="expect an unsafe eboot.bin")
    g.add_argument("--safe", action="store_true", help="expect a safe eboot.bin")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
