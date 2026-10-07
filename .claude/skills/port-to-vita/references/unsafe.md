# The unsafe flag

`vita_create_self` makes a **safe** eboot unless `UNSAFE` is given (`vita-make-fself -s`). In the SELF the
difference is the app's authid: `0x2F00000000000002` safe, `0x2F00000000000001` unsafe (`vita vpk check` reads it).
vita-make-fself's own help: "A safe eboot.bin does not have access to restricted APIs and important parts of the
filesystem."

## What it costs
- The user must allow unsafe homebrew on their console (HENkaku's settings) and trust the app with more access.
- More access means more damage if the port has a bug that writes where it shouldn't.
- A safe build is the default and what users expect from a game port.

## What tends to need it
- Restricted system APIs and memory block types beyond the `SCE_KERNEL_MEMBLOCK_TYPE_USER_*` ones a normal app uses.
- Writing outside the app's own areas (`ux0:data/<name>/` works safe).
- Loading/using kernel helpers (e.g. kubridge, used by "so-loader" ports of Android games for exception handling
  and memory protection): such ports ship unsafe.

## This toolkit's policy (PORT_PLAN.md, technical plan)
**Heap extension, extended memory and overclocking are decided only when analysis or profiling shows they're
needed.** If any is chosen, `PORT_PLAN.md` records why (the measurement), and records it together with the unsafe
decision, so the user agrees to all of it at once:
- heap extension: `_newlib_heap_size_user` (works in a safe app as long as MAIN has room; memory.md);
- extended memory: `ATTRIBUTE2=12` (`[app] extended_memory = true`; reinstall needed);
- overclocking: `scePowerSetArmClockFrequency(444)` & co (hardware.md);
- `unsafe = true` in vita.toml only with a written reason; `vita build` passes `VITA_UNSAFE`, `vitaport_package`
  calls `vita_create_self(... UNSAFE)`, and `vita vpk check` fails if the eboot doesn't match vita.toml.
The hardware checklist then says the user must enable unsafe homebrew.
