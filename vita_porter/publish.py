"""Refuse to publish packages and game data. Run by the pre-push hook that `vita init` installs, and by hand.

    vita publish check                 # this repo: every blob reachable from any ref, plus the index
    vita publish check --json
    vita publish check --no-ud         # skip `ud publish check` in a universal-decompiler repo

FAIL  .vpk files (they may carry game assets), Vita build outputs that embed the program (eboot.bin, *.self,
      *.velf) and crash dumps (*.psp2dmp: they hold the process's memory); converted assets ([assets] out,
      default build-vita/assets) and anything under build-vita/ or build-sim/; in a universal-decompiler repo,
      the extracted assets and the original (data/, files byte-identical to a file in data/, the original's
      binary and game containers); secrets (API keys, private keys). In history too: a file deleted later is still
      pushed.
ALSO  in a universal-decompiler repo, `ud publish check` runs as well (if `ud` is on PATH) and its failures count:
      the reconstruction itself must stay private, and that's ud's rule to enforce.

The project's own assets (an original open-source game's art, committed on purpose) are fine; exceptions for
your own files: [publish] allow = ["glob", ...] in vita.toml. Patterns adapted from universal-decompiler's
ud/publish.py, whose secret patterns derive from universal-modder's um/publish.py (MIT, Copyright (c) 2026 Rehan
and universal-modder contributors).
"""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
from pathlib import Path

from vita_porter.common import OK, PROBLEM, emit_json, git, is_ud_repo, load_config, repo_root

SECRET_PATTERNS = [
    ("Anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI key", re.compile(r"\bsk-(?:(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{32,}|[A-Za-z0-9]{32,})")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})")),
    ("AWS key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
PACKAGE_EXT = {".vpk": "a .vpk package", ".self": "a Vita executable", ".velf": "a Vita executable", ".psp2dmp": "a crash dump"}
ORIGINAL_EXT = {".exe", ".dll", ".so", ".dylib", ".xbe", ".xex", ".elf", ".nso", ".nro", ".nsp", ".xci", ".iso", ".cso", ".z64", ".n64",
                ".v64", ".gba", ".nds", ".3ds", ".dol", ".pbp", ".cue", ".chd", ".pak", ".pck", ".assets", ".unity3d", ".bundle", ".uasset",
                ".rpa", ".xnb", ".bsa", ".ba2", ".wad", ".pk3", ".pk4", ".bik", ".bk2", ".xwb", ".fsb", ".bnk", ".wem", ".gpr", ".gzf", ".rpf",
                ".img", ".txd", ".dff"}
BUILD_DIRS = ["build-vita/", "build-sim/"]


def history_blobs(root: Path) -> list[tuple[str, int, str]]:
    """(path, size, sha) for every blob reachable from any ref, plus the index."""
    pairs = []
    for line in git(["rev-list", "--objects", "--all"], cwd=root).stdout.splitlines():
        sha, _, path = line.partition(" ")
        if path:
            pairs.append((sha, path))
    for ent in git(["ls-files", "-s", "-z"], cwd=root).stdout.split("\0"):
        meta, _, path = ent.partition("\t")
        parts = meta.split()
        if path and len(parts) >= 2:
            pairs.append((parts[1], path))
    if not pairs:
        return []
    p = subprocess.run(["git", "cat-file", "--batch-check=%(objecttype) %(objectname) %(objectsize)"], cwd=root,
                       input="\n".join(s for s, _ in pairs) + "\n", capture_output=True, text=True)
    types = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            types[parts[1]] = (parts[0], int(parts[2]))
    out = {}
    for sha, path in pairs:
        t = types.get(sha)
        if t and t[0] == "blob":
            out[(path, sha)] = t[1]
    return [(path, size, sha) for (path, sha), size in sorted(out.items())]


def data_blob_hashes(root: Path, data_dir: Path, sizes: set[int]) -> dict[str, str]:
    """git blob sha -> data path, only for data files whose size matches a tracked blob (cheap on big installs)."""
    cands = []
    if data_dir.is_dir():
        for p in data_dir.rglob("*"):
            try:
                if p.is_file() and p.stat().st_size in sizes:
                    cands.append(p)
            except OSError:
                pass
    if not cands:
        return {}
    r = subprocess.run(["git", "hash-object", "--no-filters", "--stdin-paths"], cwd=root, input="\n".join(map(str, cands)) + "\n",
                       capture_output=True, text=True)
    return {sha: p.relative_to(root).as_posix() for sha, p in zip(r.stdout.split(), cands, strict=False)}


def ud_check(root: Path) -> dict | None:
    ud = shutil.which("ud")
    if not ud:
        return None
    offline = ["--offline"] if os.environ.get("VITA_PUBLISH_OFFLINE") else []
    r = subprocess.run([ud, "publish", "check", "--json", *offline], cwd=root, capture_output=True, text=True)
    try:
        import json
        return dict(ran=True, **json.loads(r.stdout))
    except ValueError:
        return dict(ran=True, ok=r.returncode == 0, fails=[] if r.returncode == 0 else [(r.stdout or r.stderr).strip()[-400:]], warnings=[])


def check(path: str | None = None, run_ud: bool = True) -> dict:
    root = repo_root(path)
    cfg = load_config(root)
    ud = is_ud_repo(root)
    allow = list(cfg.get("publish", {}).get("allow", []))
    converted = (cfg.get("assets", {}).get("out") or "build-vita/assets").strip("/") + "/"
    fail_dirs = sorted(set(BUILD_DIRS + [converted]))
    if ud:
        fail_dirs.append((cfg.get("assets", {}).get("source") or "data").strip("/") + "/")
        fail_dirs.append("data/")
    blobs = history_blobs(root)
    current = set(git(["ls-files", "-z"], cwd=root).stdout.split("\0"))
    fails, warns, flagged = [], [], set()

    def where(p):
        return "" if p in current else " (in history: deleted later, but still pushed)"

    for p, size, _sha in blobs:
        if any(fnmatch.fnmatch(p, a) for a in allow):
            continue
        low = p.lower()
        ext = os.path.splitext(low)[1]
        name = low.rsplit("/", 1)[-1]
        reason = None
        if ext in PACKAGE_EXT:
            reason = PACKAGE_EXT[ext]
        elif name == "eboot.bin":
            reason = "a Vita eboot.bin (the built program)"
        elif any(low.startswith(d.lower()) for d in fail_dirs):
            reason = "converted or extracted assets / build output"
        elif ud and ext in ORIGINAL_EXT:
            reason = f"looks like the original's binary or game container ({ext})"
        if reason and (p, reason) not in flagged:
            flagged.add((p, reason))
            fails.append(f"{p}: {reason}{where(p)}")
        elif size > 5 << 20:
            warns.append(f"{p}: {size / (1 << 20):.1f} MiB{where(p)}: make sure it's your own file")
    if ud:
        same = data_blob_hashes(root, root / "data", {s for _, s, _ in blobs if s >= 64})
        for p, _size, sha in blobs:
            if sha in same and not p.startswith("data/") and not any(fnmatch.fnmatch(p, a) for a in allow):
                fails.append(f"{p}: byte-identical to {same[sha]} (a file from the original){where(p)}")
    for p in sorted(current):
        if not p or os.path.splitext(p)[1].lower() not in {".c", ".cpp", ".cc", ".h", ".hpp", ".py", ".md", ".txt", ".toml", ".json", ".env", ".cmake"}:
            continue
        try:
            txt = (root / p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for label, rx in SECRET_PATTERNS:
            if rx.search(txt):
                fails.append(f"{p}: {label}")
    udr = ud_check(root) if ud and run_ud else None
    if ud and run_ud and udr is None:
        warns.append("universal-decompiler repo but `ud` isn't on PATH: `ud publish check` (privacy of the reconstruction) not run")
    if udr:
        fails += [f"ud publish check: {x}" for x in udr.get("fails", [])]
        warns += [f"ud publish check: {x}" for x in udr.get("warnings", [])]
    return dict(repo=str(root), ud_repo=ud, ok=not fails, fails=fails, warnings=warns, blobs_checked=len(blobs), ud_publish_check=udr)


def main(a):
    r = check(a.path, not a.no_ud)
    if a.json:
        emit_json(r)
        return OK if r["ok"] else PROBLEM
    for x in r["fails"]:
        print("FAIL ", x)
    for x in r["warnings"]:
        print("WARN ", x)
    print(f"{'FAIL' if r['fails'] else 'PASS'}: {r['blobs_checked']} blobs in history" + (" (universal-decompiler repo)" if r["ud_repo"] else ""))
    if r["fails"]:
        print("A .vpk with game assets, converted or extracted assets and the original never get committed or published.\n"
              "  Untrack a file but keep your copy:  git rm --cached <file>  (then commit; `git reset --hard` would delete it from disk)\n"
              "  Already in older commits:           rewrite them (e.g. git filter-repo --invert-paths --path <file>) before pushing")
    return OK if r["ok"] else PROBLEM


def register(sub):
    import argparse
    p = sub.add_parser("publish", help="refuse to publish .vpk files, converted/extracted assets, the original (pre-push hook)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    cs = p.add_subparsers(dest="cmd", metavar="<cmd>")
    q = cs.add_parser("check", help="check the repo's history", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("path", nargs="?", help="a path inside the repo (default: cwd)")
    q.add_argument("--no-ud", action="store_true", help="don't run `ud publish check` in a universal-decompiler repo")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=main)
