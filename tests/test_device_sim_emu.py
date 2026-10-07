"""vita deploy/launch/kill/logs/core against a fake vitacompanion (TCP command server, monkeypatched FTP), the UDP
log listener, vita sim's helpers and vita emu's skip when Vita3K is missing."""
from __future__ import annotations

import ftplib
import json
import socket
import threading
import time
import zipfile

import pytest
from conftest import make_vpk, vita

from vita_porter import device, emu, sim


class FakeCommands:
    """A vitacompanion command port: records lines, answers 'ok'."""

    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.lines: list[str] = []
        threading.Thread(target=self.serve, daemon=True).start()

    def serve(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            with c:
                data = c.recv(4096).decode()
                self.lines.append(data.strip())
                c.sendall(b"ok\n")


class FakeFTP:
    store: dict[str, bytes] = {}
    dirs: list[str] = []

    def __init__(self, *a, **k):
        pass

    def connect(self, host, port, timeout=None):
        self.host, self.port = host, port

    def login(self):
        pass

    def mkd(self, d):
        if d in FakeFTP.dirs:
            raise ftplib.error_perm("550 exists")
        FakeFTP.dirs.append(d)

    def storbinary(self, cmd, fh):
        FakeFTP.store[cmd.split(" ", 1)[1]] = fh.read()

    def retrbinary(self, cmd, cb):
        cb(FakeFTP.store[cmd.split(" ", 1)[1]])

    def nlst(self, path):
        return [k for k in FakeFTP.store if k.startswith(path)]

    def quit(self):
        pass


def cfg_for(port, tid="TEST00001"):
    return {"app": {"title_id": tid, "data_folder": "MyGame"}, "assets": {"out": "build-vita/assets", "vpk_dir": "assets"},
            "build": {"build_dir": "build-vita"}, "device": {"ip": "127.0.0.1", "cmd_port": port, "ftp_port": 1337, "log_port": 0}}


def test_launch_and_kill_send_vitacompanion_commands():
    srv = FakeCommands()
    dev = device.device(cfg_for(srv.port), None)
    assert device.send(dev, "launch TEST00001") == "ok"
    assert device.send(dev, "quit TEST00001") == "ok"
    assert srv.lines == ["launch TEST00001", "quit TEST00001"]


def test_deploy_dry_run_and_real(tmp_path, monkeypatch):
    (tmp_path / "build-vita").mkdir()
    make_vpk(tmp_path / "build-vita" / "game.vpk", tmp_path, extra={"assets/a.bin": b"1234"})
    (tmp_path / "build-vita" / "assets").mkdir()
    (tmp_path / "build-vita" / "assets" / "a.bin").write_bytes(b"1234")
    srv = FakeCommands()
    cfg = cfg_for(srv.port)
    dev = device.device(cfg, None)
    dry = device.deploy(tmp_path, cfg, dev, {"vpk"}, None, yes=False)
    assert dry["dry_run"] and srv.lines == []
    kinds = [s["kind"] for s in dry["plan"]]
    assert kinds[0] == "quit" and kinds[-1] == "command" and dry["plan"][-1]["command"] == "promote ux0:data/vita-porter/TEST00001"
    assert any(s.get("dst") == "ux0:data/vita-porter/TEST00001/eboot.bin" for s in dry["plan"])
    monkeypatch.setattr(device.ftplib, "FTP", FakeFTP)
    FakeFTP.store.clear()
    real = device.deploy(tmp_path, cfg, dev, {"eboot", "assets"}, None, yes=True)
    assert real["ok"] and real["uploaded"] == 2
    assert FakeFTP.store["/ux0:/app/TEST00001/eboot.bin"][:4] == b"SCE\0"
    assert FakeFTP.store["/ux0:/data/MyGame/assets/a.bin"] == b"1234"
    assert srv.lines == ["quit TEST00001"]


def test_deploy_needs_something_and_an_ip(tmp_path):
    (tmp_path / "vita.toml").write_text('[app]\ntitle_id = "TEST00001"\n')
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path)
    r = vita("deploy", cwd=tmp_path)
    assert r.returncode == 2 and "Vita IP" in r.stderr
    r = vita("deploy", "--ip", "127.0.0.1", cwd=tmp_path)
    assert r.returncode == 2 and "say what to deploy" in r.stderr


def test_udp_logs(tmp_path):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    def sender():
        time.sleep(0.4)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as c:
            c.sendto(b"vitaport: hello\n", ("127.0.0.1", port))
            c.sendto(b"lumen-drift: started\n", ("127.0.0.1", port))
    threading.Thread(target=sender, daemon=True).start()
    r = device.logs(tmp_path, cfg_for(1), {"ip": "127.0.0.1", "log_port": port}, 1.5, port, False)
    assert r["lines"] == 2 and r["tail"] == ["vitaport: hello", "lumen-drift: started"]
    assert (tmp_path / r["file"]).read_text().count("\n") == 2


def test_core_with_a_local_dump_and_no_parser(tmp_path, monkeypatch):
    monkeypatch.delenv("VITA_PARSE_CORE", raising=False)
    (tmp_path / "x.psp2dmp").write_bytes(b"\x1f\x8b" + b"\0" * 10)
    elf = tmp_path / "game.elf"
    elf.write_bytes(b"\x7fELF")
    r = device.core(tmp_path, {"build": {"build_dir": "build-vita"}}, None, str(tmp_path / "x.psp2dmp"), str(elf))
    assert r["ok"] and r["found"] and "vita-parse-core isn't configured" in r["note"]


def test_sim_mirror_and_exe(tmp_path):
    src = tmp_path / "a"
    (src / "d").mkdir(parents=True)
    (src / "d" / "x.txt").write_text("1")
    dst = tmp_path / "b"
    assert sim.mirror(src, dst) == 1 and (dst / "d" / "x.txt").read_text() == "1"
    assert sim.mirror(src, dst) == 0
    (dst / "stale.txt").write_text("gone")
    sim.mirror(src, dst)
    assert not (dst / "stale.txt").exists()
    with pytest.raises(SystemExit):
        sim.find_exe(tmp_path, {"sim": {"exe": "nope/bin/game"}}, None)


def test_sim_without_vita_toml_is_a_usage_error(repo):
    r = vita("sim", cwd=repo)
    assert r.returncode == 2 and "vita init" in r.stderr


def test_emu_skips_without_vita3k(tmp_path, monkeypatch):
    monkeypatch.setattr(emu, "find_vita3k", lambda cfg: None)
    r = emu.emu(tmp_path, {}, None, 5, False, None, False, None, [])
    assert r["ok"] and r["skipped"] and "optional" in r["reason"]


def test_emu_runs_a_fake_vita3k(tmp_path, monkeypatch):
    import os
    import sys
    if os.name == "nt":
        pytest.skip("shell-script fake")
    fake = tmp_path / "Vita3K"
    fake.write_text(f"#!{sys.executable}\nimport sys\nprint('Installation succeeded', sys.argv[1:])\n")
    fake.chmod(0o755)
    (tmp_path / "build-vita").mkdir()
    make_vpk(tmp_path / "build-vita" / "g.vpk", tmp_path)
    monkeypatch.setattr(emu, "find_vita3k", lambda cfg: str(fake))
    r = emu.emu(tmp_path, {"app": {"title_id": "TEST00001"}}, None, 10, False, None, False, "vulkan", [])
    assert r["exit_code"] == 0 and r["markers"]["Installation succeeded"]
    assert any("g.vpk" in a for a in r["cmd"]) and r["cmd"][-2:] == ["-B", "Vulkan"]
    r2 = emu.emu(tmp_path, {"app": {"title_id": "TEST00001"}}, None, 10, False, None, True, None, [])
    assert r2["cmd"][1:] == ["-r", "TEST00001"]
    assert zipfile.is_zipfile(tmp_path / "build-vita" / "g.vpk")
    assert json.loads(json.dumps(r2, default=str))
