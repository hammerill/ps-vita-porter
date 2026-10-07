"""vita kb: the repo's own notes, new/check/search round trip, rejection of decompiled code and address tables.
Parts derived from universal-modder's tests/test_um.py (MIT, Copyright (c) 2026 Rehan and universal-modder
contributors), via universal-decompiler's tests/test_kb.py."""
from __future__ import annotations

import json
import shutil

from conftest import ROOT, vita

from vita_porter import kb


def test_repo_knowledge_is_valid_and_index_current():
    root = ROOT / "knowledge"
    notes = kb.notes(root)
    assert len(notes) >= 5
    titles = {m.get("title", "").lower() for _, m, _ in notes}
    for topic in ("livearea", "docker", "libshacccg", "vita3k", "memory"):
        assert any(topic in t for t in titles), topic
    for p, _, _ in notes:
        fails, _ = kb.check_note(p, root)
        assert not fails, (p, fails)
    idx, _ = kb.build_index(root)
    assert (root / "INDEX.md").read_text(encoding="utf-8") == idx, "run `vita kb index`"


def scaffold(tmp_path):
    root = tmp_path / "knowledge"
    root.mkdir()
    shutil.copy(ROOT / "knowledge" / "TEMPLATE.md", root / "TEMPLATE.md")
    return root


def test_kb_new_check_search(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, "Foo Racer", "Porting the Foo Racer reconstruction to PS Vita", agent="Codex (gpt-6)", route="sdl2-vitagl", family="ud")
    assert p.parent.name == "foo-racer"
    fails, _ = kb.check_note(p, root)
    assert any("unfilled template text" in f for f in fails)       # a fresh scaffold must not pass
    good = p.read_text(encoding="utf-8")
    good = good.replace("FILL IN: exact source version (commit, ud repo state)", "ud repo at abc1234").replace("FILL IN: embedded | external", "external")
    good = good.replace("> Two to four sentences: what you ported", "> Ported the race loop")
    good = good.replace("The most valuable section. Numbered; each one symptom -> cause -> fix.", "")
    good = good.replace("1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.",
                        "1. **Cars stutter on hardware.** **Cause:** shader compiles mid-race. **Fix:** warm the cache at load.")
    p.write_text(good, encoding="utf-8")
    fails, _ = kb.check_note(p, root)
    assert not fails, fails
    res = kb.search(root, ["stutter"])
    assert res and res[0]["path"].endswith("porting-the-foo-racer-reconstruction-to-ps-vita.md")
    assert kb.search(root, ["stutter"], route="vitagl-only") == []
    assert kb.search(root, [], family="ud")


def test_kb_topic_note(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, None, "Warming vitaGL's shader cache", kind="topic", agent="a (m)")
    assert p.parent.name == "tooling"
    fails, _ = kb.check_note(p, root)
    assert any("unfilled template text" in f for f in fails) and any("tags" in f for f in fails)


def test_kb_check_rejects_decompiled_code_and_address_tables(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, None, "Bad note", kind="topic", agent="a (m)")
    text = p.read_text(encoding="utf-8").replace("tags: []", "tags: [x]").replace("> Two to four sentences: what this is for and when it saves time.", "> x")
    text = text.replace("Numbered; each one symptom -> cause -> fix.\n", "").replace(
        "1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.", "1. **a.** b. **Cause:** c. **Fix:** d.")
    text += "\n```c\nundefined4 FUN_00401000(int param_1) {\n  uVar1 = param_1;\n}\n```\n"
    text += " ".join(f"0x{0x401000 + i * 16:08x}" for i in range(45)) + "\n"
    p.write_text(text, encoding="utf-8")
    fails, _ = kb.check_note(p, root)
    assert any("decompiled output" in f for f in fails) and any("distinct addresses" in f for f in fails)


def test_kb_title_note_validates_route_and_family(tmp_path):
    root = scaffold(tmp_path)
    p = kb.new_note(root, "X", "Port of X", agent="a (m)")
    t = p.read_text(encoding="utf-8").replace("route: other", "route: magic").replace("family: cmake", "family: unity")
    p.write_text(t, encoding="utf-8")
    fails, _ = kb.check_note(p, root)
    assert any("route 'magic'" in f for f in fails) and any("family 'unity'" in f for f in fails)


def test_kb_cli(tmp_path):
    r = vita("kb", "search", "libshacccg", "--json", cwd=ROOT)
    assert r.returncode == 0 and any("libshacccg" in x["path"] for x in json.loads(r.stdout))
    assert vita("kb", "check", "--index", cwd=ROOT).returncode == 0
    assert "Two to four sentences" not in vita("kb", "show", "tooling/memory-budgeting.md", cwd=ROOT).stdout
    d = vita("kb", "pr", str(ROOT / "knowledge" / "tooling" / "memory-budgeting.md"), "--json", cwd=ROOT)
    assert d.returncode == 0 and json.loads(d.stdout)["dry_run"]
