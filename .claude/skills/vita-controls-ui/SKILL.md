---
name: vita-controls-ui
description: Design and implement a PS Vita port's controls and the UI around them - mapping every PC action to the Vita's buttons and two sticks (no L2/R2/L3/R3), front touch for menus/direct interaction/virtual buttons, rear touchpad zones that never fire while gripping, optional gyro only where it fits, the system confirm button (Cross or Circle), original button glyphs (never Sony's), a remapping menu, touch hints, and the vitaport kit's input API shared with the PC simulation. Use when choosing or changing a Vita control scheme, adding touch or gyro, replacing keyboard/mouse prompts, or when the user reports a control problem.
---

# Vita controls and UI

Decisions come from the intake (PORT_PLAN.md, Controls and In-game UI); rules and genre patterns are in
`port-to-vita/references/controls.md`. This skill is how to build them.

## The input path
1. Read the Vita once per frame through the kit: `vp_poll(&in)` (`vitaport.h`): `buttons/pressed/released`
   (VP_CROSS... same bits as SceCtrl; the shoulders are `VP_L`/`VP_R`), sticks `lx/ly/rx/ry` (0-255),
   `front[]`/`rear[]` touches (normalised 0..1), `accel[]`/`gyro[]`.
2. Translate to the game's own actions in **one** function shared by the Vita backend and the PC simulation
   profile (the example: `src/platform/vita_input.h`, `platform::vita::translate`). Game code only sees actions.
3. Confirm/cancel: `vp_confirm_button()` / `vp_cancel_button()` (system setting). Never hard-code Cross.
4. Remappable actions: a table of `{name, mask, glyph}` and an index saved in `ux0:data/<name>/` (the example's
   Dash binding).

## Touch
- Map a touch to game coordinates through the same rectangle the renderer uses (`vp_fit`), so taps hit what's
  drawn even with pillarbox bars.
- Taps = new touches (edge), not held ones. Drag/scroll only where the original had mouse drag.
- Rear touch: off by default; when enabled, act only after a hold (~250 ms) inside a zone, two zones max, with an
  options toggle; never for destructive actions.
- Disable touch sampling you don't use (`vp_config.enable_front_touch/enable_rear_touch/enable_motion`).

## Gyro
Only when it fits (shooter fine aim, optional racing steering), off by default, with sensitivity. Use
`gyro[]` (rad/s) integrated per frame for aim deltas; recentre on a button.

## Glyphs and prompts
- Draw your own glyphs (shapes + letters) or use CC0 sets; the example draws Cross/Circle/Square/Triangle/L/R/
  Start/Select in `tools/make_art.py`. Never Sony's artwork or fonts.
- The confirm prompt shows the glyph of `vp_confirm_button()`; the cancel prompt the other one.
- Replace every keyboard/mouse prompt string ("Press Enter", "Click") on the Vita path.

## Remapping menu
In the game's options if it has one; else an overlay on Start+Select. Show the current binding with its glyph,
cycle through allowed buttons, save immediately, and refuse bindings that collide with confirm/cancel in menus.

## Check it
`vita sim --input <script>` presses exactly the buttons you list (`tap confirm`, `lstick 255 128`,
`touch 480 300`, `rtouch ...`) and screenshots each screen; run with `--enter circle` too. The hardware checklist
lists every mapping one per line.
