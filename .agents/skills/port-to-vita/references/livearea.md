# LiveArea: what `vita livearea make/check` produce and enforce

Based on hammerill's gist "LiveArea Specs" (https://gist.github.com/hammerill/64411eebf071b93396b7d310ba8d6776),
**with its colour bug fixed**: the gist converts with `-pix_fmt ya8`, which is **grayscale + alpha** and turns
every image gray. `rgb24` (and `rgba` for the startup image) replace `ya8` here. Wrong images make the Vita
refuse the install with **error 0x8010113D**.

## Layout
```
sce_sys/
├── icon0.png                  128x128, no alpha
├── pic0.png                   960x544, no alpha, indexed, exactly a 256-colour palette
└── livearea/contents/
    ├── bg0.png                840x500, no alpha
    ├── startup.png            280x158, alpha allowed (the only layer that supports it)
    └── template.xml
```
All images: 8 bits per channel, indexed (palette) PNGs.

## Pipeline (`vita livearea make`)
Scale filter: `neighbor` only for pixel-art sources (`--pixel-art`), otherwise `lanczos`. Sources are cropped to
fill by default (`--fit cover`), or padded (`--fit pad`) or stretched (`--fit stretch`).
- `icon0`, `bg0`: `ffmpeg -i src -vf scale=W:H:flags=F -pix_fmt rgb24 tmp.png`, then `pngquant tmp.png -o out.png`.
- `startup`: the same with `-pix_fmt rgba` (transparency survives as a tRNS chunk).
- `pic0`: scale with `-pix_fmt rgb24`, then `palettegen=max_colors=256:reserve_transparent=0` + `paletteuse`
  (exactly 256 colours, no transparent entry). **Never pngquant `pic0`.**
- pngquant writes **1-, 2- or 4-bit** PNGs when an image has few colours (measured: a flat icon became 1-bit, a
  12-colour image 4-bit). `make` re-expands them to 8-bit (same palette, same pixels).
- `template.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<livearea style="a1" format-ver="01.00" content-rev="1">
    <livearea-background><image>bg0.png</image></livearea-background>
    <gate><startup-image>startup.png</startup-image></gate>
</livearea>
```
`style` is `a1` (startup image centred) or `psmobile` (on the right).

## CMake
`vita_create_vpk(... FILE sce_sys sce_sys)`; the destination `sce_sys` is fixed. `vitaport_package()` in
`cmake/VitaPort.cmake` adds it (and warns when the folder is missing). `vita-pack-vpk -a <dir>=<dest>` adds a
folder recursively.

## What `vita livearea check` (and `vita vpk check`) verify
- exact dimensions; 8 bits per channel; an indexed palette; no alpha (no RGBA/gray+alpha, no tRNS) except in
  `startup.png`; exactly 256 colours in `pic0.png`; valid XML whose `style` is `a1`/`psmobile` and whose image
  references exist; the gist's grayscale+alpha output is rejected by name.

## Sources
- An original game: its own key art, logo and title screen (the example draws them in `tools/make_art.py`).
- A universal-decompiler repo: the game's own title screen, logo or key art from `data/` (extracted from the
  user's copy). Those LiveArea files then contain game art: they stay local like `data/`, and a `.vpk` built
  from them is never published.

## Hardware check (always in the test checklist)
The bubble shows `icon0`; opening it shows `bg0` with `startup.png` on the gate; `pic0` appears while the app
boots. Colours must match the sources (not gray), nothing cropped awkwardly, the name under the bubble right.
