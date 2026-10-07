<!-- Field note PR? Most of this is filled in by `vita kb pr`. -->

**What:** <!-- one line: game/topic + what was ported or learned, or the tool/skill change -->

**Checklist**
- [ ] `vita kb check` passes (field notes) / `uv run pytest` and `uv run ruff check` pass (code)
- [ ] `vita kb index` regenerated (field notes)
- [ ] no game assets, `.vpk` files, decompiled code, large address tables or secrets
- [ ] nothing that bypasses DRM or ownership checks
- [ ] versions, verification (simulation / Vita3K / hardware) and what was NOT verified are written down
- [ ] skills edited in `skills/` and synced (`python scripts/sync_skills.py`)
- [ ] authored by (agent + model / human): <!-- e.g. Claude Code (Opus 5.5) with @someone -->
