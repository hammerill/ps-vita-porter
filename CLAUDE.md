@AGENTS.md

## Claude Code specifics
- Installed as a plugin, the skills are namespaced (`/ps-vita-porter:port-to-vita`) and a SessionStart hook
  (`hooks/hooks.json`) puts `vita` on PATH.
- In a clone, `.claude/settings.json` adds the same PATH hook, and `.claude/skills` is a copy of `skills/`.
- Look at screenshots `vita sim` and `vita emu` write (`build-sim/vita-sim/<time>/*.png`) with the Read tool.
