"""Build the .vpk with VitaSDK: configure + build the CMake project for the Vita, keep the full log, print a short
error summary, then check the ELF for unresolved imports.

    vita build                         # native if $VITASDK is valid, else Docker (vita.toml [build] backend)
    vita build --docker                # in the vitasdk/vitasdk image (must be pulled: vita tools check)
    vita build --native --config Debug
    vita build -D GAME_NO_NETWORK=ON   # extra cache options (also: [build] options in vita.toml)
    vita build --fresh                 # wipe the CMake cache first
    vita build --build-dir build-vita-ext -D VITA_ASSETS_MODE=external   # a second flavour next to the first
    vita build --json                  # {ok, vpk, elf, unresolved, errors: [{file, line, message}], log}

The configure passes the toolchain file ($VITASDK/share/vita.toolchain.cmake, which sets VITA=True) and the
values from vita.toml, for the project's Vita target (cmake/VitaPort.cmake reads them):
  VITA_TITLEID VITA_APP_NAME VITA_VERSION VITA_DATA_FOLDER VITA_ASSETS_MODE VITA_ASSETS_DIR VITA_ASSETS_VPK_DIR
  VITA_LIVEAREA_DIR VITA_UNSAFE VITA_EXTENDED_MEMORY
If vita-elf-create fails with "Cannot allocate N bytes for SCE data ... overlaps" (the code segment ends just
below the 64 KiB-aligned data segment), the build is retried once with -D VITAPORT_ELF_PAD=4096.
Full log: build-vita/vita-build.log. After a successful build `arm-vita-eabi-nm -u` runs on the ELF: any `U`
symbol is an unresolved import (vita-elf-create stays silent about them when the link allowed it).
Exit code 1 on a failed configure/build, a missing .vpk, or unresolved imports.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, is_windows, load_config, rel, project_root, usage
from vita_porter.tools import docker_image_present, vitasdk_dir

ERROR_RX = [
    re.compile(r"^(?P<file>[^\s:][^:]*?|[A-Za-z]:[^:]+?):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?:fatal )?error:\s*(?P<msg>.+)$"),
    re.compile(r"^(?P<file>[^:\s]+\.o(?:bj)?)?:?.*?(?P<msg>undefined reference to .+|undefined symbol: .+|multiple definition of .+)$"),
    re.compile(r"^CMake Error(?: at (?P<file>[^:]+):(?P<line>\d+))?.*?:?\s*(?P<msg>.*)$"),
    re.compile(r"^(?P<msg>(?:Unable to relocate ELF sections|Failed to .+|.*vita-(?:elf-create|make-fself|mksfoex|pack-vpk).*(?:error|failed|Cannot allocate).*))$", re.I),
]
WARN_RX = re.compile(r"(?:^|\s)warning\s*:", re.I)


def parse_errors(log: str, limit: int = 10) -> tuple[list[dict], int, int]:
    errors, seen, total = [], set(), 0
    lines = log.splitlines()
    for i, ln in enumerate(lines):
        for rx in ERROR_RX:
            m = rx.match(ln.rstrip())
            if not m:
                continue
            d = {k: v for k, v in m.groupdict().items() if v}
            msg = d.get("msg", "").strip()
            if rx.pattern.startswith("^CMake Error") and not msg and i + 1 < len(lines):
                msg = lines[i + 1].strip()
            sig = (d.get("file"), d.get("line"), msg)
            if sig in seen:
                break
            seen.add(sig)
            total += 1
            if len(errors) < limit:
                errors.append(dict(file=d.get("file"), line=int(d["line"]) if d.get("line") else None, message=msg[:300]))
            break
    return errors, total, sum(1 for ln in lines if WARN_RX.search(ln))


def run_logged(cmd: list[str], cwd: Path, log) -> int:
    log.write(f"\n$ {' '.join(cmd)}\n")
    log.flush()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    assert p.stdout
    for line in p.stdout:
        log.write(line)
    return p.wait()


def defines(root: Path, cfg: dict, prefix: str) -> list[str]:
    """-D values from vita.toml. prefix: how the container (or host) sees the repo root."""
    app, assets, la = cfg.get("app", {}), cfg.get("assets", {}), cfg.get("livearea", {})
    out = assets.get("out", "build-vita/assets")
    onoff = lambda b: "ON" if b else "OFF"
    vals = {
        "VITA_TITLEID": app.get("title_id", ""), "VITA_APP_NAME": app.get("name", ""), "VITA_VERSION": app.get("version", "01.00"),
        "VITA_DATA_FOLDER": app.get("data_folder", ""), "VITA_ASSETS_MODE": app.get("assets", "embedded"),
        "VITA_ASSETS_DIR": f"{prefix}/{out}", "VITA_ASSETS_VPK_DIR": assets.get("vpk_dir", "assets"),
        "VITA_LIVEAREA_DIR": f"{prefix}/{la.get('dir', 'sce_sys')}", "VITA_UNSAFE": onoff(app.get("unsafe", False)),
        "VITA_EXTENDED_MEMORY": onoff(app.get("extended_memory", False)),
    }
    return [f"-D{k}={v}" for k, v in vals.items() if v != ""]


def pick_backend(cfg: dict, want: str | None) -> str:
    want = want or cfg.get("build", {}).get("backend", "auto")
    if want == "native":
        if not vitasdk_dir():
            usage("native build requested but $VITASDK isn't a valid VitaSDK (see `vita tools check`)")
        return "native"
    if want == "docker":
        return "docker"
    return "native" if vitasdk_dir() else "docker"


def find_outputs(out: Path, cfg: dict, root: Path, since: float) -> tuple[Path | None, Path | None, list[str]]:
    b = cfg.get("build", {})
    notes = []
    vpk = (root / b["vpk"]) if b.get("vpk") else None
    if vpk is None:
        cands = sorted(out.glob("*.vpk"), key=lambda p: p.stat().st_mtime, reverse=True)
        if len(cands) > 1:
            notes.append(f"several .vpk files in {rel(root, out)}: using the newest; set [build] vpk in vita.toml")
        vpk = cands[0] if cands else None
    elf = (root / b["elf"]) if b.get("elf") else None
    if elf is None:
        cands = []
        for p in out.rglob("*"):
            if p.is_file() and p.suffix in ("", ".elf") and "CMakeFiles" not in p.parts and p.stat().st_size > 1024:
                try:
                    with open(p, "rb") as fh:
                        h = fh.read(20)
                except OSError:
                    continue
                if h[:4] == b"\x7fELF" and h[18:20] == b"\x28\x00" and h[16:18] == b"\x02\x00":   # ARM ET_EXEC: the linked program
                    cands.append(p)
        cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        elf = cands[0] if cands else None
    if vpk and vpk.stat().st_mtime < since - 1:
        notes.append(f"{rel(root, vpk)} was not rewritten by this build (is the vpk target part of ALL?)")
    return vpk, elf, notes


def unresolved(elf: Path, backend: str, root: Path, image: str) -> tuple[list[str], str | None]:
    if backend == "native":
        sdk = vitasdk_dir()
        nm = str(sdk / "bin" / "arm-vita-eabi-nm") if sdk else "arm-vita-eabi-nm"
        cmd = [nm, "-u", str(elf)]
    else:
        cmd = docker_cmd(root, image, f"$VITASDK/bin/arm-vita-eabi-nm -u /src/{rel(root, elf)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as e:
        return [], f"could not run nm: {e}"
    if r.returncode:
        return [], f"nm failed: {(r.stderr or r.stdout).strip()[-300:]}"
    return [ln.split()[-1] for ln in r.stdout.splitlines() if ln.strip().startswith("U ")], None


def docker_cmd(root: Path, image: str, script: str) -> list[str]:
    cmd = ["docker", "run", "--rm", "-v", f"{root}:/src", "-w", "/src", "-e", "HOME=/tmp"]
    if not is_windows() and hasattr(os, "getuid"):
        cmd += ["-u", f"{os.getuid()}:{os.getgid()}"]
    return cmd + [image, "sh", "-c", script]


def build(root: Path, backend: str | None = None, config: str | None = None, extra: list[str] | None = None, fresh: bool = False,
          max_errors: int = 10, target: str | None = None, build_dir: str | None = None, _retrying: bool = False) -> dict:
    cfg = load_config(root)
    b = cfg.get("build", {})
    backend = pick_backend(cfg, backend)
    image = b.get("docker_image", "vitasdk/vitasdk:latest")
    src_rel = (cfg.get("project", {}).get("source_dir") or ".").strip("/") or "."
    out_rel = (build_dir or b.get("build_dir", "build-vita")).strip("/")
    out = root / out_rel
    config = config or b.get("config") or "Release"
    if not (root / src_rel / "CMakeLists.txt").exists():
        usage(f"no CMakeLists.txt in {src_rel} (the port adds a Vita target to the project's CMake build)")
    if backend == "docker":
        if not shutil.which("docker"):
            usage("Docker isn't on PATH and there's no native VitaSDK (see `vita tools check`)")
        if not docker_image_present(image, None):
            usage(f"the {image} image isn't pulled; vita never pulls it by itself. Ask the user: docker pull {image}")
    cache, marker = out / "CMakeCache.txt", out / ".vita-backend"
    if cache.exists() and (not marker.exists() or marker.read_text(encoding="utf-8").strip() != backend):
        fresh = True    # configured by the other backend (its paths are /src/... or host paths): start over
    if fresh and cache.exists():
        cache.unlink()
        shutil.rmtree(out / "CMakeFiles", ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    marker.write_text(backend + "\n", encoding="utf-8")
    logp = out / "vita-build.log"
    gen = b.get("generator") or ""
    opts = list(b.get("options", [])) + [f"-D{x}" if not x.startswith("-D") else x for x in (extra or [])]
    t0 = time.time()
    with open(logp, "w", encoding="utf-8", newline="\n") as log:
        if backend == "native":
            sdk = vitasdk_dir()
            env_tc = str(sdk / "share" / "vita.toolchain.cmake")  # type: ignore[operator]
            configure = ["cmake", "-S", str(root / src_rel), "-B", str(out), f"-DCMAKE_TOOLCHAIN_FILE={env_tc}", f"-DCMAKE_BUILD_TYPE={config}",
                         *(["-G", gen] if gen else []), *defines(root, cfg, root.as_posix()), *opts]
            rc = run_logged(configure, root, log)
            stage = "configure"
            if rc == 0:
                stage = "build"
                rc = run_logged(["cmake", "--build", str(out), "--parallel", *(["--target", target] if target else [])], root, log)
        else:
            q = lambda s: "'" + s.replace("'", "'\\''") + "'"
            conf = ["cmake", "-S", f"/src/{src_rel}", "-B", f"/src/{out_rel}", "-DCMAKE_TOOLCHAIN_FILE=$VITASDK/share/vita.toolchain.cmake",
                    f"-DCMAKE_BUILD_TYPE={config}", *(["-G", gen] if gen else []), *defines(root, cfg, "/src"), *opts]
            script = " ".join(c if c.startswith("-DCMAKE_TOOLCHAIN_FILE") else q(c) for c in conf)
            script += f" && echo '@@configured' && cmake --build /src/{out_rel} --parallel" + (f" --target {q(target)}" if target else "")
            rc = run_logged(docker_cmd(root, image, script), root, log)
            stage = "build" if "@@configured" in logp.read_text(encoding="utf-8", errors="replace") else "configure"
    text = logp.read_text(encoding="utf-8", errors="replace")
    overlap = re.search(r"Cannot allocate (\d+) bytes for SCE data at end of segment \d+; segment \d+ overlaps", text)
    if rc and overlap and not any("VITAPORT_ELF_PAD" in x for x in (extra or [])) and not _retrying:
        # the code segment ends too close to the 64 KiB-aligned data segment for vita-elf-create's import tables:
        # pad .rodata (cmake/VitaPort.cmake) and build once more
        r = build(root, backend, config, [*(extra or []), "VITAPORT_ELF_PAD=4096"], False, max_errors, target, build_dir, _retrying=True)
        r["notes"].insert(0, f"vita-elf-create couldn't fit {overlap.group(1)} bytes of import tables between the code and data segments "
                             "(code size happened to end just below a 64 KiB boundary); rebuilt with -D VITAPORT_ELF_PAD=4096 "
                             "(cmake/VitaPort.cmake). Keep that option in [build] options if it recurs.")
        return r
    errors, nerr, nwarn = parse_errors(text, max_errors)
    res: dict = dict(ok=rc == 0, backend=backend, stage=stage, exit_code=rc, config=config, seconds=round(time.time() - t0, 1),
                     errors=errors, error_count=nerr, warning_count=nwarn, log=rel(root, logp), vpk=None, elf=None, unresolved=[], notes=[])
    if rc == 0:
        vpk, elf, notes = find_outputs(out, {} if build_dir else cfg, root, t0)   # [build] vpk/elf name the default folder's files
        res["notes"] += notes
        res["vpk"] = rel(root, vpk) if vpk else None
        res["elf"] = rel(root, elf) if elf else None
        if not vpk:
            res["ok"] = False
            res["notes"].append("the build succeeded but produced no .vpk: add vita_create_self + vita_create_vpk (cmake/VitaPort.cmake)")
        if elf:
            uns, err = unresolved(elf, backend, root, image)
            res["unresolved"] = uns
            if err:
                res["notes"].append(err)
            if uns:
                res["ok"] = False
        else:
            res["notes"].append("no linked ARM ELF found in the build folder: unresolved imports not checked")
    return res


def main(a):
    root = project_root()
    backend = "docker" if a.docker else "native" if a.native else None
    r = build(root, backend, a.config, a.define, a.fresh, a.max_errors, a.target, a.build_dir)
    if a.json:
        emit_json(r)
        return OK if r["ok"] else PROBLEM
    if r["exit_code"] == 0:
        print(f"build {'OK' if r['ok'] else 'FINISHED WITH PROBLEMS'} ({r['backend']}, {r['config']}, {r['seconds']} s, "
              f"{r['warning_count']} warning lines). Log: {r['log']}")
        if r["vpk"]:
            print(f"  vpk: {r['vpk']}")
        if r["elf"]:
            print(f"  elf: {r['elf']}  (unresolved imports: {len(r['unresolved']) or 'none'})")
        for u in r["unresolved"][:20]:
            print(f"  UNRESOLVED: {u}")
        if r["vpk"]:
            print(f"next: vita vpk check {r['vpk']}")
    else:
        print(f"{r['stage']} FAILED ({r['backend']}, exit {r['exit_code']}, {r['error_count']} errors, {r['seconds']} s). Full log: {r['log']}")
        for e in r["errors"]:
            loc = f"{e['file']}:{e['line']}" if e.get("line") else (e.get("file") or "")
            print(f"  {loc + ': ' if loc else ''}{e['message']}")
        if r["error_count"] > len(r["errors"]):
            print(f"  ... {r['error_count'] - len(r['errors'])} more in the log")
        if not r["errors"]:
            print("  (no recognisable error lines: read the end of the log)")
    for n in r["notes"]:
        print(f"  note: {n}")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("build", help="build the .vpk with VitaSDK (native or Docker); full log, short error summary",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--docker", action="store_true", help="build in the vitasdk/vitasdk image")
    g.add_argument("--native", action="store_true", help="build with $VITASDK")
    p.add_argument("--config", choices=["Debug", "Release", "RelWithDebInfo", "MinSizeRel"])
    p.add_argument("--target", help="build only this CMake target")
    p.add_argument("--build-dir", help="build folder (default: [build] build_dir, build-vita), e.g. for a second assets mode")
    p.add_argument("-D", "--define", action="append", help="extra CMake cache entry, e.g. -D GAME_NO_NETWORK=ON")
    p.add_argument("--fresh", action="store_true", help="delete CMakeCache.txt first")
    p.add_argument("--max-errors", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
