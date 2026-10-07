"""Repository checks: layout, manifests, skill copies in sync, help screens, PATH hook, the `vita` name.
The skill-copy and PATH-hook tests are derived from universal-modder's tests/test_um.py
(MIT, Copyright (c) 2026 Rehan and universal-modder contributors), via universal-decompiler."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

import pytest
from conftest import ROOT, vita

from vita_porter.cli import GROUPS

LAYOUT = ["AGENTS.md", "CLAUDE.md", "GEMINI.md", "README.md", "CONTRIBUTING.md", "LICENSE", "NOTICE", "DEVLOG.md", "pyproject.toml",
          "bin/vita", "bin/vita.cmd", "hooks/hooks.json", "hooks/add-to-path.sh", ".claude-plugin/plugin.json",
          ".claude-plugin/marketplace.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", ".cursor-plugin/marketplace.json",
          ".agents/plugins/marketplace.json", "gemini-extension.json", "opencode.json", "plugin.json", "knowledge/INDEX.md",
          "knowledge/index.json", "knowledge/TEMPLATE.md", "knowledge/README.md", "examples/lumen-drift/README.md",
          "examples/lumen-drift/PORT_PLAN.md", "examples/lumen-drift/PORTLOG.md", "examples/lumen-drift/vita.toml",
          ".github/workflows/test.yml", "vita_porter/tools.toml", "vita_porter/deps.toml", "scripts/sync_skills.py"]
SKILLS = ["port-to-vita", "vita-recon", "vita-controls-ui", "vita-graphics", "vita-packaging", "vita-testing", "share-field-notes"]
REFERENCES = ["hardware.md", "livearea.md", "vitagl.md", "memory.md", "controls.md", "scaling.md", "audio.md", "filesystem.md",
              "unsafe.md", "testing.md", "safety.md"]
# VitaSDK 2026.08's $VITASDK/bin (DEVLOG.md): `vita` must not be one of them
VITASDK_BINARIES = ["arm-vita-eabi-gcc", "arm-vita-eabi-g++", "arm-vita-eabi-nm", "psp2rela", "vdpm", "vdpm-channel", "vita-elf-create",
                    "vita-elf-export", "vita-libs-gen", "vita-libs-gen-2", "vita-make-fself", "vita-makepkg", "vita-mksfoex",
                    "vita-nid-check", "vita-pack-vpk"]


def test_layout():
    missing = [p for p in LAYOUT if not (ROOT / p).exists()]
    assert not missing, missing
    assert not (ROOT / "src").exists(), "the package lives in vita_porter/, not src/"
    assert not any((ROOT / f).exists() for f in (".mcp.json", ".cursor/mcp.json", ".vscode/mcp.json", ".codex/config.toml")), \
        "no MCP server of our own: no MCP config in this repo"


def test_skill_copies_match():
    # .agents/skills and .claude/skills are real copies of skills/ (Windows clones turn symlinks into text files)
    def tree(d):
        return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}
    src = tree(ROOT / "skills")
    for copy in (".agents/skills", ".claude/skills"):
        assert not (ROOT / copy).is_symlink(), f"{copy} must be a folder, not a symlink"
        assert tree(ROOT / copy) == src, f"{copy} differs from skills/: python scripts/sync_skills.py"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "sync_skills.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_skills_have_frontmatter_and_structure():
    for name in SKILLS:
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        m = re.match(r"^---\nname: (.+)\ndescription: (.+?)\n---\n", text, re.S)
        assert m and m.group(1) == name and len(m.group(2)) > 100, name
    main = (ROOT / "skills" / "port-to-vita" / "SKILL.md").read_text(encoding="utf-8")
    for heading in ("## Your tools", "## The loop", "## Autonomy", "## Hard rules", "## References"):
        assert heading in main, heading
    for step in range(10):
        assert re.search(rf"^### {step}\. ", main, re.M), f"loop step {step}"
    for ref in REFERENCES:
        p = ROOT / "skills" / "port-to-vita" / "references" / ref
        assert p.exists() and len(p.read_text(encoding="utf-8")) > 800, ref
        assert f"`{ref}`" in main, f"{ref} not listed in References"
    for phrase in ("Never stop to ask the user to test a vertical slice", "Circuit breaker", "PORTLOG.md", "libshacccg.suprx"):
        assert phrase in main, phrase


def test_livearea_reference_records_the_ya8_fix():
    t = (ROOT / "skills" / "port-to-vita" / "references" / "livearea.md").read_text(encoding="utf-8")
    assert "ya8" in t and "rgb24" in t and "0x8010113D" in t and "grayscale" in t


def test_recon_documents_the_intake_logic():
    t = (ROOT / "skills" / "vita-recon" / "SKILL.md").read_text(encoding="utf-8")
    for topic in ("### Controls", "### In-game UI", "### Resolution and scaling", "### Textures and memory", "### Assets",
                  "### Frame rate", "### App identity", "Recommendation logic", "off"):
        assert topic in t, topic


def test_manifests():
    names = set()
    for f in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "gemini-extension.json", "plugin.json"):
        data = json.loads((ROOT / f).read_text(encoding="utf-8"))
        names.add(data["name"])
        assert "mcpServers" not in data, f"{f}: no MCP server of our own"
    assert names == {"ps-vita-porter"}
    assert json.loads((ROOT / ".codex-plugin/plugin.json").read_text())["skills"] == "./skills/"
    assert json.loads((ROOT / "opencode.json").read_text())["skills"]["paths"] == ["skills"]
    assert json.loads((ROOT / "gemini-extension.json").read_text())["contextFileName"] == "AGENTS.md"
    for f in (".claude-plugin/marketplace.json", ".cursor-plugin/marketplace.json"):
        assert json.loads((ROOT / f).read_text())["plugins"][0]["source"] == "./"
    hooks = json.loads((ROOT / "hooks/hooks.json").read_text())
    assert list(hooks["hooks"]) == ["SessionStart"], "SessionStart only: no Stop hook"
    assert "add-to-path.sh" in hooks["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "add-to-path.sh" in (ROOT / ".claude/settings.json").read_text()
    for f in ("CLAUDE.md", "GEMINI.md"):
        assert (ROOT / f).read_text().startswith("@AGENTS.md")


def test_pyproject():
    import tomllib
    p = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert p["project"]["name"] == "ps-vita-porter" and p["project"]["scripts"]["vita"] == "vita_porter.cli:main"
    assert p["project"]["requires-python"] == ">=3.12" and p["project"]["license"] == "MIT"


def test_readme_and_notice_state_origin():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Inspired by universal-modder. Not affiliated with its authors." in readme
    assert "universal-decompiler" in readme and "never decompiles" in readme
    for prereq in ("VitaSDK", "Docker", "Vita3K", "libshacccg.suprx", "vitacompanion"):
        assert prereq in readme, prereq
    assert "uv tool install git+https://github.com/hammerill/ps-vita-porter" in readme
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "Not affiliated with its authors." in notice and "Copyright (c) 2026 Rehan and universal-modder contributors" in notice
    code_section = notice.split("Code (", 1)[1].split("Structure and text", 1)[0]
    listed = re.findall(r"^- ((?:vita_porter|bin|hooks|tests)/[\w./-]+)", code_section, re.M)
    assert len(listed) >= 6
    for f in listed:
        path = ROOT / f
        assert path.exists(), f
        assert "universal-modder" in path.read_text(encoding="utf-8")[:2500], f"{f} must carry the universal-modder notice"
    assert "MIT License" in (ROOT / "LICENSE").read_text()


def test_vita_name_does_not_clash_with_vitasdk():
    assert "vita" not in VITASDK_BINARIES
    sdk = os.environ.get("VITASDK")
    if sdk and os.path.isdir(os.path.join(sdk, "bin")):
        assert not os.path.exists(os.path.join(sdk, "bin", "vita")), "VitaSDK ships a `vita` binary now: rename the CLI"
    assert "No binary is named `vita`" in (ROOT / "DEVLOG.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("group", GROUPS)
def test_help_screens_have_examples(group):
    r = vita(group, "--help")
    assert r.returncode == 0, r.stderr
    assert re.search(rf"^\s+vita {group}\b", r.stdout, re.M), f"`vita {group} --help` shows no examples"


def test_group_without_command_is_usage_error():
    for g in ("tools", "livearea", "vpk", "assets", "publish", "kb"):
        assert vita(g).returncode == 2, g


def test_spec_commands_exist():
    cmds = {"init": [], "scan": [], "tools": ["check", "list", "show"], "build": [], "livearea": ["make", "check"], "vpk": ["check"],
            "assets": ["convert", "check"], "sim": [], "emu": [], "deploy": [], "launch": [], "kill": [], "logs": [], "core": [],
            "publish": ["check"], "kb": ["search", "show", "new", "check", "index", "sync", "pr"]}
    assert set(cmds) == set(GROUPS)
    for g, subs in cmds.items():
        for s in subs or [None]:
            args = [g, s, "--help"] if s else [g, "--help"]
            assert vita(*args).returncode == 0, f"vita {g} {s or ''}"


def test_reporting_commands_take_json():
    for args in (["init"], ["scan"], ["tools", "check"], ["build"], ["livearea", "make"], ["livearea", "check"], ["vpk", "check"],
                 ["assets", "convert"], ["assets", "check"], ["sim"], ["emu"], ["deploy"], ["launch"], ["kill"], ["logs"], ["core"],
                 ["publish", "check"], ["kb", "search"], ["kb", "check"], ["kb", "index"], ["kb", "new"]):
        assert "--json" in vita(*args, "--help").stdout, " ".join(args)


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="bash hook; the Windows variant needs Git Bash's cygpath")
def test_path_hook_appends_once(tmp_path):
    env_file = tmp_path / "env.sh"
    env = {**os.environ, "CLAUDE_ENV_FILE": str(env_file)}
    hook = ROOT / "hooks" / "add-to-path.sh"
    for _ in range(2):
        subprocess.run(["bash", str(hook), str(ROOT)], env=env, check=True)
    text = env_file.read_text()
    assert text.count("ps-vita-porter-path") == 1 and f'{ROOT}/bin:$PATH' in text


def test_no_packages_or_binaries_in_repo():
    r = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    files = r.stdout.split() if r.returncode == 0 else []
    bad = [f for f in files if re.search(r"\.(vpk|self|velf|psp2dmp|exe|dll|so|dylib|elf|iso)$|(^|/)eboot\.bin$", f, re.I)]
    assert not bad, bad
