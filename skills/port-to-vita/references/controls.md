# Controls, touch, rear touch, gyro, glyphs, remapping

## The Vita's inputs
D-pad, Cross, Circle, Square, Triangle, L, R, Start, Select, two analog sticks; front touchscreen; rear
touchpad; motion. **No L2/R2/L3/R3.** The PS button belongs to the system. PS TV has none of the touch/motion
inputs: every action needs a button path.

## Rules
- Every original action gets a home. Recover L2/R2/L3/R3-style actions with: L/R (when the triggers were the
  main shoulder actions), L/R + face-button combos for rare actions, front-touch virtual buttons, a radial/menu,
  or deliberate rear-touch zones.
- **Confirm/cancel follow the system setting** (Cross or Circle, `vp_confirm_button()` / `vp_cancel_button()`),
  never hard-coded. Not asked at intake.
- **Every optional feature has an "off"**: front touch, rear touch, gyro, both in the intake and in-game options.
- **Nothing against the spirit of the game.** Gyro aiming fits a shooter; it doesn't fit a menu-driven RPG.
  Touch-to-move doesn't fit a precision platformer.
- **Rear touch must never fire while gripping.** Default off. When used: only a held press (e.g. 250 ms) inside a
  zone, two zones max (left/right halves of the pad), and an option to disable. Never map destructive actions
  (quit, delete, sell) to it.
- Front touch: tap = click/select in menus; direct interaction for pointer-driven games; virtual buttons only
  when physical buttons run out, drawn subtly and only while usable.
- Glyphs: original drawings or CC0 art for Cross/Circle/Square/Triangle/L/R/Start/Select (the example draws its
  own in `tools/make_art.py`). **Never Sony's artwork.** Prompts follow the confirm-button setting.
- A remapping menu: in the game's options if it has one, else a small overlay (e.g. Start+Select). Saved in
  `ux0:data/<name>/`.

## Mapping patterns by genre
| Genre | Move | Camera / aim | Main actions | Notes |
|---|---|---|---|---|
| Platformer | left stick + D-pad | - | Cross jump, Square attack/run | no touch in gameplay; D-pad must be precise |
| Twin-stick / arcade | left stick | right stick aims | R fire, L special/dash | gyro: no |
| FPS / TPS shooter | left stick | right stick (+ optional gyro, off by default) | R fire, L aim, Cross jump, Circle crouch, Square reload, Triangle swap | L3 sprint -> L+Cross or double-tap; R3 melee -> rear zone (hold) or Circle |
| RPG / menu-driven | left stick + D-pad | right stick camera if 3D | confirm/cancel, Triangle menu, Square context | front touch for menus and inventories; gyro: never |
| Point-and-click / strategy | right stick cursor | left stick scroll | confirm = click, cancel = right click | front touch = direct interaction; L/R cycle units; Select = map |
| Racing | left stick steer | - | R accelerate, L brake, Square handbrake | analog triggers become digital: ramp the input over ~150 ms; gyro steering only as an option |
| Puzzle | D-pad / stick | - | confirm/cancel, L/R rotate | front touch direct manipulation works well |

Keyboard -> Vita defaults `vita scan` suggests: WASD/arrows -> left stick + D-pad; Space -> Cross; Enter ->
confirm; Escape -> Start (pause) / cancel in menus; Shift -> L; Ctrl -> R or Circle; Tab/M -> Select; E/F ->
Square; Q -> Triangle or L; 1-9 -> D-pad cycling or a touch hotbar; F-keys -> options menu entries.

## Analog details
- Dead zone ~0.2 on each axis (`(v - 128) / 127`), radial if the game moves in 2D.
- `SCE_CTRL_MODE_ANALOG_WIDE` (the kit sets it) for the full stick range.
- Mouse look -> right stick: map stick deflection to angular *velocity* (with acceleration), not position;
  expose sensitivity and invert-Y.

## Testing without a Vita
`vita sim` uses Vita3K's keyboard layout (arrows, WASD, IJKL, Z/X/C/V, Q/E, Enter, Backspace); front touch =
left click, rear touch = Left Alt + left click, gyro = numpad. Script exact sequences with `vita sim --input`.
