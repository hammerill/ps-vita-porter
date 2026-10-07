"""vita init (idempotent, ud detection, kit) and vita publish check."""
from __future__ import annotations

import json
import tomllib

from conftest import ROOT, git, make, vita

from vita_porter import init as vinit


def test_init_is_idempotent(repo):
    r1 = vita("init", "--json", cwd=repo)
    assert r1.returncode == 0, r1.stderr
    j1 = json.loads(r1.stdout)
    assert j1["kind"] == "cmake"
    for f in ("vita.toml", "PORT_PLAN.md", "PORTLOG.md", ".gitignore"):
        assert j1["changes"][f] == "created", f
    cfg = tomllib.loads((repo / "vita.toml").read_text())
    assert cfg["app"]["assets"] == "embedded" and cfg["app"]["unsafe"] is False
    gi = (repo / ".gitignore").read_text()
    assert "build-vita/" in gi and "*.vpk" in gi
    hook = repo / ".git" / "hooks" / "pre-push"
    assert hook.exists() and "vita publish check" in hook.read_text() or "publish check" in hook.read_text()
    before = {p: (repo / p).read_bytes() for p in ("vita.toml", "PORT_PLAN.md", "PORTLOG.md", ".gitignore", ".git/hooks/pre-push")}
    j2 = json.loads(vita("init", "--json", cwd=repo).stdout)
    assert all(v in ("kept", "unchanged") for v in j2["changes"].values()), j2["changes"]
    assert before == {p: (repo / p).read_bytes() for p in before}
    assert (repo / ".gitignore").read_text().count("# >>> ps-vita-porter") == 1


def test_init_detects_ud_and_chains_its_hook(repo):
    make(repo, {"ud.toml": "[project]\nname='x'\n", "DECOMP_PLAN.md": "# plan\n", "decomp/progress.json": "{}", "src/platform/platform.h": "",
                ".gitignore": "data/\nbuild/\n"})
    hooks = repo / ".git" / "hooks"
    (hooks / "pre-push").write_text("#!/bin/sh\n# universal-decompiler pre-push guard\nexit 0\n")
    j = json.loads(vita("init", "--json", "--title-id", "ABCD12345", "--name", "Foo", cwd=repo).stdout)
    assert j["kind"] == "ud" and j["ud"]["platform_layer"] == "src/platform"
    assert "pre-push.local" in j["changes"]["pre-push hook"]
    assert (hooks / "pre-push.local").read_text().startswith("#!/bin/sh\n# universal-decompiler")
    cfg = tomllib.loads((repo / "vita.toml").read_text())
    assert cfg["app"]["assets"] == "external" and cfg["app"]["title_id"] == "ABCD12345" and cfg["assets"]["source"] == "data"
    gi = (repo / ".gitignore").read_text()
    assert gi.startswith("data/\nbuild/\n") and "build-vita/" in gi


def test_init_kit_and_no_hook(repo):
    j = json.loads(vita("init", "--kit", "--no-hook", "--json", cwd=repo).stdout)
    assert (repo / "cmake" / "VitaPort.cmake").exists() and (repo / "platform" / "vita" / "vitaport" / "vitaport.h").exists()
    assert j["changes"]["pre-push hook"].startswith("skipped")
    assert not (repo / ".git" / "hooks" / "pre-push").exists()
    (repo / "platform" / "vita" / "vitaport" / "vitaport.h").write_text("// mine\n")
    j2 = json.loads(vita("init", "--kit", "--no-hook", "--json", cwd=repo).stdout)
    assert "yours wins" in j2["changes"]["platform/vita/vitaport/vitaport.h"]
    assert (repo / "platform" / "vita" / "vitaport" / "vitaport.h").read_text() == "// mine\n"


def test_title_id_suggestions():
    for name in ("lumen-drift", "PCS game", "x", "", "Sonic & Knuckles", "vsdk demo"):
        tid = vinit.suggest_title_id(name)
        from vita_porter.common import title_id_problems
        assert not title_id_problems(tid), (name, tid)


def test_init_bad_title_id_is_a_problem(repo):
    r = vita("init", "--title-id", "PCSE00001", cwd=repo)
    assert r.returncode == 1 and "reserved prefix" in r.stdout


def commit_all(repo, msg="c"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", msg)


def test_publish_clean_repo(repo):
    vita("init", "--no-hook", cwd=repo)
    make(repo, {"src/main.cpp": "int main(){}\n", "assets/own.png": b"\x89PNG" + b"\0" * 100})
    commit_all(repo)
    r = vita("publish", "check", "--json", cwd=repo)
    assert r.returncode == 0, r.stdout
    assert json.loads(r.stdout)["ok"]


def test_publish_blocks_packages_and_converted_assets(repo):
    vita("init", "--no-hook", cwd=repo)
    make(repo, {"game.vpk": b"PK\x03\x04" + b"\0" * 64, "out/eboot.bin": b"SCE\0" + b"\0" * 64,
                "build-vita/assets/atlas.dds": b"DDS " + b"\0" * 64})
    git(repo, "add", "-f", "game.vpk", "out/eboot.bin", "build-vita/assets/atlas.dds")
    git(repo, "commit", "-q", "-m", "oops")
    git(repo, "rm", "-q", "--cached", "game.vpk")
    git(repo, "commit", "-q", "-m", "untrack")
    j = json.loads(vita("publish", "check", "--json", cwd=repo).stdout)
    f = " | ".join(j["fails"])
    assert not j["ok"]
    assert "game.vpk: a .vpk package (in history" in f
    assert "out/eboot.bin" in f and "build-vita/assets/atlas.dds" in f


def test_publish_in_a_ud_repo(repo):
    make(repo, {"ud.toml": "[project]\nname='x'\n", "DECOMP_PLAN.md": "", "decomp/progress.json": "{}",
                "data/game.exe": b"MZ" + bytes(range(256)) * 4, "data/tex/wall.png": b"\x89PNG" + bytes(range(200)) * 3})
    vita("init", "--no-hook", cwd=repo)
    make(repo, {"src/copy_of_wall.png": (repo / "data" / "tex" / "wall.png").read_bytes(), "tools/game.exe": b"MZ" + b"x" * 300})
    git(repo, "add", "-A")
    git(repo, "add", "-f", "data/game.exe")
    git(repo, "commit", "-q", "-m", "c")
    j = json.loads(vita("publish", "check", "--no-ud", "--json", cwd=repo).stdout)
    f = " | ".join(j["fails"])
    assert j["ud_repo"] and not j["ok"]
    assert "data/game.exe" in f and "byte-identical to data/tex/wall.png" in f and "tools/game.exe" in f


def test_publish_allow_list_and_secrets(repo):
    vita("init", "--no-hook", cwd=repo)
    t = (repo / "vita.toml").read_text().replace('allow = []', 'allow = ["docs/*.vpk"]')
    (repo / "vita.toml").write_text(t)
    make(repo, {"docs/sample.vpk": b"PK" + b"\0" * 10, "notes.md": "key: sk-ant-" + "a" * 30 + "\n"})
    git(repo, "add", "-f", "-A")
    git(repo, "commit", "-q", "-m", "c")
    j = json.loads(vita("publish", "check", "--json", cwd=repo).stdout)
    assert not any("docs/sample.vpk" in x for x in j["fails"])
    assert any("notes.md: Anthropic key" in x for x in j["fails"])


def test_the_toolkit_repo_itself_passes(monkeypatch):
    r = vita("publish", "check", "--json", cwd=ROOT, env={"VITA_PUBLISH_OFFLINE": "1"})
    j = json.loads(r.stdout)
    assert j["ok"], j["fails"]
