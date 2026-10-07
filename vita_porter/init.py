"""Set up the game's source repo for the Vita port. Idempotent: run it again any time.

    cd my-game                       # the repo with the full source (normally a universal-decompiler repo)
    vita init                        # vita.toml, PORT_PLAN.md, PORTLOG.md, .gitignore block, pre-push guard
    vita init --title-id ABCD00001 --name "My Game"
    vita init --kit                  # also the vitaport kit (platform/vita/vitaport/) and cmake/VitaPort.cmake
    vita init --no-hook              # no pre-push guard (a project in a sub-folder of a bigger repo)
    vita init --json

What it does:
  vita.toml        title ID, name, version, assets mode, data folder, unsafe flag, build backend (only if missing)
  PORT_PLAN.md     intake answers, done criterion, technical plan (only if missing)
  PORTLOG.md       the journal (only if missing)
  .gitignore       a managed block: build-vita/, build-sim/, *.vpk
  pre-push hook    runs `vita publish check` before every push (an existing hook is kept and chained)
  --kit            platform/vita/vitaport/ (input, touch, motion, paths, logging, screenshots, the PC simulation
                   profile and its memory cap) and cmake/VitaPort.cmake (Vita target helpers)

A universal-decompiler repo (ud.toml, or DECOMP_PLAN.md + decomp/progress.json) is detected: the assets default
to external (they come from the user's own copy in data/ and must never be inside a .vpk anyone shares).
"""
from __future__ import annotations

import datetime as dt
import re
import shutil
import stat
import sys
import zlib
from pathlib import Path

from vita_porter.common import OK, PROBLEM, RESERVED_PREFIXES, TEXT, emit_json, git, is_ud_repo, project_root, title_id_problems

TEMPLATES = Path(__file__).resolve().parent / "templates"
KIT = Path(__file__).resolve().parent / "kit"
BEGIN, END = "# >>> ps-vita-porter (vita init)", "# <<< ps-vita-porter"
IGNORE = ["# Vita builds, the PC simulation profile and packages (a .vpk can contain game assets)",
          "build-vita/", "build-sim/", "*.vpk", "*.psp2dmp"]
HOOK_MARK = "ps-vita-porter pre-push guard"


def suggest_title_id(name: str) -> str:
    """4 letters from the name + 5 digits from its CRC, avoiding reserved prefixes."""
    letters = re.sub(r"[^A-Z]", "", name.upper())
    cons = re.sub(r"[AEIOU]", "", letters)
    head = (letters[:1] + cons[1:] + letters[1:] + "XXXX")[:4] if letters else "PORT"
    if head.startswith(RESERVED_PREFIXES):
        head = "V" + head[1:] if not ("V" + head[1:]).startswith(RESERVED_PREFIXES) else "HOMB"
    return f"{head}{zlib.crc32(name.encode()) % 100000:05d}"


def data_folder_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", name.replace(" ", "")) or "game"


def gitignore(root: Path) -> str:
    p = root / ".gitignore"
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    block = "\n".join([BEGIN, *IGNORE, END]) + "\n"
    if BEGIN in old and END in old:
        head, rest = old.split(BEGIN, 1)
        new = head + block + rest.split(END, 1)[1].lstrip("\n")
    else:
        new = old + ("\n" if old and not old.endswith("\n") else "") + ("\n" if old.strip() else "") + block
    if new == old:
        return "unchanged"
    p.write_text(new, **TEXT)
    return "updated" if old else "created"


def launcher() -> str:
    """How the hook calls vita when it isn't on PATH: the toolkit's bin/vita, else this interpreter."""
    here = Path(__file__).resolve().parents[1]
    if (here / "bin" / "vita").exists():
        return f'"{(here / "bin" / "vita").as_posix()}"'
    return f'"{Path(sys.executable).as_posix()}" -m vita_porter'


def hook_script() -> str:
    return f"""#!/bin/sh
# {HOOK_MARK} (installed by `vita init`; re-run it to refresh).
# Refuses pushes that would publish .vpk files, converted or extracted assets, or the original binary.
remote="$1"
url="$2"
refs=$(cat)
here=$(dirname "$0")
if [ -x "$here/pre-push.local" ]; then
  printf '%s\\n' "$refs" | "$here/pre-push.local" "$@" || exit $?
fi
if command -v vita >/dev/null 2>&1; then
  vita publish check
else
  {launcher()} publish check
fi
status=$?
if [ $status -ne 0 ]; then
  echo "pre-push: blocked by vita publish check (exit $status)." >&2
  exit 1
fi
exit 0
"""


def install_hook(root: Path) -> str:
    r = git(["rev-parse", "--git-path", "hooks"], cwd=root, check=True)
    hooks = Path(r.stdout.strip())
    if not hooks.is_absolute():
        hooks = root / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-push"
    text = hook_script()
    status = "created"
    if hook.exists():
        old = hook.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARK not in old:
            local = hooks / "pre-push.local"
            if local.exists():
                shutil.copyfile(hook, hooks / f"pre-push.local.{dt.datetime.now():%Y%m%d%H%M%S}")
            else:
                hook.rename(local)
            status = "installed (the existing pre-push hook, e.g. ud's, now runs first as pre-push.local)"
        elif old == text:
            status = "unchanged"
        else:
            status = "updated"
    if status != "unchanged":
        hook.write_text(text, **TEXT)
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return status


def write_template(src: Path, dst: Path, subs: dict) -> str:
    if dst.exists():
        return "kept"
    dst.parent.mkdir(parents=True, exist_ok=True)
    text = src.read_text(encoding="utf-8")
    for k, v in subs.items():
        text = text.replace("{" + k + "}", v)
    dst.write_text(text, **TEXT)
    return "created"


def copy_kit(root: Path, kit_dir: str) -> dict:
    ch = {}
    for src in sorted(KIT.rglob("*")):
        if not src.is_file():
            continue
        relp = src.relative_to(KIT).as_posix()
        dst = root / ("cmake/VitaPort.cmake" if relp == "VitaPort.cmake" else f"{kit_dir}/{relp}")
        if dst.exists():
            ch[dst.relative_to(root).as_posix()] = "kept" if dst.read_bytes() == src.read_bytes() else "kept (differs from the kit: yours wins)"
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        ch[dst.relative_to(root).as_posix()] = "created"
    return ch


def init(title_id: str | None = None, name: str | None = None, kit: bool = False, kit_dir: str = "platform/vita/vitaport",
         hook: bool = True) -> dict:
    root = project_root()   # the git top level, or a sub-folder that already holds vita.toml
    ud = is_ud_repo(root)
    name = name or root.name
    tid = title_id or suggest_title_id(name)
    res: dict = dict(repo=str(root), kind="ud" if ud else "cmake", changes={}, problems=title_id_problems(tid))
    subs = dict(date=dt.date.today().isoformat(), name=name, title_id=tid, data_folder=data_folder_name(name),
                assets="external" if ud else "embedded", kind=res["kind"], pc_build_dir="build",
                asset_source="data" if ud or (root / "data").is_dir() else "assets")
    ch = res["changes"]
    ch[".gitignore"] = gitignore(root)
    for fname in ("vita.toml", "PORT_PLAN.md", "PORTLOG.md"):
        ch[fname] = write_template(TEMPLATES / fname, root / fname, subs)
    if kit:
        ch.update(copy_kit(root, kit_dir))
    ch["pre-push hook"] = install_hook(root) if hook else "skipped (--no-hook)"
    try:
        import tomllib
        tid = tomllib.loads((root / "vita.toml").read_text(encoding="utf-8")).get("app", {}).get("title_id") or tid
    except (OSError, ValueError):
        pass
    res["problems"] = title_id_problems(tid)
    if ud:
        res["ud"] = {k: (root / k).exists() for k in ("DECOMP_PLAN.md", "DECOMPLOG.md", "decomp/progress.json", "ud.toml", "data")}
        res["ud"]["platform_layer"] = next((p.relative_to(root).as_posix() for p in (root / "src" / "platform", root / "platform")
                                            if p.is_dir()), None)
    res["title_id"] = tid
    res["next"] = "vita scan, then vita tools check" + (" (read DECOMP_PLAN.md and decomp/progress.json first)" if ud else "")
    return res


def main(a):
    r = init(a.title_id, a.name, a.kit, a.kit_dir, not a.no_hook)
    if a.json:
        emit_json(r)
        return PROBLEM if r["problems"] else OK
    print(f"port repo: {r['repo']}  ({'universal-decompiler reconstruction' if r['kind'] == 'ud' else 'CMake project'})")
    for k, v in r["changes"].items():
        print(f"  {k:40} {v}")
    if r.get("ud"):
        u = r["ud"]
        print("  ud repo: " + ", ".join(f"{k} {'yes' if v else 'no'}" for k, v in u.items() if k != "platform_layer")
              + f"; platform layer: {u['platform_layer'] or 'not found'}")
    for p in r["problems"]:
        print(f"WARNING: {p}")
    print(f"title ID: {r['title_id']}" + ("" if r["changes"].get("vita.toml") == "kept" else " (a proposal until the intake confirms it)"))
    print(f"next: {r['next']}")
    return PROBLEM if r["problems"] else OK


def register(sub):
    import argparse
    p = sub.add_parser("init", help="set up the repo for the port (vita.toml, PORT_PLAN.md, PORTLOG.md, .gitignore, guard)",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--title-id", help="4 uppercase letters + 5 digits (default: derived from the name)")
    p.add_argument("--name", help="display name (default: the repo folder's name)")
    p.add_argument("--kit", action="store_true", help="also copy the vitaport kit and cmake/VitaPort.cmake")
    p.add_argument("--kit-dir", default="platform/vita/vitaport", help="where the kit goes (default platform/vita/vitaport)")
    p.add_argument("--no-hook", action="store_true", help="don't install the pre-push guard (e.g. a project inside a bigger repo)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=main)
