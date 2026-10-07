"""Real hardware, through vitacompanion (FTP on 1337, commands on 1338). Only once the user says a Vita is connected:
the Vita's IP comes from vita.toml [device] ip or --ip. Deploying needs the user's permission (--yes).

    vita deploy --vpk --yes            # upload the unpacked .vpk to ux0:data/vita-porter/<TITLEID>/ and install it (promote);
                                       # without promote (releases up to 1.07): copy the .vpk to ux0: for VitaShell
    vita deploy --eboot --yes          # fast iteration: quit the app, replace ux0:app/<TITLEID>/eboot.bin
    vita deploy --assets --yes         # external assets: build-vita/assets -> ux0:data/<data_folder>/<vpk_dir>/
    vita deploy --eboot                # dry run: what would be uploaded, nothing sent
    vita launch                        # launch <TITLEID>
    vita kill                          # quit <TITLEID>
    vita logs --timeout 120            # receive the app's UDP network log (build with -D VITA_LOG_HOST=<this PC's IP>)
    vita logs --ftp                    # fetch ux0:data/<data_folder>/vitaport.log instead
    vita core                          # fetch the newest ux0:data/*.psp2dmp, parse it with vita-parse-core + the ELF
    vita core --file crash.psp2dmp --json

vitacompanion commands (devnoname120/vitacompanion README, 2026-10-07): launch <TITLEID>, quit <TITLEID>|all,
reboot, screen on|off, promote <dir> (installs an *extracted* app folder; it does not take a .vpk), separated by
';'. promote is only in the development tree: release 1.07 (2026-09-16) answers "Error: Unknown command." and
doesn't list it in `help`, so `deploy --vpk` asks `help` first and, without promote, uploads the .vpk itself to
ux0:<name>.vpk for the user to install with VitaShell. Network logs: vitaport.h sends each vp_log line as a UDP datagram to VP_LOG_HOST:VP_LOG_PORT (default 18194).
Crash dumps: the Vita writes ux0:data/*.psp2dmp when an app crashes; vita-parse-core (Python 2) needs the
unstripped ELF from the build. Nothing on the console is ever deleted by these commands.
"""
from __future__ import annotations

import datetime as dt
import ftplib
import io
import os
import socket
import subprocess
import time
import zipfile
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, load_config, project_root, rel, usage

STAGE = "ux0:data/vita-porter"


def device(cfg: dict, ip: str | None) -> dict:
    d = dict(cfg.get("device", {}))
    d["ip"] = ip or d.get("ip")
    if not d["ip"]:
        usage("no Vita IP: set [device] ip in vita.toml (only once the user says the console is connected) or pass --ip")
    d.setdefault("ftp_port", 1337)
    d.setdefault("cmd_port", 1338)
    d.setdefault("log_port", 18194)
    return d


def send(dev: dict, command: str, timeout: float = 5.0) -> str:
    """Send one vitacompanion command line; return whatever it answers within the timeout."""
    with socket.create_connection((dev["ip"], int(dev["cmd_port"])), timeout=timeout) as s:
        s.sendall((command.strip() + "\n").encode())
        s.settimeout(1.5)
        chunks = []
        try:
            while True:
                b = s.recv(4096)
                if not b:
                    break
                chunks.append(b)
        except (TimeoutError, socket.timeout):
            pass
    return b"".join(chunks).decode(errors="replace").strip()


def ftp_connect(dev: dict) -> ftplib.FTP:
    f = ftplib.FTP()
    f.connect(dev["ip"], int(dev["ftp_port"]), timeout=20)
    f.login()
    return f


def ftp_path(vita_path: str) -> str:
    """ux0:data/x -> /ux0:/data/x (vitacompanion accepts Vita-style paths under the drive)."""
    drive, _, rest = vita_path.partition(":")
    return f"/{drive}:/{rest.lstrip('/')}"


def ftp_mkdirs(f: ftplib.FTP, vita_dir: str):
    drive, _, rest = vita_dir.partition(":")
    cur = f"/{drive}:"
    for part in [p for p in rest.split("/") if p]:
        cur += "/" + part
        try:
            f.mkd(cur)
        except ftplib.error_perm:
            pass   # exists


def ftp_put(f: ftplib.FTP, data: bytes, vita_file: str):
    drive, _, rest = vita_file.partition(":")
    if "/" in rest.strip("/"):   # a file at the drive root (ux0:x.vpk) needs no folders
        ftp_mkdirs(f, f"{drive}:{rest.strip('/').rsplit('/', 1)[0]}")
    f.storbinary(f"STOR {ftp_path(vita_file)}", io.BytesIO(data))


def find_vpk(root: Path, cfg: dict, override: str | None) -> Path:
    from vita_porter.emu import pick_vpk
    return pick_vpk(root, cfg, override)


def has_promote(dev: dict) -> bool:
    """Whether this vitacompanion knows `promote`: its `help` lists one command per line."""
    return any(ln.split()[:1] == ["promote"] for ln in send(dev, "help").splitlines())


def plan_deploy(root: Path, cfg: dict, what: set[str], vpk: str | None, promote: bool = True) -> list[dict]:
    app, a = cfg.get("app", {}), cfg.get("assets", {})
    tid = app.get("title_id")
    if not tid:
        usage("[app] title_id is missing in vita.toml")
    steps: list[dict] = []
    if "vpk" in what or "eboot" in what:
        p = find_vpk(root, cfg, vpk)
        if "vpk" in what and not promote:
            # no promote (vitacompanion releases up to 1.07): copy the .vpk itself for VitaShell to install
            steps.append(dict(kind="file", src=rel(root, p), dst=f"ux0:{p.name}", size=p.stat().st_size))
            what = what - {"vpk"}
        else:
            steps.append(dict(kind="quit", command=f"quit {tid}"))
    if "vpk" in what or "eboot" in what:
        with zipfile.ZipFile(p) as z:
            if "vpk" in what:
                for n in z.namelist():
                    if not n.endswith("/"):
                        steps.append(dict(kind="file", src=f"{rel(root, p)}!{n}", dst=f"{STAGE}/{tid}/{n}", size=z.getinfo(n).file_size))
                steps.append(dict(kind="command", command=f"promote {STAGE}/{tid}"))
            else:
                steps.append(dict(kind="file", src=f"{rel(root, p)}!eboot.bin", dst=f"ux0:app/{tid}/eboot.bin", size=z.getinfo("eboot.bin").file_size))
    if "assets" in what:
        out = root / (a.get("out") or "build-vita/assets")
        if not out.is_dir():
            usage(f"{rel(root, out)} doesn't exist: run `vita assets convert` first")
        base = f"ux0:data/{app.get('data_folder', 'game')}/{a.get('vpk_dir', 'assets')}"
        for p in sorted(out.rglob("*")):
            if p.is_file():
                steps.append(dict(kind="file", src=rel(root, p), dst=f"{base}/{p.relative_to(out).as_posix()}", size=p.stat().st_size))
    return steps


def read_src(root: Path, src: str) -> bytes:
    if "!" in src:
        z, member = src.split("!", 1)
        with zipfile.ZipFile(root / z) as zf:
            return zf.read(member)
    return (root / src).read_bytes()


def deploy(root: Path, cfg: dict, dev: dict, what: set[str], vpk: str | None, yes: bool) -> dict:
    promote = not (yes and "vpk" in what) or has_promote(dev)
    steps = plan_deploy(root, cfg, what, vpk, promote)
    total = sum(s.get("size", 0) for s in steps)
    res = dict(ip=dev["ip"], steps=len(steps), bytes=total, dry_run=not yes, plan=steps[:50])
    if "vpk" in what:
        res["promote"] = promote
        if promote:
            res["note"] = "a vitacompanion without `promote` (releases up to 1.07) gets the .vpk copied to ux0: instead"
        else:
            res["note"] = (f"this vitacompanion has no `promote`: {steps[0]['dst']} was copied as is; the user installs "
                           "it with VitaShell (ux0:, select the .vpk, Cross, install)")
    if not yes:
        res["ok"] = True
        return res
    done, answers = 0, []
    f = None
    try:
        for s in steps:
            if s["kind"] in ("quit", "command"):
                answers.append(dict(command=s["command"], answer=send(dev, s["command"])))
                if s["kind"] == "quit":
                    time.sleep(1.0)
                continue
            if f is None:
                f = ftp_connect(dev)
            ftp_put(f, read_src(root, s["src"]), s["dst"])
            done += 1
    except (OSError, ftplib.Error) as e:
        res.update(ok=False, error=f"{e.__class__.__name__}: {e}", uploaded=done, answers=answers)
        return res
    finally:
        if f is not None:
            try:
                f.quit()
            except (OSError, ftplib.Error):
                pass
    res.update(ok=True, uploaded=done, answers=answers)
    return res


def logs(root: Path, cfg: dict, dev: dict, timeout: float, port: int | None, via_ftp: bool) -> dict:
    out = root / cfg.get("build", {}).get("build_dir", "build-vita") / "logs"
    out.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if via_ftp:
        folder = cfg.get("app", {}).get("data_folder", "game")
        f = ftp_connect(dev)
        buf = io.BytesIO()
        try:
            f.retrbinary(f"RETR {ftp_path(f'ux0:data/{folder}/vitaport.log')}", buf.write)
        finally:
            f.quit()
        dst = out / f"vitaport-{stamp}.log"
        dst.write_bytes(buf.getvalue())
        lines = buf.getvalue().decode(errors="replace").splitlines()
        return dict(ok=True, file=rel(root, dst), lines=len(lines), tail=lines[-40:])
    port = port or int(dev["log_port"])
    dst = out / f"udp-{stamp}.log"
    lines: list[str] = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s, open(dst, "w", encoding="utf-8") as fh:
        s.bind(("0.0.0.0", port))
        s.settimeout(0.5)
        end = time.time() + timeout
        print(f"listening for the app's log on UDP {port} for {timeout:g} s (Ctrl-C stops) -> {rel(root, dst)}", flush=True)
        try:
            while time.time() < end:
                try:
                    data, addr = s.recvfrom(65536)
                except (TimeoutError, socket.timeout):
                    continue
                if addr[0] != dev["ip"] and dev.get("ip_strict", False):
                    continue
                for ln in data.decode(errors="replace").splitlines():
                    lines.append(ln)
                    fh.write(ln + "\n")
                    fh.flush()
                    print(ln, flush=True)
        except KeyboardInterrupt:
            pass
    return dict(ok=True, file=rel(root, dst), port=port, lines=len(lines), tail=lines[-40:])


def core(root: Path, cfg: dict, dev: dict | None, local: str | None, elf: str | None) -> dict:
    out = root / cfg.get("build", {}).get("build_dir", "build-vita") / "cores"
    out.mkdir(parents=True, exist_ok=True)
    if local:
        dump = Path(local)
        if not dump.exists():
            usage(f"no such file: {local}")
    else:
        assert dev is not None
        f = ftp_connect(dev)
        try:
            names = [n for n in f.nlst(ftp_path("ux0:data")) if n.lower().endswith(".psp2dmp")]
            if not names:
                return dict(ok=True, found=False, note="no ux0:data/*.psp2dmp on the console: no crash recorded")
            name = sorted(names)[-1]
            buf = io.BytesIO()
            f.retrbinary(f"RETR {name if name.startswith('/') else ftp_path('ux0:data/' + name.rsplit('/', 1)[-1])}", buf.write)
        finally:
            f.quit()
        dump = out / name.rsplit("/", 1)[-1]
        dump.write_bytes(buf.getvalue())
    res: dict = dict(ok=True, found=True, dump=rel(root, dump))
    from vita_porter.build import find_outputs
    elf_path = Path(elf) if elf else find_outputs(root / cfg.get("build", {}).get("build_dir", "build-vita"), cfg, root, 0)[1]
    parser = os.environ.get("VITA_PARSE_CORE")
    py2 = next((p for p in ("python2", "python2.7") if subprocess.run(["which", p], capture_output=True).returncode == 0), None) \
        if os.name != "nt" else "python2"
    if not elf_path or not Path(elf_path).exists():
        res["note"] = "no unstripped ELF found (set [build] elf or pass --elf): the dump can't be symbolised"
        return res
    res["elf"] = rel(root, Path(elf_path))
    main_py = Path(parser) / "main.py" if parser and Path(parser).is_dir() else Path(parser) if parser else None
    if not main_py or not main_py.exists() or not py2:
        res["note"] = ("vita-parse-core isn't configured (set VITA_PARSE_CORE to its folder; it needs python2): "
                       f"run `python2 main.py {res['dump']} {res['elf']}` by hand, see `vita tools show vita-parse-core`")
        return res
    r = subprocess.run([py2, str(main_py), str(dump), str(elf_path)], capture_output=True, text=True, timeout=300)
    report = (r.stdout or "") + (r.stderr or "")
    (out / (dump.stem + ".txt")).write_text(report, encoding="utf-8")
    res.update(parsed=r.returncode == 0, report=rel(root, out / (dump.stem + ".txt")), tail=report.splitlines()[-60:])
    res["ok"] = r.returncode == 0
    return res


def main(a):
    root = project_root()
    cfg = load_config(root)
    cmd = a.group
    if cmd == "core" and a.file:
        r = core(root, cfg, None, a.file, a.elf)
    else:
        dev = device(cfg, a.ip)
        tid = cfg.get("app", {}).get("title_id")
        try:
            if cmd == "deploy":
                what = {k for k in ("vpk", "eboot", "assets") if getattr(a, k)}
                if not what:
                    usage("say what to deploy: --vpk (install), --eboot (replace the program), --assets (external assets)")
                if {"vpk", "eboot"} <= what:
                    usage("--vpk already contains eboot.bin; pick one")
                r = deploy(root, cfg, dev, what, a.vpk_file, a.yes)
            elif cmd in ("launch", "kill"):
                t = a.title_id or tid
                if not t:
                    usage("no title ID ([app] title_id or --title-id)")
                command = f"launch {t}" if cmd == "launch" else f"quit {t}"
                r = dict(ok=True, command=command, answer=send(dev, command))
            elif cmd == "logs":
                r = logs(root, cfg, dev, a.timeout, a.port, a.ftp)
            else:
                r = core(root, cfg, dev, None, a.elf)
        except (OSError, ftplib.Error) as e:
            r = dict(ok=False, error=f"{e.__class__.__name__}: {e}",
                     hint=f"is the Vita at {dev['ip']} awake, on the same network, with vitacompanion loaded? (`vita tools check`)")
    if a.json:
        emit_json(r)
        return OK if r.get("ok") else PROBLEM
    if r.get("error"):
        print(f"FAILED: {r['error']}")
        if r.get("hint"):
            print(f"  {r['hint']}")
        return PROBLEM
    if cmd == "deploy":
        if r["dry_run"]:
            print(f"dry run ({r['steps']} steps, {r['bytes'] / 1048576:.1f} MiB to {r['ip']}); add --yes once the user agreed to deploy:")
        for s in r["plan"]:
            print(f"  {s['kind']:7} {s.get('command') or s['src'] + ' -> ' + s['dst']}")
        if r["steps"] > len(r["plan"]):
            print(f"  ... {r['steps'] - len(r['plan'])} more")
        if r.get("note") and (r["dry_run"] or not r["promote"]):
            print(f"note: {r['note']}")
        if not r["dry_run"]:
            print(f"uploaded {r['uploaded']} file(s); command answers: " + "; ".join(f"{x['command']}: {x['answer'] or '(no answer)'}" for x in r["answers"]))
    elif cmd in ("launch", "kill"):
        print(f"{r['command']}: {r['answer'] or '(no answer)'}")
    elif cmd == "logs":
        print(f"{r['lines']} line(s) -> {r['file']}")
    else:
        if not r.get("found", True):
            print(r["note"])
        else:
            print(f"dump: {r['dump']}" + (f"  elf: {r['elf']}" if r.get("elf") else ""))
            for ln in r.get("tail", []):
                print(f"  {ln}")
            if r.get("note"):
                print(f"note: {r['note']}")
    return OK if r.get("ok") else PROBLEM


def register(sub):
    import argparse
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ip", help="the Vita's IP (default: [device] ip in vita.toml)")
    common.add_argument("--json", action="store_true")
    kw = dict(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, parents=[common])
    p = sub.add_parser("deploy", help="upload the .vpk / eboot.bin / external assets to the Vita (vitacompanion FTP)", **kw)
    p.add_argument("--vpk", action="store_true", help="install the whole .vpk (upload unpacked + promote; without promote, copy the .vpk to ux0:)")
    p.add_argument("--eboot", action="store_true", help="replace ux0:app/<TITLEID>/eboot.bin")
    p.add_argument("--assets", action="store_true", help="upload [assets] out to ux0:data/<data_folder>/<vpk_dir>/")
    p.add_argument("--vpk-file", help="the .vpk to use (default: [build] vpk, else the newest in the build folder)")
    p.add_argument("--yes", action="store_true", help="really upload (only after the user agreed)")
    p.set_defaults(func=main)
    for name, hlp in (("launch", "launch the app on the Vita"), ("kill", "quit the app on the Vita")):
        p = sub.add_parser(name, help=hlp, **kw)
        p.add_argument("--title-id", help="default: [app] title_id")
        p.set_defaults(func=main)
    p = sub.add_parser("logs", help="capture the app's network log (UDP) or fetch its log file (--ftp)", **kw)
    p.add_argument("--timeout", type=float, default=60.0, help="seconds to listen (default 60)")
    p.add_argument("--port", type=int, help="UDP port (default [device] log_port, 18194)")
    p.add_argument("--ftp", action="store_true", help="fetch ux0:data/<data_folder>/vitaport.log over FTP instead")
    p.set_defaults(func=main)
    p = sub.add_parser("core", help="fetch the newest crash dump and parse it with vita-parse-core", **kw)
    p.add_argument("--file", help="parse a local .psp2dmp instead of fetching one")
    p.add_argument("--elf", help="the unstripped ELF (default: from the build folder)")
    p.set_defaults(func=main)
