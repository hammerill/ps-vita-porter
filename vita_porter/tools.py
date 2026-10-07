"""Check everything the port needs. Never installs anything: missing tools come with exact install steps for
Windows, Linux and macOS, which the agent hands to the user before stopping.

    vita tools check                 # VitaSDK (native) or Docker + vitasdk image, vdpm packages, vitaGL, CMake,
                                     # a PC compiler, ffmpeg, pngquant; Vita3K and the crash-dump parser as optional;
                                     # vitacompanion on the Vita only once [device] ip is set in vita.toml
    vita tools check --json
    vita tools check --mock-path /tmp/fakebin   # tests: look tools up in this PATH only
    vita tools list                  # every tool in the registry
    vita tools show vita3k           # one tool: what it's for, status, install steps

The registry is vita_porter/tools.toml. vdpm packages come from vita.toml [build] vdpm (vitaGL is always
checked). Vita3K missing is reported as optional: the loop continues without the emulator level.
Exit code 1 if a required tool or package is missing.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, find_project, load_config, os_key, usage

REGISTRY = Path(__file__).resolve().parent / "tools.toml"
ALWAYS_VDPM = ["vitaGL"]
VDPM_HINT = {"sdl2": "sdl2 (or sdl2_vitagl: SDL2 with the vitaGL video backend)", "sdl2_vitagl": "sdl2_vitagl (conflicts with sdl2)"}


@lru_cache(maxsize=1)
def registry() -> dict:
    return tomllib.loads(REGISTRY.read_text(encoding="utf-8"))


def _expand(p: str) -> str:
    out = re.sub(r"%([^%]+)%", lambda m: os.environ.get(m.group(1), m.group(0)), p)
    return os.path.expanduser(os.path.expandvars(out))


def vkey(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def _version(cmd: list[str], rx: str | None) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    if rx:
        m = re.search(rx, out)
        return m.group(1) if m else None
    line = out.strip().splitlines()
    return line[0][:80] if line else None


def which(name: str, path: str | None) -> str | None:
    return shutil.which(name, path=path) if path is not None else shutil.which(name)


def vitasdk_dir() -> Path | None:
    v = os.environ.get("VITASDK")
    if not v:
        return None
    p = Path(_expand(v))
    if (p / "bin" / "arm-vita-eabi-gcc").exists() or (p / "bin" / "arm-vita-eabi-gcc.exe").exists():
        return p
    return None


def vdpm_installed_native(sdk: Path) -> dict[str, str]:
    """name -> version from the SDK's pacman database (vdpm 2026+), else from `vdpm list`."""
    db = sdk / "var" / "lib" / "pacman" / "local"
    out = {}
    if db.is_dir():
        for d in db.iterdir():
            parts = d.name.rsplit("-", 2)
            if d.is_dir() and len(parts) == 3:
                out[parts[0]] = f"{parts[1]}-{parts[2]}"
        return out
    vdpm = sdk / "bin" / "vdpm"
    if vdpm.exists():
        try:
            r = subprocess.run([str(vdpm), "list"], capture_output=True, text=True, timeout=60)
            for line in r.stdout.splitlines():
                m = re.match(r"^([\w.+-]+)\s+(\S+)$", line.strip())
                if m:
                    out[m.group(1)] = m.group(2)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return out


def docker_ok(path: str | None) -> tuple[bool, str]:
    d = which("docker", path)
    if not d:
        return False, "docker not on PATH"
    try:
        r = subprocess.run([d, "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"docker info failed: {e}"
    if r.returncode:
        return False, "the Docker daemon isn't reachable (is Docker running?)"
    return True, r.stdout.strip()


def docker_image_present(image: str, path: str | None) -> bool:
    d = which("docker", path)
    if not d:
        return False
    r = subprocess.run([d, "image", "inspect", image, "--format", "{{.Id}}"], capture_output=True, text=True)
    return r.returncode == 0


def vdpm_installed_docker(image: str, path: str | None) -> dict[str, str]:
    d = which("docker", path)
    r = subprocess.run([d or "docker", "run", "--rm", image, "sh", "-c", "ls $VITASDK/var/lib/pacman/local"],
                       capture_output=True, text=True, timeout=120)
    out = {}
    for name in r.stdout.split():
        parts = name.rsplit("-", 2)
        if len(parts) == 3:
            out[parts[0]] = f"{parts[1]}-{parts[2]}"
    return out


def tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_tool(tid: str, spec: dict, osk: str | None = None, path: str | None = None, cfg: dict | None = None) -> dict:
    osk = osk or os_key()
    cfg = cfg or {}
    kind = spec.get("kind", "bin")
    res: dict = dict(id=tid, name=spec.get("name", tid), kind=kind, found=False, path=None, version=None, ok=False,
                     homepage=spec.get("homepage"))
    platforms = spec.get("platforms", ["windows", "linux", "macos"])
    install = spec.get("install", {})
    res["install"] = {k: install[k] for k in ("windows", "linux", "macos") if k in install}
    if osk not in platforms:
        res.update(available=False, note=f"not available on {osk}")
        return res
    res["available"] = True
    if kind == "vitasdk":
        sdk = vitasdk_dir() if path is None else None
        if sdk:
            res.update(found=True, path=str(sdk))
            vf = sdk / "version_info.txt"
            if vf.exists():
                m = re.search(spec.get("version_regex", r"([0-9.]+)"), vf.read_text(encoding="utf-8", errors="replace"))
                res["version"] = m.group(1) if m else None
            res["toolchain_file"] = (sdk / "share" / "vita.toolchain.cmake").exists()
            if not res["toolchain_file"]:
                res["note"] = "share/vita.toolchain.cmake is missing"
        elif os.environ.get("VITASDK"):
            res["note"] = f"$VITASDK is {os.environ['VITASDK']} but bin/arm-vita-eabi-gcc isn't there"
        res["ok"] = res["found"] and res.get("toolchain_file", False)
        return res
    if kind == "docker-image":
        image = (cfg.get("build", {}) or {}).get("docker_image") or spec.get("image", "vitasdk/vitasdk:latest")
        res["image"] = image
        up, how = docker_ok(path)
        if not up:
            res["note"] = how
            return res
        res.update(found=True, path=which("docker", path), version=how)
        res["ok"] = docker_image_present(image, path)
        if not res["ok"]:
            res["note"] = f"image {image} not pulled yet (vita never pulls it by itself): docker pull {image}"
        return res
    if kind == "vita3k":
        exe = find_vita3k(cfg, path)
        if exe:
            res.update(found=True, ok=True, path=exe)
        return res
    if kind == "vitacompanion":
        dev = cfg.get("device", {})
        ip = dev.get("ip")
        if not ip:
            res.update(note="no [device] ip in vita.toml: not checked", skipped=True)
            return res
        ftp, cmd = tcp_open(ip, int(dev.get("ftp_port", 1337))), tcp_open(ip, int(dev.get("cmd_port", 1338)))
        res.update(found=ftp or cmd, ok=ftp and cmd, path=ip, version=f"ftp {'open' if ftp else 'closed'}, commands {'open' if cmd else 'closed'}")
        if not res["ok"]:
            res["note"] = f"{ip}: is the Vita on the same network, awake, with vitacompanion loaded?"
        return res
    for b in spec.get("bin", []):
        p = which(b, path)
        if p:
            res.update(found=True, path=p)
            if spec.get("version"):
                res["version"] = _version([p, *spec["version"]], spec.get("version_regex"))
            break
    env = spec.get("env")
    if not res["found"] and env and os.environ.get(env) and path is None:
        ep = Path(_expand(os.environ[env]))
        files = spec.get("env_files", [])
        if ep.is_file():
            res.update(found=True, path=str(ep))
        elif ep.is_dir():
            hit = next((ep / f for f in files if (ep / f).exists()), None)
            if hit or not files:
                res.update(found=True, path=str(hit or ep))
            else:
                res["note"] = f"${env} is set to {ep} but none of {', '.join(files)} is there"
        else:
            res["note"] = f"${env} points to {ep}, which doesn't exist"
    if not res["found"] and path is None:
        for pat in spec.get("paths", []):
            hits = sorted(glob.glob(_expand(pat)))
            if hits:
                res.update(found=True, path=hits[-1])
                break
    res["ok"] = res["found"]
    if res["found"] and spec.get("min_version"):
        if res["version"] and vkey(res["version"]) < vkey(spec["min_version"]):
            res["ok"] = False
            res["note"] = f"version {res['version']} is older than the required {spec['min_version']}"
    return res


def find_vita3k(cfg: dict, path: str | None = None) -> str | None:
    """vita.toml [emu] vita3k, then $VITA3K, PATH, the usual install folders."""
    spec = registry()["tools"]["vita3k"]
    configured = (cfg.get("emu", {}) or {}).get("vita3k")
    if configured and path is None:
        p = Path(_expand(configured))
        return str(p) if p.exists() else None
    for b in spec.get("bin", []):
        p = which(b, path)
        if p:
            return p
    if path is not None:
        return None
    if os.environ.get("VITA3K") and Path(_expand(os.environ["VITA3K"])).exists():
        return _expand(os.environ["VITA3K"])
    for pat in spec.get("paths", []):
        hits = sorted(glob.glob(_expand(pat)))
        if hits:
            return hits[-1]
    return None


def check_all(cfg: dict, osk: str | None = None, path: str | None = None) -> dict:
    reg = registry()
    group = reg["groups"]["check"]
    osk = osk or os_key()
    backend = (cfg.get("build", {}) or {}).get("backend", "auto")
    out: dict = dict(os=osk, backend=backend, toolchain={}, required=[], optional=[], packages=[], device=None)
    tc = {tid: check_tool(tid, reg["tools"][tid], osk, path, cfg) for tid in group["one_of"][0]}
    if backend == "native":
        chosen = "vitasdk" if tc["vitasdk"]["ok"] else None
        needed = ["vitasdk"]
    elif backend == "docker":
        chosen = "docker-image" if tc["docker-image"]["ok"] else None
        needed = ["docker-image"]
    else:
        chosen = "vitasdk" if tc["vitasdk"]["ok"] else "docker-image" if tc["docker-image"]["ok"] else None
        needed = ["vitasdk", "docker-image"]
    out["toolchain"] = dict(chosen=chosen, candidates=[tc[t] for t in needed])
    for kind in ("required", "optional"):
        for tid in group.get(kind, []):
            out[kind].append(check_tool(tid, reg["tools"][tid], osk, path, cfg))
    # vdpm packages: the backend's own database
    wanted = list(dict.fromkeys(ALWAYS_VDPM + list((cfg.get("build", {}) or {}).get("vdpm", []))))
    have: dict[str, str] = {}
    if chosen == "vitasdk":
        have = vdpm_installed_native(Path(tc["vitasdk"]["path"]))
    elif chosen == "docker-image":
        try:
            have = vdpm_installed_docker(tc["docker-image"]["image"], path)
        except (OSError, subprocess.TimeoutExpired):
            have = {}
    for pkg in wanted:
        alt = {"sdl2": "sdl2_vitagl", "sdl2_vitagl": "sdl2"}.get(pkg)
        ver = have.get(pkg) or (have.get(alt) if alt else None)
        flavour = pkg if pkg in have else alt if ver else None
        out["packages"].append(dict(name=pkg, ok=bool(ver), version=ver, installed_as=flavour, checked_in=chosen,
                                    install=f"vdpm install {pkg}" if chosen != "docker-image" else
                                    f"the {tc['docker-image'].get('image')} image lacks it: build a derived image with `vdpm install {pkg}`"))
    dev = check_tool("vitacompanion", reg["tools"]["vitacompanion"], osk, path, cfg)
    out["device"] = dev
    missing = [] if chosen else [f"toolchain ({' or '.join(needed)})"]
    missing += [t["id"] for t in out["required"] if t.get("available", True) and not t["ok"]]
    missing += [f"vdpm:{p['name']}" for p in out["packages"] if not p["ok"] and chosen]
    if not dev.get("skipped") and not dev["ok"]:
        missing.append("vitacompanion")
    out["missing"] = missing
    out["ok"] = not missing
    out["vita3k"] = next((t for t in out["optional"] if t["id"] == "vita3k"), None)
    return out


def _steps(t: dict, osk: str) -> list[str]:
    steps = t["install"].get(osk) or t["install"].get("linux") or "see the homepage"
    return [f"    {ln}" for ln in steps.splitlines()]


def format_check(r: dict) -> str:
    osk = r["os"] if r["os"] in ("windows", "linux", "macos") else "linux"
    L = [f"vita tools check (on {r['os']}, build backend {r['backend']})"]

    def line(t, kind):
        mark = " ok " if t["ok"] else ("OLD " if t["found"] else ("MISS" if kind == "required" else " -- "))
        ver = f" {t['version']}" if t.get("version") else ""
        where = f"  ({t['path']})" if t.get("path") else ""
        L.append(f"   [{mark}] {t['name']}{ver}{where}")
        if t.get("note"):
            L.append(f"          note: {t['note']}")

    L.append("  toolchain (one of):" + (f"  -> using {r['toolchain']['chosen']}" if r["toolchain"]["chosen"] else ""))
    for t in r["toolchain"]["candidates"]:
        line(t, "required" if not r["toolchain"]["chosen"] else "optional")
    L.append("  required:")
    for t in r["required"]:
        line(t, "required")
    if r["packages"]:
        L.append(f"  vdpm packages (in {r['toolchain']['chosen'] or 'no toolchain'}):")
        for p in r["packages"]:
            mark = " ok " if p["ok"] else "MISS"
            L.append(f"   [{mark}] {VDPM_HINT.get(p['name'], p['name'])}" + (f" {p['version']}" if p["version"] else "")
                     + (f" (as {p['installed_as']})" if p.get("installed_as") and p["installed_as"] != p["name"] else ""))
    L.append("  optional:")
    for t in r["optional"]:
        line(t, "optional")
    d = r["device"]
    if d.get("skipped"):
        L.append(f"  device: {d['note']}")
    else:
        L.append("  device:")
        line(d, "required")
    if r["missing"]:
        L.append("")
        L.append("MISSING: stop here and give the user these steps (the agent never installs anything itself):")
        if not r["toolchain"]["chosen"]:
            L.append("\n  A Vita toolchain: either VitaSDK natively or Docker with the vitasdk image.")
            for t in r["toolchain"]["candidates"]:
                L.append(f"  - {t['name']} — {t.get('homepage') or ''}")
                L += _steps(t, osk)
        for t in r["required"] + ([d] if not d.get("skipped") else []):
            if t.get("available", True) and not t["ok"]:
                L.append(f"\n  {t['name']}  — {t.get('homepage') or ''}")
                L += _steps(t, osk)
        for p in r["packages"]:
            if not p["ok"] and r["toolchain"]["chosen"]:
                L.append(f"\n  vdpm package {p['name']}:\n    {p['install']}")
        L.append("\nThen re-run: vita tools check")
    else:
        L.append("\nall required tools found")
    v = r.get("vita3k")
    if v and not v["ok"]:
        L.append("Vita3K is not installed: optional. The loop continues without the emulator level (`vita emu` is skipped).")
    return "\n".join(L)


def main(a):
    reg = registry()
    if a.cmd == "list":
        if a.json:
            emit_json(dict(groups=reg["groups"], tools=sorted(reg["tools"])))
            return OK
        for k, v in reg["groups"].items():
            print(f"{k}: {v.get('label', '')}")
            print(f"  one of: {', '.join('/'.join(x) for x in v.get('one_of', []))}")
            print(f"  required: {', '.join(v.get('required', []))}")
            print(f"  optional: {', '.join(v.get('optional', []))}")
        print(f"\ntools ({len(reg['tools'])}): {', '.join(sorted(reg['tools']))}")
        return OK
    root = find_project()
    cfg = load_config(root) if root else {}
    if a.cmd == "show":
        if a.tool not in reg["tools"]:
            usage(f"unknown tool {a.tool!r}; see `vita tools list`")
        r = check_tool(a.tool, reg["tools"][a.tool], cfg=cfg)
        if a.json:
            emit_json(r)
        else:
            spec = reg["tools"][a.tool]
            print(f"{r['name']}: {spec.get('description', '')}\n  homepage: {r.get('homepage')}\n  status:   "
                  f"{'found ' + str(r['path']) if r['found'] else 'not found'}" + (f" (version {r['version']})" if r.get("version") else ""))
            if r.get("note"):
                print(f"  note:     {r['note']}")
            for k, v in r["install"].items():
                print(f"  install ({k}):\n    " + v.replace("\n", "\n    "))
        return OK if r["ok"] else PROBLEM
    r = check_all(cfg, path=a.mock_path)
    if a.json:
        emit_json(r)
    else:
        print(format_check(r))
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("tools", help="check VitaSDK/Docker, vdpm packages, ffmpeg, pngquant, Vita3K, vitacompanion (never installs)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="check everything the port needs", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("--mock-path", help=argparse.SUPPRESS)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("list", help="the tools in the registry")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("show", help="one tool: description, status, install steps")
    q.add_argument("tool")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
