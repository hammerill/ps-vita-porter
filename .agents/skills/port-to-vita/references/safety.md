# Safety rules, with their reasons

1. **Only software the user owns.** The port runs the user's own copy of the game; ps-vita-porter never downloads
   games, assets, firmware, keys or `libshacccg.suprx` (the user extracts that from their own console).
2. **Never bypass DRM or ownership checks.** Not in the PC source, not on the Vita. If the game checks a license,
   tell the user; don't patch it out.
3. **No decompiling here.** ps-vita-porter ports source that exists. An earlier project that tried to decompile a
   PC game and port it to the Vita at the same time failed: the two problems multiply. Incomplete source ->
   universal-decompiler first.
4. **Never commit or publish `.vpk` files that contain game assets, extracted assets, or the original binary.**
   A `.vpk` with embedded assets is a redistribution of the game. `vita publish check` (also the pre-push hook)
   fails on `.vpk`, `eboot.bin`, `*.self`/`*.velf`, crash dumps, `build-vita/`, `build-sim/`, converted assets,
   and in a universal-decompiler repo on `data/`, the original and files identical to it; there, `ud publish
   check` also runs, because the reconstruction itself must stay private (re3 was taken down by DMCA in 2021
   despite shipping no assets). A `.vpk` built from an original open-source game with its own assets is fine to
   share; that's the user's call.
5. **External assets keep distribution clean.** A `.vpk` built in external mode holds only the program and the
   LiveArea; but LiveArea images made from game art are game art: keep such a `.vpk` private too.
6. **Ask before installing or deleting anything**, and **before deploying to the console**. `vita tools check`
   prints install steps; it never installs (tools, vdpm packages, Docker images). `vita deploy` is a dry run
   without `--yes`. Nothing on the console is deleted by any `vita` command.
7. **Kill processes by exact PID only.** `vita sim` and `vita emu` only kill the process (group) they started.
   Never `pkill -f`: it matches your own shell.
8. **Field notes** never contain game assets, decompiled code, `.vpk` files or large address tables.
9. **Unsafe builds** only with a written reason (unsafe.md).
This is not legal advice.
