"""The knowledge base: field notes on how games were actually ported to PS Vita, written by agents for agents.

    vita kb search "vitagl shader cache"          # prior art before you start (local clone, or synced from GitHub)
    vita kb search sdl2 --route sdl2-vitagl       # filter by route / family
    vita kb show tooling/livearea-spec.md
    vita kb new --subject "Foo Racer" --title "Porting the Foo Racer reconstruction to PS Vita" --family ud --route sdl2-vitagl
    vita kb new --kind topic --family tooling --title "Profiling vitaGL memory pools"
    vita kb check knowledge/foo-racer/porting-the-foo-racer-reconstruction-to-ps-vita.md
    vita kb index                                 # regenerate knowledge/INDEX.md + index.json
    vita kb sync                                  # refresh the cached copy from GitHub
    vita kb pr knowledge/foo-racer/<note>.md --yes # branch, commit, push (fork if needed), open a PR

Notes are Markdown with YAML front matter (knowledge/TEMPLATE.md), one per game or topic, under
knowledge/<game-or-family>/: exact versions, the route and why, what worked, how it was verified, and gotchas
(symptom -> cause -> fix). `check` enforces the schema and sections and rejects secrets, code blocks over 40
lines, anything that looks like decompiled output (Ghidra/IDA auto-names, undefined4, uVar1, param_1 ...) and
large address tables. Never put game assets or decompiled code in a note. Ask your human before
`vita kb pr --yes`: a PR is public.

Derived from universal-modder's um/kb.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors),
via universal-decompiler's ud/kb.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from vita_porter.common import OK, PROBLEM, TEXT, data_dir, die, emit_json, usage

REPO = os.environ.get("VITA_KB_REPO", "hammerill/ps-vita-porter")
BRANCH = os.environ.get("VITA_KB_BRANCH", "main")
# how the port renders and reads input on the Vita
ROUTES = ["sdl2-vitagl", "sdl3-vitagl", "sdl2-gxm", "sdl3-gxm", "vitagl-only", "native-gxm", "other"]
# what the port started from
FAMILIES = ["ud", "cmake", "other-build", "other-language"]
DECOMP_PATTERNS = [
    ("Ghidra auto-name", re.compile(r"\b(?:FUN|DAT|LAB|PTR|SUB|UNK)_[0-9a-fA-F]{6,}\b")),
    ("IDA auto-name", re.compile(r"\b(?:sub|loc|unk|off|dword|qword|byte|word)_[0-9A-F]{5,}\b")),
    ("Ghidra decompiler types", re.compile(r"\bundefined[1248]?\b|\bin_stack_[0-9a-f]+\b|\bextraout_[A-Z]+\b|\bunaff_[A-Za-z0-9]+\b")),
    ("Ghidra/IDA locals", re.compile(r"\b(?:[ipu]Var|uVar|lVar|bVar|cVar|sVar|pcVar|puVar|piVar|ppVar|auVar)\d+\b|\b(?:local|param)_[0-9a-f]{1,4}\b")),
    ("decompiler banner", re.compile(r"/\*\s*WARNING: |Decompiled with|JetBrains decompiler|^\s*//\s*ILSpy|// Decompiled by", re.M)),
]
STATUSES = ["idea", "in-progress", "working", "complete", "abandoned"]
TITLE_KEYS = ["kind", "title", "subject", "subject_version", "family", "route", "status", "date", "agents"]
TOPIC_KEYS = ["kind", "title", "tags", "date", "agents"]
TITLE_SECTIONS = ["setup", "route", "what worked", "verification", "gotchas"]
MAX_BLOCK_WARN, MAX_BLOCK_FAIL = 15, 40
MAX_ADDR_WARN, MAX_ADDR_FAIL = 15, 40
MAX_NOTE_KB, MAX_MEDIA_MB = 120, 1.5
SKIP = ("README.md", "INDEX.md", "TEMPLATE.md")


# --------------------------------------------------------------------------- where the notes are

def local_root() -> Path | None:
    """knowledge/ of the repo this package runs from (clone, plugin, editable install), or of the cwd's repo."""
    here = Path(__file__).resolve().parents[1] / "knowledge"
    if (here / "TEMPLATE.md").exists():
        return here
    for d in [Path.cwd(), *Path.cwd().parents]:
        if (d / "knowledge" / "TEMPLATE.md").exists():
            return d / "knowledge"
    return None


def cache_root() -> Path:
    return data_dir() / "kb" / REPO.replace("/", "__") / "knowledge"


def sync(quiet: bool = False) -> Path:
    """Mirror knowledge/ from GitHub into the cache (git tree API + raw files; no auth needed)."""
    api = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    req = urllib.request.Request(api, headers={"User-Agent": "ps-vita-porter", "Accept": "application/vnd.github+json"})
    tree = json.load(urllib.request.urlopen(req, timeout=60))
    paths = [t["path"] for t in tree.get("tree", []) if t["type"] == "blob" and t["path"].startswith("knowledge/")
             and t["path"].endswith((".md", ".json"))]
    root = cache_root()
    tmp = root.with_name("knowledge.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    for p in paths:
        dst = tmp / p[len("knowledge/"):]
        dst.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{p}"
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ps-vita-porter"}), timeout=60) as r:
            dst.write_bytes(r.read())
    shutil.rmtree(root, ignore_errors=True)
    tmp.rename(root)
    (root / ".synced").write_text(str(time.time()), **TEXT)
    if not quiet:
        print(f"synced {len(paths)} files from github.com/{REPO} -> {root}")
    return root


def resolve_root(explicit: str | None = None, remote: bool = False) -> Path:
    if explicit:
        return Path(explicit)
    if os.environ.get("VITA_KB"):
        return Path(os.environ["VITA_KB"])
    loc = None if remote else local_root()
    if loc:
        return loc
    root = cache_root()
    stamp = root / ".synced"
    stale = not stamp.exists() or time.time() - float(stamp.read_text(encoding="utf-8") or 0) > 86400
    if stale:
        try:
            return sync(quiet=True)
        except OSError as e:
            if not root.exists():
                die(f"no local knowledge/ and GitHub sync failed ({e}); clone https://github.com/{REPO}")
    return root


# --------------------------------------------------------------------------- notes

def parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    import yaml
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except (yaml.YAMLError, ValueError) as e:  # ValueError: a date YAML can't build, e.g. 2026-09-31
        return {"_yaml_error": str(e)}, m.group(2)
    return (meta if isinstance(meta, dict) else {}), m.group(2)


def notes(root: Path) -> list[tuple[Path, dict, str]]:
    out = []
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        if rel in SKIP:
            continue
        meta, body = parse(p)
        out.append((p, meta, body))
    return out


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "note"


# --------------------------------------------------------------------------- search

def search(root: Path, terms: list[str], subject=None, family=None, engine=None, route=None, limit=10) -> list[dict]:
    terms = [t.lower() for t in terms if t.strip()]
    res = []
    for p, meta, body in notes(root):
        if subject and slug(subject) not in slug(str(meta.get("subject", ""))):
            continue
        if family and str(meta.get("family", "")).lower() != family.lower():
            continue
        if engine and str(meta.get("engine", "")).lower() != engine.lower():
            continue
        if route and str(meta.get("route", "")).lower() != route.lower():
            continue
        fields = {
            5: str(meta.get("title", "")),
            4: str(meta.get("subject", "")),
            3: " ".join(str(x) for x in [meta.get("family", ""), meta.get("engine", ""), meta.get("route", ""),
                                          *(meta.get("tags") or []), *(meta.get("tools") or [])]),
        }
        low = body.lower()
        score = 0
        for t in terms:
            score += sum(w for w, f in fields.items() if t in f.lower())
            score += min(5, low.count(t))
        if terms and score == 0:
            continue
        hits = [ln.strip() for ln in body.splitlines() if ln.strip() and any(t in ln.lower() for t in terms)][:3]
        res.append(dict(score=score, path=p.relative_to(root).as_posix(), title=meta.get("title"), subject=meta.get("subject"),
                        family=meta.get("family"), route=meta.get("route"), status=meta.get("status"), hits=hits))
    res.sort(key=lambda r: -r["score"])
    return res[:limit]


# --------------------------------------------------------------------------- check

def check_note(path: Path, root: Path | None = None) -> tuple[list[str], list[str]]:
    from vita_porter.publish import SECRET_PATTERNS
    fails, warns = [], []
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = parse(path)
    if not meta:
        return [f"{path}: no YAML front matter (start the file with --- ... --- ; see knowledge/TEMPLATE.md)"], []
    if "_yaml_error" in meta:
        return [f"{path}: front matter is not valid YAML: {meta['_yaml_error']}"], []
    kind = meta.get("kind", "title")
    if kind not in ("title", "topic"):
        fails.append(f"kind must be title or topic, not {kind!r}")
    for k in TITLE_KEYS if kind == "title" else TOPIC_KEYS:
        if meta.get(k) in (None, "", []):
            fails.append(f"missing front-matter key: {k}")
    if kind == "title":
        if meta.get("route") and meta["route"] not in ROUTES:
            fails.append(f"route {meta['route']!r} not one of: {', '.join(ROUTES)}")
        if meta.get("family") and meta["family"] not in FAMILIES:
            fails.append(f"family {meta['family']!r} must be one of: {', '.join(FAMILIES)}")
        heads = [h.lower() for h in re.findall(r"^##\s+(.+)$", body, re.M)]
        for s in TITLE_SECTIONS:
            if not any(h.startswith(s) for h in heads):
                fails.append(f"missing section: ## {s.capitalize()}...")
    if any(h.lower().startswith("gotchas") for h in re.findall(r"^##\s+(.+)$", body, re.M)):
        if not re.search(r"^##\s+Gotchas.*?\n(?:.*\n)*?\s*1\.", body, re.M | re.I):
            warns.append("Gotchas section has no numbered items")
    if meta.get("status") and meta["status"] not in STATUSES:
        fails.append(f"status {meta['status']!r} not one of: {', '.join(STATUSES)}")
    d = meta.get("date")
    if d and not isinstance(d, dt.date) and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d)):
        fails.append(f"date must be YYYY-MM-DD, got {d!r}")
    if not isinstance(meta.get("agents", []), list):
        fails.append("agents must be a list, e.g. [\"Claude Code (Opus 5.5)\"]")
    left = [ph for ph in ("FILL IN", "Two to four sentences:", "Numbered; each one symptom", "What you saw. **Cause:** what it really was")
            if ph in text]
    if left and path.name != "TEMPLATE.md":
        fails.append(f"unfilled template text: {', '.join(repr(x) for x in left)}")
    for label, rx in SECRET_PATTERNS:
        if rx.search(text):
            fails.append(f"{label} in the note - remove it")
    blocks = re.findall(r"```[^\n]*\n(.*?)```", body, re.S)
    for b in blocks:
        n = b.count("\n")
        if n > MAX_BLOCK_FAIL:
            fails.append(f"a {n}-line code block (limit {MAX_BLOCK_FAIL}): describe it in words or link your own repo")
        elif n > MAX_BLOCK_WARN:
            warns.append(f"a {n}-line code block: keep snippets short (under {MAX_BLOCK_WARN} lines)")
        hit = [label for label, rx in DECOMP_PATTERNS if rx.search(b)]
        strong = {"Ghidra decompiler types", "Ghidra/IDA locals", "decompiler banner"}
        if len(hit) >= 2 or strong.intersection(hit):
            fails.append(f"code block looks like decompiled output ({', '.join(hit)}): never paste decompiled code; describe the logic")
        elif hit:
            warns.append(f"{hit[0]} in a code block: name your own symbols instead")
    prose = re.sub(r"```.*?```", "", body, flags=re.S)
    addrs = set(re.findall(r"\b0x[0-9a-fA-F]{6,16}\b", text))
    if len(addrs) > MAX_ADDR_FAIL:
        fails.append(f"{len(addrs)} distinct addresses: an address table that large helps rebuild the code; keep a few examples")
    elif len(addrs) > MAX_ADDR_WARN:
        warns.append(f"{len(addrs)} distinct addresses: keep it to the few that explain something")
    if re.search(r"\b(?:FUN|DAT|LAB)_[0-9a-fA-F]{6,}\b", prose) and len(re.findall(r"\b(?:FUN|DAT|LAB)_[0-9a-fA-F]{6,}\b", prose)) > 10:
        warns.append("many Ghidra auto-names in the text: use your own names")
    if re.search(r"[A-Z]:\\Users\\(?!<)[^\\\s`\"']+|/home/(?!<)[a-z_][a-z0-9_-]*/|/Users/(?!<)[A-Za-z]+/", text):
        warns.append("absolute user path (use <you>, %USERPROFILE% or ~ instead)")
    if len(text.encode()) > MAX_NOTE_KB * 1024:
        warns.append(f"note is {len(text.encode()) // 1024} KB; split it or trim (limit {MAX_NOTE_KB} KB)")
    for m in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)\)", body):
        src = m.group(1)
        if src.startswith("http"):
            continue
        img = (path.parent / src).resolve()
        if not img.exists():
            fails.append(f"image not found: {src}")
        elif img.stat().st_size > MAX_MEDIA_MB * 2**20:
            fails.append(f"image {src} is {img.stat().st_size / 2**20:.1f} MB (limit {MAX_MEDIA_MB} MB)")
    return fails, warns


# --------------------------------------------------------------------------- index

def build_index(root: Path) -> tuple[str, list[dict]]:
    rows = []
    for p, meta, _ in notes(root):
        rows.append(dict(path=p.relative_to(root).as_posix(), **{k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in meta.items()}))
    titles = sorted([r for r in rows if r.get("kind", "title") == "title"], key=lambda r: (str(r.get("subject", "")).lower(), str(r.get("date", ""))))
    topics = sorted([r for r in rows if r.get("kind") == "topic"], key=lambda r: (str(r.get("family", "")), str(r.get("title", "")).lower()))
    esc = lambda s: str(s or "").replace("|", "\\|")
    lines = ["# Knowledge base index", "",
             "_Generated by `vita kb index` from the notes' front matter; don't edit by hand. Machine-readable: `index.json`._", "",
             f"## Titles ({len(titles)} notes)", ""]
    if titles:
        lines += ["| Subject | Note | Family | Route | Status | Agents | Date |", "|---|---|---|---|---|---|---|"]
        for r in titles:
            lines.append(f"| {esc(r.get('subject'))} | [{esc(r.get('title'))}]({r['path']}) | {esc(r.get('family'))} | {esc(r.get('route'))} | "
                         f"{esc(r.get('status'))} | {esc(', '.join(r.get('agents') or []))} | {esc(r.get('date'))} |")
    else:
        lines.append("_None yet: the first agent to finish a port writes one (`vita kb new`)._")
    lines += ["", f"## Topics ({len(topics)} notes)", ""]
    for r in topics:
        lines.append(f"- [{esc(r.get('title'))}]({r['path']}) · {esc(r.get('family') or '')} · {esc(', '.join(r.get('tags') or []))}")
    lines += ["", "## References", "",
              "Hardware, vitaGL, memory, controls, LiveArea and testing references live with the skill: "
              "[skills/port-to-vita/references/](../skills/port-to-vita/references/).", ""]
    return "\n".join(lines), rows


# --------------------------------------------------------------------------- new / pr

def new_note(root: Path, subject: str | None, title: str, kind: str = "title", from_scan: bool = False, family: str | None = None,
             route: str | None = None, agent: str | None = None, out: str | None = None) -> Path:
    import yaml
    meta, body = parse(root / "TEMPLATE.md")
    meta = dict(meta)
    meta.update(kind=kind, title=title, date=dt.date.today().isoformat(), agents=[agent or os.environ.get("VITA_AGENT", "FILL IN: agent (model)")],
                humans=[], links=[], tags=[], status="in-progress")
    if kind == "title":
        meta.update(subject=subject or "FILL IN", subject_version="FILL IN: exact source version (commit, ud repo state)",
                    family=family or "cmake", route=route or "other", tools=[], assets_mode="FILL IN: embedded | external")
        if from_scan:
            from vita_porter.scan import scan
            s = scan(Path.cwd())
            meta.update(family=family or ("ud" if s["project"]["ud_repo"] else "cmake"),
                        graphics=s["graphics"]["summary"], dependencies=[d["name"] for d in s["dependencies"]][:12])
    else:
        for k in ("subject", "subject_version", "route", "tools", "assets_mode", "graphics", "dependencies"):
            meta.pop(k, None)
        meta["family"] = family or "tooling"
    body = re.sub(r"^# .*$", f"# {title}", body, count=1, flags=re.M)
    if kind == "topic":
        body = (f"# {title}\n\n> Two to four sentences: what this is for and when it saves time.\n\n## When to use it\n\n## How\n\n"
                "## Gotchas\nNumbered; each one symptom -> cause -> fix.\n"
                "1. **Symptom.** What you saw. **Cause:** what it really was. **Fix:** what worked.\n\n"
                "## Seen in\nLinks to title notes that used it.\n")
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=120)
    folder = slug(meta.get("subject", "misc")) if kind == "title" else slug(meta["family"])
    path = Path(out) if out else root / folder / f"{slug(title)}.md"
    if path.exists():
        usage(f"{path} exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}---\n{body}", **TEXT)
    return path


def pr_head(branch: str, fork_url: str | None) -> str:
    """The --head for `gh pr create`: a PR from a fork needs "<fork owner>:<branch>"."""
    m = re.search(r"github\.com[:/]+([^/]+)/", fork_url or "")
    return f"{m.group(1)}:{branch}" if m else branch


def open_pr(path: Path, yes: bool, as_json: bool = False) -> int:
    """Branch + commit the note (and its media + regenerated index) + push to your fork + gh pr create."""
    root = local_root()
    if not root:
        die("run this inside a clone of ps-vita-porter (or your fork)")
    repo = root.parent
    meta, _ = parse(path)
    fails, _ = check_note(path, root)
    if fails:
        die("fix these first:\n  " + "\n  ".join(fails))
    branch = f"kb/{slug(meta.get('subject', '') or meta.get('family', 'topic'))}-{slug(meta.get('title', 'note'))}"[:80]
    title = f"kb: {meta.get('title')}" + (f" ({meta.get('subject')})" if meta.get("subject") else "")
    body = (f"Field note: **{meta.get('title')}**\n\n- subject: {meta.get('subject', '-')}\n- family / route: {meta.get('family', '-')} / "
            f"{meta.get('route', '-')}\n- status: {meta.get('status')}\n- agents: {', '.join(meta.get('agents') or [])}\n\n"
            "Checked with `vita kb check`; index regenerated with `vita kb index`.\n\n"
            "- [x] no .vpk files, game assets, decompiled code or large address tables\n- [x] versions and verification written down\n")
    media = list(path.parent.glob("media/*")) if (path.parent / "media").exists() else []
    can_push = False
    if shutil.which("gh"):
        r = subprocess.run(["gh", "api", f"repos/{REPO}", "--jq", ".permissions.push"], capture_output=True, text=True)
        can_push = r.stdout.strip() == "true"
    remote = "origin" if can_push else "fork"
    cmds = [["git", "checkout", "-b", branch], ["vita", "kb", "index"],
            ["git", "add", str(path), str(root / "INDEX.md"), str(root / "index.json"), *map(str, media)],
            ["git", "commit", "-m", title]]
    if not can_push:
        cmds.append(["gh", "repo", "fork", "--remote", "--remote-name", "fork"])
    cmds += [["git", "push", "-u", remote, branch],
             ["gh", "pr", "create", "--repo", REPO, "--head", branch, "--title", title, "--body", body]]
    if not yes and as_json:
        emit_json(dict(dry_run=True, branch=branch, title=title, commands=cmds))
        return OK
    if not yes:
        print("dry run (add --yes after your human agrees):")
        for c in cmds:
            print("  " + " ".join(c if len(" ".join(c)) < 200 else c[:6] + ["..."]))
        return OK
    if not shutil.which("gh"):
        die("needs the GitHub CLI (gh) logged in; or push a branch and open the PR on github.com")
    idx, rows = build_index(root)
    (root / "INDEX.md").write_text(idx, **TEXT)
    (root / "index.json").write_text(json.dumps(rows, indent=1, default=str) + "\n", **TEXT)
    for c in cmds:
        if c[:3] == ["vita", "kb", "index"]:
            continue
        if c[:3] == ["gh", "repo", "fork"] and subprocess.run(["git", "remote", "get-url", "fork"], cwd=repo, capture_output=True).returncode == 0:
            continue
        if c[:3] == ["gh", "pr", "create"] and remote == "fork":
            url = subprocess.run(["git", "remote", "get-url", "fork"], cwd=repo, capture_output=True, text=True).stdout.strip()
            c[c.index("--head") + 1] = pr_head(branch, url)
        r = subprocess.run(c, cwd=repo, capture_output=True, text=True)
        if r.returncode:
            die(f"{' '.join(c[:4])} failed: {(r.stderr or r.stdout).strip()[-800:]}")
        if c[:3] == ["gh", "pr", "create"]:
            print(r.stdout.strip())
    return OK


# --------------------------------------------------------------------------- CLI

def main(a):
    c = a.cmd
    if c == "sync":
        root = sync(quiet=a.json)
        if a.json:
            emit_json(dict(root=str(root), files=sum(1 for _ in root.rglob("*") if _.is_file())))
        return OK
    if c == "search":
        root = resolve_root(a.root, a.remote)
        res = search(root, a.terms, a.subject, a.family, a.engine, a.route, a.limit)
        if a.json:
            emit_json(res)
            return OK
        if not res:
            print(f"nothing in {root} matches; you may be first - write it up afterwards (`vita kb new`)")
        for r in res:
            facts = " | ".join(str(x) for x in (r["subject"], r["family"], r["route"], r["status"]) if x) or "topic"
            print(f"{r['path']}\n   {r['title']}  [{facts}]")
            for h in r["hits"]:
                print(f"     | {h.lstrip('> ')[:160]}")
        return OK
    if c == "show":
        root = resolve_root(a.root, a.remote)
        p = root / a.note
        if not p.exists():
            cands = [x for x in root.rglob("*.md") if a.note in x.as_posix()]
            if not cands:
                usage(f"no note {a.note!r} in {root}")
            p = cands[0]
        print(p.read_text(encoding="utf-8"))
        return OK
    if c == "new":
        root = Path(a.root) if a.root else local_root()
        if not root:
            usage("run inside a clone of ps-vita-porter (knowledge/ is written there), or pass --root")
        p = new_note(root, a.subject, a.title, a.kind, a.from_scan, a.family, a.route, a.agent, a.out)
        if a.json:
            emit_json(dict(note=str(p)))
            return OK
        print(p)
        print("next: fill it in (Gotchas matter most), `vita kb check " + str(p) + "`, `vita kb index`, then a PR (`vita kb pr ...`) once your human says OK")
        return OK
    if c == "check":
        root = Path(a.root) if a.root else local_root()
        paths = [Path(x) for x in a.paths] or ([p for p, _, _ in notes(root)] if root else [])
        bad = 0
        report = []
        for p in paths:
            fails, warns = check_note(p, root)
            report.append(dict(note=str(p), fails=fails, warnings=warns))
            bad += bool(fails)
        stale = False
        if root and a.index and not a.paths:
            idx, _ = build_index(root)
            stale = not (root / "INDEX.md").exists() or (root / "INDEX.md").read_text(encoding="utf-8") != idx
            bad += stale
        if a.json:
            emit_json(dict(ok=not bad, notes=report, index_stale=stale))
        else:
            for r in report:
                for f in r["fails"]:
                    print(f"FAIL {r['note']}: {f}")
                for w in r["warnings"]:
                    print(f"WARN {r['note']}: {w}")
            if stale:
                print("FAIL knowledge/INDEX.md is out of date: run `vita kb index`")
            print(f"{'FAIL' if bad else 'PASS'}: {len(paths)} notes checked")
        return PROBLEM if bad else OK
    if c == "index":
        root = Path(a.root) if a.root else local_root()
        if not root:
            usage("no local knowledge/ folder")
        idx, rows = build_index(root)
        (root / "INDEX.md").write_text(idx, **TEXT)
        (root / "index.json").write_text(json.dumps(rows, indent=1, default=str, ensure_ascii=False) + "\n", **TEXT)
        if a.json:
            emit_json(dict(index=str(root / "INDEX.md"), notes=len(rows)))
        else:
            print(f"{root / 'INDEX.md'}: {len(rows)} notes")
        return OK
    if c == "pr":
        return open_pr(Path(a.note), a.yes, a.json)
    usage("give a command: search, show, new, check, index, sync or pr")


def register(sub):
    import argparse
    p = sub.add_parser("kb", help="knowledge base of Vita ports: search, write, check, PR",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("search", help="find prior notes (local clone, else the GitHub copy)")
    q.add_argument("terms", nargs="*")
    q.add_argument("--subject")
    q.add_argument("--family")
    q.add_argument("--engine", help=argparse.SUPPRESS)
    q.add_argument("--route", choices=ROUTES)
    q.add_argument("--limit", type=int, default=10)
    q.add_argument("--json", action="store_true")
    q.add_argument("--remote", action="store_true", help="search the synced GitHub copy even inside a clone")
    q.add_argument("--root")
    q.set_defaults(func=main)
    q = cs.add_parser("show", help="print a note")
    q.add_argument("note")
    q.add_argument("--remote", action="store_true")
    q.add_argument("--root")
    q.set_defaults(func=main)
    q = cs.add_parser("new", help="scaffold a note from the template")
    q.add_argument("--title", required=True)
    q.add_argument("--subject", help="the game (title notes)")
    q.add_argument("--kind", default="title", choices=["title", "topic"])
    q.add_argument("--from-scan", action="store_true", help="pre-fill family / graphics / dependencies from `vita scan` of the cwd")
    q.add_argument("--family", help=f"title notes: {', '.join(FAMILIES)}; topics: the folder (default: tooling)")
    q.add_argument("--route", choices=ROUTES)
    q.add_argument("--agent", help='e.g. "Claude Code (Opus 5.5)"; default $VITA_AGENT')
    q.add_argument("--out")
    q.add_argument("--root")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("check", help="validate notes (all, or the given paths)")
    q.add_argument("paths", nargs="*")
    q.add_argument("--index", action="store_true", help="also fail if INDEX.md is stale")
    q.add_argument("--root")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("index", help="regenerate knowledge/INDEX.md and index.json")
    q.add_argument("--root")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("sync", help="refresh the cached GitHub copy")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
    q = cs.add_parser("pr", help="open a pull request with a note (dry run unless --yes)")
    q.add_argument("note")
    q.add_argument("--yes", action="store_true", help="really branch, push and open the PR")
    q.add_argument("--json", action="store_true", help="dry run as JSON")
    q.set_defaults(func=main)
