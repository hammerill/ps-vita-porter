---
kind: topic
title: "Building .vpk files with VitaSDK in Docker"
family: tooling
tags: [vitasdk, docker, ci, vdpm, sdl2]
tools: ["vitasdk/vitasdk:latest (VitaSDK 2026.08, digest fd82d88f)", "Docker 29.7.2", "vita 0.1.0"]
status: working
agents: ["Claude Code (Opus 5.5)"]
humans: []
date: 2026-10-07
links: ["https://hub.docker.com/r/vitasdk/vitasdk", "https://github.com/vitasdk/docker"]
---

# Building .vpk files with VitaSDK in Docker

> When there's no native VitaSDK (Windows without WSL, CI), the official `vitasdk/vitasdk` image builds the same
> .vpk. `vita build --docker` runs CMake inside it; the example's CI job does too. The image and a native install
> differ in ways that matter for SDL and vitaGL.

## When to use it
CI, Windows hosts, or to reproduce a build on a clean toolchain. `vita build` picks it automatically when
`$VITASDK` isn't a valid SDK.

## How
- Tags (2026-09-25): `latest` (full: core + ~130 vdpm packages, ~1.6 GB), `minimal` (core only), and
  `*-non-root` variants. `VITASDK=/usr/local/vitasdk` inside; CMake 3.28, ninja, make, python3; no ffmpeg or
  pngquant (LiveArea images are made on the host).
- `vita build --docker` = `docker run --rm -v <repo>:/src -w /src -u <uid>:<gid> -e HOME=/tmp vitasdk/vitasdk:latest
  sh -c "cmake -S /src -B /src/build-vita -DCMAKE_TOOLCHAIN_FILE=$VITASDK/share/vita.toolchain.cmake ... && cmake --build ..."`.
- vita never pulls the image itself (`vita tools check` prints `docker pull vitasdk/vitasdk:latest`).

## Gotchas
1. **SDL2 links differently in Docker and natively.** **Cause:** the `latest` image ships `sdl2_vitagl` (SDL2 with
   the vitaGL video backend) while a typical native install has plain `sdl2`; they conflict in vdpm. **Fix:** use
   SDL only for audio/input and call `vglInit` yourself (builds with both), or require `sdl2_vitagl` explicitly
   when you need `SDL_GL_CreateContext`.
2. **vitaGL versions differ.** **Cause:** image r1448 vs native r1488 on the same day. **Fix:** don't depend on
   brand-new vitaGL symbols without checking both (`vglEnd` exists in neither, by the way).
3. **Build outputs owned by root.** **Cause:** the image runs as root. **Fix:** `-u $(id -u):$(id -g)` and
   `HOME=/tmp` (what `vita build --docker` does).
4. **CMake cache from the other backend.** **Cause:** a cache configured natively has host paths, a Docker one
   `/src` paths. **Fix:** `vita build` remembers the backend per build folder (`.vita-backend`) and starts fresh
   when it changes.

## Seen in
`examples/lumen-drift` (built natively and with `--docker`, both pass `vita vpk check`), `.github/workflows/test.yml`.
