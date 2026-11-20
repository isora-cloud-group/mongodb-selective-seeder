# Contributing Guidelines

Thank you for helping improve this educational MongoDB lab repository. Please follow these engineering, style, and architectural standards before submitting a Pull Request.

## Development Environment Setup

You can run tests and linters either natively with Python 3.12+ or inside the `configurator` Docker image.

### Local Python Setup

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r configurator/requirements.txt
```

### Running Tests and Validation

```bash
# Run Python unit tests
python -m unittest discover -s configurator/tests -v

# Validate Bash syntax for the MongoDB init hook (POSIX / Git Bash / Docker)
bash -n init-db/01-restore.sh
```

If you have `shellcheck` installed locally, run:

```bash
shellcheck init-db/01-restore.sh
```

## Coding Standards

1. **Python Style & Typing:**
   - Follow PEP 8 formatting (`4`-space indentation, LF line endings).
   - Provide complete type annotations on all functions, methods, parameters, return values, and module constants (`from __future__ import annotations`).
   - Keep `configurator/src/core.py` completely free of `rich` imports so business logic remains testable in isolation.

2. **Shell Scripting (`init-db/`):**
   - Use `#!/usr/bin/env bash` and `set -euo pipefail`.
   - Store all file operations safely inside functions and never use `eval` or unquoted word splitting on user-controlled values.
   - Maintain LF (`\n`) line endings and executable permissions (`chmod +x`).

3. **Strict Language Policy:**
   - **Inline `#` comments** inside Python, Bash, `Dockerfile`, and Compose/env config files MUST be written strictly in **Spanish**, explaining *why* non-obvious decisions exist (not merely restating what the code does).
   - **Everything else** MUST be written strictly in **English**: identifiers, docstrings (`"""..."""`), CLI output, exception messages, and Markdown documentation.

4. **Architectural Invariants:**
   - Require `.env` values (`MONGO_VERSION`, `PYTHON_VERSION`, credentials, archive configuration) via `${VAR:?error}` without hardcoded fallbacks (only `MONGO_HOST` and `MONGO_PORT` may carry defaults).
   - Never hardcode the list of selectable datasets; inspect `.archive` files dynamically via official `bsondump` / `mongorestore`.
   - Never mount `/var/run/docker.sock` inside the `configurator` service.
   - Never implement custom BSON binary parsers in Python.
   - Always write generated contract files (`init-db/seed.conf`) atomically with `newline="\n"` and `0o644` permissions.

## Pull Request Workflow

1. Fork the repository and create a descriptive feature branch from `main` (for example, `feat/add-custom-dataset` or `fix/archive-retry`).
2. Add or update unit tests in `configurator/tests/` for any behavioral change.
3. Update `CHANGELOG.md` under an `## [Unreleased]` section when introducing user-facing changes.
4. Open a Pull Request and complete every item in [the PR template](.github/PULL_REQUEST_TEMPLATE.md).
