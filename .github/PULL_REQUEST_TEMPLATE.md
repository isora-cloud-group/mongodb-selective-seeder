## Summary

Describe the changes introduced in this Pull Request and link any related issue.

## Type of Change

- [ ] Bug fix
- [ ] New feature or dataset catalog addition
- [ ] Documentation or governance update
- [ ] Tests or refactoring

## Verification & Compliance Checklist

- [ ] Ran `python -m unittest discover -s configurator/tests -v` and all tests pass
- [ ] Validated `init-db/01-restore.sh` syntax (`bash -n`) and LF line endings
- [ ] Confirmed `configurator/src/core.py` contains zero `rich` imports
- [ ] Confirmed strict language policy: inline `#` comments in `.py` / `.sh` are in Spanish; all identifiers, docstrings, UI output, and docs are strictly in English
- [ ] Confirmed architectural invariants remain intact (no Docker socket mount, no Python binary `.archive` parsing, atomic LF + `0o644` writes)
