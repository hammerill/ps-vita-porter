#!/usr/bin/env bash
# SessionStart hook: put ps-vita-porter's bin/ on PATH for every later Bash call in the session,
# so skills can just say `vita ...`. Arg 1: the toolkit root (plugin root or the cloned repo).
# Derived from universal-modder's hooks/add-to-path.sh (MIT, Copyright (c) 2026 Rehan and universal-modder contributors),
# via universal-decompiler.
root="${1:-${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-}}}"
# Windows (Git Bash): the root arrives as C:/..., whose colon would split PATH into "C" and "/Users/...".
[ -n "$root" ] && command -v cygpath >/dev/null 2>&1 && root="$(cygpath -u "$root")"
[ -n "$root" ] && [ -n "${CLAUDE_ENV_FILE:-}" ] && [ -x "$root/bin/vita" ] || exit 0
grep -qs "ps-vita-porter-path" "$CLAUDE_ENV_FILE" && exit 0
printf 'export PATH="%s/bin:$PATH"  # ps-vita-porter-path\n' "$root" >> "$CLAUDE_ENV_FILE"
exit 0
