# Files and paths

## Where things live
| What | Embedded assets | External assets |
|---|---|---|
| Read-only game data | `app0:<vpk_dir>/...` (inside the installed .vpk) | `ux0:data/<data_folder>/<vpk_dir>/...` (copied there by the user) |
| Saves, settings, logs | `ux0:data/<data_folder>/...` | same |
| Shader cache (vitaGL) | `ux0:data/shader_cache/...` | same |
`app0:` is read-only for the running app. Never write anywhere else (`ur0:`, `vs0:` ...).
The kit's `vp_asset_path(rel)`, `vp_save_path(rel)` (creates folders) and `vp_translate("app0:...")` produce the
right path for the Vita and for the PC simulation (where `app0:` = `build-sim/app0/`, `ux0:` = `build-sim/ux0/`).

## Path translation rules for PC code
- Route every path through the platform layer; no literal `C:\`, `~`, `getenv("HOME")`, `%APPDATA%`,
  `SDL_GetPrefPath` or `GetModuleFileName` in game code on the Vita path.
- Use `/` separators. The Vita's `ux0:` (exFAT) is **case-insensitive but case-preserving**; `app0:` follows the
  .vpk's names. Linux PCs are case-sensitive: a PC build that works on Linux has consistent case already; one that
  only ran on Windows may not (`vita sim` on Linux catches those).
- No `chdir`: the working directory isn't meaningful on the Vita; build absolute Vita paths.
- stdio (`fopen`) and POSIX calls go through newlib to the Vita's file API for `ux0:`/`app0:` paths. Directory
  iteration and `std::filesystem` depend on what the toolchain's newlib/libstdc++ implement: test them early (or
  use `sceIoDopen`/`sceIoDread` behind the platform layer).
- File sizes: FAT32-formatted cards (SD2Vita) limit files to 4 GiB; keep single files well below.

## Saves
- Default (not asked): `ux0:data/<data_folder>/`. Keep the PC save format if its layout uses fixed-size types;
  `long`/pointers in binary saves change size on the 32-bit Vita.
- Write atomically (temp file + rename): the user can close the app from LiveArea at any time.

## External assets
`vita assets convert` writes `build-vita/assets/`; the user copies it to `ux0:data/<data_folder>/<vpk_dir>/`
(VitaShell over USB/FTP, or `vita deploy --assets` once a console is connected). The game must say clearly which
file is missing and where it expects it, instead of crashing.
