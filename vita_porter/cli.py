"""`vita` command line: one entry point for every tool, so skills can say `vita <command> ...`.

Derived from universal-modder's um/cli.py (MIT, Copyright (c) 2026 Rehan and universal-modder contributors),
via universal-decompiler's ud/cli.py.
"""
from __future__ import annotations

import argparse
import importlib
import sys

from vita_porter import __doc__ as DOC, __version__

# command -> module (several hardware commands live in device.py)
COMMANDS = {
    "init": "init", "scan": "scan", "tools": "tools", "build": "build", "livearea": "livearea", "vpk": "vpk",
    "assets": "assets", "sim": "sim", "emu": "emu", "deploy": "device", "launch": "device", "kill": "device",
    "logs": "device", "core": "device", "publish": "publish", "kb": "kb",
}
GROUPS = list(COMMANDS)


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to a code page
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="vita", description=DOC, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"ps-vita-porter {__version__}")
    sub = ap.add_subparsers(dest="group", metavar="<command>")
    done = set()
    for mod in COMMANDS.values():
        if mod not in done:
            importlib.import_module(f"vita_porter.{mod}").register(sub)
            done.add(mod)
    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        # a group without a command: show that group's help; exit 2 (usage error)
        (sub.choices.get(args.group) if args.group else ap).print_help(sys.stderr)
        sys.exit(2)
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
