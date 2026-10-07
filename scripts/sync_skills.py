"""Copy skills/ (the source of truth) to .claude/skills and .agents/skills, where agents look in a clone.

    python scripts/sync_skills.py           # refresh the copies
    python scripts/sync_skills.py --check   # exit 1 if a copy differs (CI and tests/test_repo.py)

Real copies, not symlinks: Windows clones turn symlinks into text files.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "skills"
COPIES = [ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"]


def tree(d: Path) -> dict[str, bytes]:
    return {p.relative_to(d).as_posix(): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()} if d.is_dir() else {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    src = tree(SRC)
    bad = 0
    for dst in COPIES:
        same = not dst.is_symlink() and tree(dst) == src
        if a.check:
            if not same:
                print(f"{dst.relative_to(ROOT)} differs from skills/: run python scripts/sync_skills.py")
                bad += 1
            continue
        if dst.is_symlink() or dst.is_file():
            dst.unlink()
        elif dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(SRC, dst)
        print(f"copied skills/ -> {dst.relative_to(ROOT)}")
    if a.check and not bad:
        print(f"skill copies in sync ({len(src)} files)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
