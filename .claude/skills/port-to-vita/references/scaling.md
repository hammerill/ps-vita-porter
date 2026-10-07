# Resolution and scaling

The Vita screen is **960 x 544** (1.765:1, not exactly 16:9). Decide at intake, from `vita scan`'s resolutions,
the art style and the GPU cost.

## Internal resolution
- **Native 960x544** when the game is resolution-independent (vector UI, 3D) and the GPU keeps up.
- **Lower internal resolution, upscaled** (e.g. 720x408, 640x362) for heavy 3D: render to an FBO, then draw it
  scaled to the screen. Decide from profiling (`vita emu`/hardware frame times), not up front.
- **The game's own resolution, scaled** for fixed-resolution 2D games (e.g. 640x480, 320x240): keep the game
  logic at its resolution and scale the final image (`vp_fit()` in the kit computes the rectangle).

## Aspect ratio (non-16:9 content)
| Policy | When | Notes |
|---|---|---|
| Letterbox / pillarbox | default for 4:3 and other ratios | 640x480 -> 725x544 with 117-pixel bars; bars black or a subtle border |
| Stretch | only if the user insists | distorts circles and pixel art |
| Crop | wide content whose edges carry no UI | check every screen for clipped UI |
`vp_fit(src_w, src_h, 960, 544, VP_FIT_ASPECT | VP_FIT_INTEGER | VP_FIT_STRETCH | VP_FIT_CROP)`.

## Pixel art
- **Integer scaling** keeps pixels square and even: 320x240 x2 = 640x480 in the middle of the screen. `vita scan`
  recommends it when the integer image fills at least 90% of the 544 lines.
- Otherwise **fit to height with nearest filtering** (uneven pixel widths are less visible at 2x+), or a
  "sharp bilinear" pass (integer prescale with nearest, then linear to the final size).
- Never compress pixel-art textures; filter `neighbor` in `vita assets convert` and `--pixel-art` in
  `vita livearea make`.

## UI and text on a 5-inch screen
- The screen is about 220 ppi held at ~30 cm: text below ~16 px tall at 544 lines is hard to read. After scaling
  640x480 to 725x544 everything grows by 1.13; scaling 1280x720 down to 960x540 shrinks UI by 0.75 and usually
  needs a UI scale option or larger fonts.
- Touch targets: at least ~48x48 pixels at 960x544 for fingers.
- Safe area: nothing important in the 2-3% at the edges (bezel and hands).

## Filtering
- Pixel art: `GL_NEAREST` for minification and magnification.
- Everything else: `GL_LINEAR` (+ mipmaps for 3D).

## Checks
`vita sim` renders in a 960x544 window exactly as on the Vita: look at the screenshots for bars, cropping, text
size and blur. The hardware checklist repeats it on the real screen.
