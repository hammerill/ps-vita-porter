"""Build the .vpk with VitaSDK: configure + build the CMake project for the Vita, keep the full log, print a short
error summary, then check the ELF for unresolved imports.

    vita build                         # native if $VITASDK is valid, else Docker (vita.toml [build] backend)
    vita build --docker                # in the vitasdk/vitasdk image (must be pulled: vita tools check)
    vita build --native --config Debug
    vita build -D GAME_NO_NETWORK=ON   # extra cache options (also: [build] options in vita.toml)
    vita build --fresh                 # wipe the CMake cache first
    vita build --build-dir build-vita-ext -D VITA_ASSETS_MODE=external   # a second flavour next to the first
    vita build -j 4                    # at most 4 compile jobs (also: [build] jobs in vita.toml)
    vita build --json                  # {ok, vpk, elf, unresolved, errors: [{file, line, message}], jobs, killed, log}

Parallel jobs are always bounded. A bare `cmake --build --parallel` means `make -j` with no limit, and hundreds of
C++ compilers at once can exhaust RAM and take WSL down. The job count comes from --jobs, then [build] jobs, then
$CMAKE_BUILD_PARALLEL_LEVEL, else min(CPUs, available GiB), and is lowered so each job has at least 700 MiB
(only --jobs is obeyed as given). On WSL, also consider giving the VM more memory in %UserProfile%\\.wslconfig:
[wsl2] memory=12GB, swap=8GB.
The build runs in its own process group and is killed whole (Docker: the container too) on Ctrl+C, after
[build] timeout_min (default 120, or --timeout-min), or after [build] stall_min (default 15) with no output; 0 = off.
A build that never finished (the machine or WSL went down) is detected next time: its precompiled headers, which
may be half-written, are deleted; corrupt ones (-Winvalid-pch, "not a PCH file") are deleted too.

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
import sys
import threading
import time
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, is_windows, load_config, rel, project_root, usage
from vita_porter.proc import kill_tree
from vita_porter.tools import docker_image_present, vitasdk_dir

GIB = 1 << 30
JOB_MIN_MEM = 700 << 20
TIMEOUT_MIN, STALL_MIN = 120, 15

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


def run_logged(cmd: list[str], cwd: Path, log, timeout: float = 0, stall: float = 0, status: dict | None = None,
               docker_name: str | None = None) -> int:
    """Run cmd in its own process group with its output appended to log. timeout/stall (seconds, 0 = off): kill the
    whole group when the run takes longer, or when it prints nothing for that long; status["killed"] says why.
    Ctrl+C kills the group too (a Ctrl+C'd `cmake --build` used to leave make and the compilers running)."""
    log.write(f"\n$ {' '.join(cmd)}\n")
    log.flush()
    kw: dict = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if is_windows() else {"start_new_session": True}  # type: ignore[attr-defined]
    t0 = time.time()
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                         encoding="utf-8", errors="replace", **kw)
    assert p.stdout
    last, done = [t0], threading.Event()

    def stop(why: str):
        if status is not None:
            status["killed"] = why
        if docker_name:   # the container outlives its `docker run` client
            subprocess.run(["docker", "kill", docker_name], capture_output=True)
        kill_tree(p, Path(cmd[0]), t0)

    def watch():
        while not done.wait(2):
            now = time.time()
            if timeout and now - t0 > timeout:
                return stop(f"took longer than {timeout / 60:g} min ([build] timeout_min)")
            if stall and now - last[0] > stall:
                return stop(f"printed nothing for {stall / 60:g} min ([build] stall_min): hung, or swapping")

    th = threading.Thread(target=watch, daemon=True)
    th.start()
    try:
        for line in p.stdout:
            log.write(line)
            last[0] = time.time()
        rc = p.wait()
    except KeyboardInterrupt:
        stop("interrupted (Ctrl+C)")
        log.write("\n@@vita: interrupted, the build's process group was killed\n")
        raise
    finally:
        done.set()
    if status is not None and status.get("killed"):
        log.write(f"\n@@vita: killed, {status['killed']}\n")
    return rc


def cpu_count() -> int:
    if hasattr(os, "process_cpu_count"):
        return os.process_cpu_count() or 1
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0)) or 1
    return os.cpu_count() or 1


def mem_available() -> int | None:
    """Bytes of RAM available right now (Linux/WSL: MemAvailable; Windows: available physical), None if unknown."""
    try:
        for ln in Path("/proc/meminfo").read_text().splitlines():
            if ln.startswith("MemAvailable:"):
                return int(ln.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    if is_windows():
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), *((f, ctypes.c_ulonglong) for f in
                        ("total", "avail", "ptotal", "pavail", "vtotal", "vavail", "xavail"))]
        m = MS()
        m.len = ctypes.sizeof(MS)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):  # type: ignore[attr-defined]
            return m.avail
    return None


def job_count(cfg: dict, cli: int | None) -> tuple[int, str]:
    """Parallel compile jobs for `cmake --build --parallel N` and why. Never unbounded: a bare --parallel is `make -j`,
    and a heavy C++ compile takes up to ~1 GiB, so hundreds of them at once take the machine down (WSL included).
    Order: --jobs, [build] jobs, $CMAKE_BUILD_PARALLEL_LEVEL, else min(CPUs, available GiB). The last two are
    lowered to fit at least 700 MiB per job; --jobs is obeyed with a warning."""
    cpus, avail = cpu_count(), mem_available()
    env = os.environ.get("CMAKE_BUILD_PARALLEL_LEVEL", "").strip()
    conf = cfg.get("build", {}).get("jobs") or 0
    n, src = (cli, "--jobs") if cli else (int(conf), "[build] jobs") if int(conf) > 0 else \
             (int(env), "$CMAKE_BUILD_PARALLEL_LEVEL") if env.isdigit() and int(env) > 0 else (0, "auto")
    gib = f"{avail / GIB:.1f} GiB available" if avail is not None else "available memory unknown"
    if src == "auto":
        n = max(1, min(cpus, avail // GIB)) if avail is not None else cpus
        return n, f"{n} jobs ({cpus} CPUs, {gib}, about 1 GiB per C++ compile job)"
    fit = max(1, avail // JOB_MIN_MEM) if avail is not None else n
    if n > fit:
        if src == "--jobs":
            return n, f"{n} jobs ({src}); warning: {gib}, under 700 MiB per job: the build may run out of memory"
        return fit, f"{n} jobs ({src}) -> {fit} jobs: {gib}"
    return n, f"{n} jobs ({src})"


def build_limits(cfg: dict, timeout_min: float | None = None) -> tuple[float, float]:
    """(whole-build timeout, no-output stall timeout) in seconds from [build] timeout_min / stall_min; 0 = off."""
    b = cfg.get("build", {})
    t = timeout_min if timeout_min is not None else b.get("timeout_min", TIMEOUT_MIN)
    return float(t or 0) * 60, float(b.get("stall_min", STALL_MIN) or 0) * 60


def pch_files(out: Path) -> list[Path]:
    return [p for p in out.rglob("cmake_pch*") if p.suffix in (".gch", ".pch") and "CMakeFiles" in p.parts] if out.is_dir() else []


def bad_pch(out: Path) -> list[Path]:
    """Precompiled headers that aren't one (a build killed while writing them leaves garbage that GCC then rejects with
    -Winvalid-pch on every file of that target). GCC's start with "gpch", Clang's with "CPCH"."""
    bad = []
    for p in pch_files(out):
        try:
            with open(p, "rb") as fh:
                head = fh.read(4)
        except OSError:
            continue
        if head not in (b"gpch", b"CPCH"):
            bad.append(p)
    return bad


def pid_alive(pid: int) -> bool:
    if is_windows() or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        return "vita" in Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return True


def recover(root: Path, out: Path, running: Path) -> list[str]:
    """Clean up after an earlier build that never finished (WSL or the machine went down, the process was killed)."""
    notes = []
    if running.exists():
        try:
            pid = int(running.read_text().split()[0])
        except (ValueError, IndexError):
            pid = 0
        if pid_alive(pid):
            usage(f"another vita build (pid {pid}) is using {rel(root, out)}; wait for it, or stop exactly that PID")
        gone = pch_files(out)
        for p in gone:
            p.unlink(missing_ok=True)
        notes.append(f"the previous build in {rel(root, out)} never finished (killed, out of memory, or WSL went down)"
                     + (f": deleted {len(gone)} precompiled header(s) it may have left half-written" if gone else "")
                     + ". If the link then fails on a damaged object file, run `vita build --fresh`.")
    else:
        bad = bad_pch(out)
        for p in bad:
            p.unlink(missing_ok=True)
        if bad:
            notes.append(f"deleted {len(bad)} corrupt precompiled header(s) (not a GCC/Clang PCH): "
                         + ", ".join(rel(root, p) for p in bad[:3]))
    return notes


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


def docker_cmd(root: Path, image: str, script: str, name: str | None = None) -> list[str]:
    cmd = ["docker", "run", "--rm", "-v", f"{root}:/src", "-w", "/src", "-e", "HOME=/tmp", *(["--name", name] if name else [])]
    if not is_windows() and hasattr(os, "getuid"):
        cmd += ["-u", f"{os.getuid()}:{os.getgid()}"]
    return cmd + [image, "sh", "-c", script]


def build(root: Path, backend: str | None = None, config: str | None = None, extra: list[str] | None = None, fresh: bool = False,
          max_errors: int = 10, target: str | None = None, build_dir: str | None = None, jobs: int | None = None,
          timeout_min: float | None = None, _retrying: bool = False) -> dict:
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
    running = out / ".vita-build-running"
    notes = recover(root, out, running)
    running.write_text(f"{os.getpid()}\n", encoding="utf-8")
    njobs, jobs_why = job_count(cfg, jobs)
    timeout, stall = build_limits(cfg, timeout_min)
    status: dict = {}
    logp = out / "vita-build.log"
    print(f"vita build: {backend}, {jobs_why}", file=sys.stderr, flush=True)
    gen = b.get("generator") or ""
    opts = list(b.get("options", [])) + [f"-D{x}" if not x.startswith("-D") else x for x in (extra or [])]
    t0 = time.time()
    with open(logp, "w", encoding="utf-8", newline="\n") as log:
        if backend == "native":
            sdk = vitasdk_dir()
            env_tc = str(sdk / "share" / "vita.toolchain.cmake")  # type: ignore[operator]
            configure = ["cmake", "-S", str(root / src_rel), "-B", str(out), f"-DCMAKE_TOOLCHAIN_FILE={env_tc}", f"-DCMAKE_BUILD_TYPE={config}",
                         *(["-G", gen] if gen else []), *defines(root, cfg, root.as_posix()), *opts]
            rc = run_logged(configure, root, log, timeout, stall, status)
            stage = "configure"
            if rc == 0:
                stage = "build"
                rc = run_logged(["cmake", "--build", str(out), "--parallel", str(njobs), *(["--target", target] if target else [])], root, log,
                                timeout, stall, status)
        else:
            q = lambda s: "'" + s.replace("'", "'\\''") + "'"
            conf = ["cmake", "-S", f"/src/{src_rel}", "-B", f"/src/{out_rel}", "-DCMAKE_TOOLCHAIN_FILE=$VITASDK/share/vita.toolchain.cmake",
                    f"-DCMAKE_BUILD_TYPE={config}", *(["-G", gen] if gen else []), *defines(root, cfg, "/src"), *opts]
            script = " ".join(c if c.startswith("-DCMAKE_TOOLCHAIN_FILE") else q(c) for c in conf)
            script += f" && echo '@@configured' && cmake --build /src/{out_rel} --parallel {njobs}" + (f" --target {q(target)}" if target else "")
            name = f"vita-build-{os.getpid()}-{int(t0)}"
            rc = run_logged(docker_cmd(root, image, script, name), root, log, timeout, stall, status, name)
            stage = "build" if "@@configured" in logp.read_text(encoding="utf-8", errors="replace") else "configure"
    running.unlink(missing_ok=True)
    text = logp.read_text(encoding="utf-8", errors="replace")
    if "-Winvalid-pch" in text or "not a PCH file" in text:
        gone = pch_files(out)
        for f in gone:
            f.unlink(missing_ok=True)
        notes.append(f"the compiler rejected a precompiled header (-Winvalid-pch: left corrupt by an interrupted build); deleted "
                     f"{len(gone)} PCH file(s), the next build regenerates them")
    if status.get("killed"):
        notes.insert(0, f"the build was killed: it {status['killed']}. With {njobs} jobs; if the machine was swapping, lower "
                        "--jobs / [build] jobs, else raise [build] timeout_min / stall_min (0 = off)")
    overlap = re.search(r"Cannot allocate (\d+) bytes for SCE data at end of segment \d+; segment \d+ overlaps", text)
    if rc and overlap and not any("VITAPORT_ELF_PAD" in x for x in (extra or [])) and not _retrying:
        # the code segment ends too close to the 64 KiB-aligned data segment for vita-elf-create's import tables:
        # pad .rodata (cmake/VitaPort.cmake) and build once more
        r = build(root, backend, config, [*(extra or []), "VITAPORT_ELF_PAD=4096"], False, max_errors, target, build_dir, jobs, timeout_min,
                  _retrying=True)
        r["notes"].insert(0, f"vita-elf-create couldn't fit {overlap.group(1)} bytes of import tables between the code and data segments "
                             "(code size happened to end just below a 64 KiB boundary); rebuilt with -D VITAPORT_ELF_PAD=4096 "
                             "(cmake/VitaPort.cmake). Keep that option in [build] options if it recurs.")
        return r
    errors, nerr, nwarn = parse_errors(text, max_errors)
    res: dict = dict(ok=rc == 0, backend=backend, stage=stage, exit_code=rc, config=config, seconds=round(time.time() - t0, 1),
                     errors=errors, error_count=nerr, warning_count=nwarn, log=rel(root, logp), vpk=None, elf=None, unresolved=[],
                     jobs=njobs, jobs_reason=jobs_why, killed=status.get("killed"), notes=notes)
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
    r = build(root, backend, a.config, a.define, a.fresh, a.max_errors, a.target, a.build_dir, a.jobs, a.timeout_min)
    if a.json:
        emit_json(r)
        return OK if r["ok"] else PROBLEM
    if r["exit_code"] == 0:
        print(f"build {'OK' if r['ok'] else 'FINISHED WITH PROBLEMS'} ({r['backend']}, {r['config']}, {r['jobs']} jobs, {r['seconds']} s, "
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
        print(f"{r['stage']} {'KILLED' if r['killed'] else 'FAILED'} ({r['backend']}, exit {r['exit_code']}, {r['error_count']} errors, "
              f"{r['seconds']} s). Full log: {r['log']}")
        for e in r["errors"]:
            loc = f"{e['file']}:{e['line']}" if e.get("line") else (e.get("file") or "")
            print(f"  {loc + ': ' if loc else ''}{e['message']}")
        if r["error_count"] > len(r["errors"]):
            print(f"  ... {r['error_count'] - len(r['errors'])} more in the log")
        if not r["errors"] and not r["killed"]:
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
    p.add_argument("-j", "--jobs", type=int, help="parallel compile jobs (default: [build] jobs, $CMAKE_BUILD_PARALLEL_LEVEL, "
                   "else min(CPUs, available GiB))")
    p.add_argument("--timeout-min", type=float, help=f"kill the build after this many minutes (default [build] timeout_min, {TIMEOUT_MIN}; 0 = off)")
    p.add_argument("--max-errors", type=int, default=10)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
