@AGENTS.md

## Quick Reminders for Claude Code

- Read `AGENTS.md` (imported above) before proposing edits.
- Keep `configurator/src/core.py` UI-free (`rich` imports forbidden).
- Remember the strict split: `#` inline comments in `.py` / `.sh` are Spanish; all docstrings, code identifiers, UI strings, and docs are English.
- Re-run `python -m unittest discover -s configurator/tests -v` after any Python edit.
