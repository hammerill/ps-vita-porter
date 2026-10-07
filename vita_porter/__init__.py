"""ps-vita-porter: the `vita` CLI an AI coding agent uses to port a C/C++ game whose full source is available
(typically a universal-decompiler reconstruction) to PS Vita as a .vpk. It never decompiles anything.

Commands (see `vita <command> --help`; every reporting command takes --json):
  init      set up the project repo for the port: vita.toml, PORT_PLAN.md, PORTLOG.md, .gitignore (+ --kit)
  scan      analyse the source project: build system, dependencies vs vdpm, graphics/input APIs, control scheme,
            resolutions, 64-bit/SIMD, threads, file paths, assets and memory; blockers and intake questions
  tools     check VitaSDK (native or Docker), vdpm packages, vitaGL, ffmpeg, pngquant, Vita3K, vitacompanion
  build     build the .vpk with VitaSDK (native or Docker); full log + short error summary
  livearea  make and check sce_sys/ (icon0, pic0, bg0, startup, template.xml)
  vpk       check a .vpk: structure, param.sfo, title ID, unsafe flag, size, assets vs the assets mode
  assets    convert assets per the plan into build-vita/assets (textures, audio) and check them
  sim       build and run the PC "Vita simulation" profile (960x544, memory cap, Vita controls)
  emu       install and run the .vpk in Vita3K: logs, screenshots, stop at the timeout
  deploy    upload the .vpk / eboot.bin / external assets to a real Vita (vitacompanion FTP)
  launch    start the app on the Vita          kill   quit it
  logs      capture network logs from the app  core   fetch and parse a crash dump
  publish   refuse to publish .vpk files, converted or extracted assets, the original binary
  kb        the knowledge base of Vita ports: search, write, check, PR

Exit codes: 0 ok, 1 problem found, 2 usage error.
"""

__version__ = "0.1.0"
