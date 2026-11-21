# AI Agent Guidelines (`AGENTS.md`)

This file defines repository boundaries, build/test commands, non-negotiable architectural invariants, and coding rules for automated coding agents working in this repository.

## Project Map

- `.env.example` / `.env`: Single source of truth for `MONGO_VERSION`, `PYTHON_VERSION`, credentials, archive URL/filename, and host/port overrides.
- `docker-compose.yml`: Defines `mongodb` (`mongo:${MONGO_VERSION}`) and opt-in `configurator` (`profiles: ["setup"]`) using strict `${VAR:?error}` validation for versions, credentials, and archive configuration.
- `configurator/Dockerfile`: Multi-stage build copying official `/usr/bin/mongorestore` and `/usr/bin/bsondump` from `mongo:${MONGO_VERSION}` into `python:${PYTHON_VERSION}-slim` with `libgssapi-krb5-2`.
- `configurator/src/core.py`: Pure domain logic (cache discovery, gzip magic-byte detection, offline `bsondump` archive introspection, optional `KNOWN_DATASET_METADATA` enrichment with custom fallback, selection parser, streaming downloader, atomic key-value `seed.conf` persistence). **Must never import `rich`.**
- `configurator/src/ui.py`: Pure presentation layer built with `rich`. **Keep business logic out of this file.**
- `configurator/src/main.py`: Thin CLI entrypoint (`run()`) coordinating archive selection, dynamic introspection, UI rendering, and `seed.conf` generation.
- `configurator/tests/test_core.py`: Offline `unittest` suite validating gzip detection, multi-archive cache discovery, mocked introspection with fallback metadata, selection parsing, atomic LF writes, `0o644` permissions, and mocked HTTP streaming.
- `init-db/01-restore.sh`: First-boot Bash hook sourced by `mongo`'s `/usr/local/bin/docker-entrypoint.sh`; safely parses key-value `seed.conf` without `source`/`eval` and invokes `mongorestore`.
- `docs/`: System architecture (`ARCHITECTURE.md`) and ADRs (`docs/adr/0001-*`, `docs/adr/0002-*`).

## Build, Run & Verification Commands

```bash
# Create .env before running Docker Compose commands (required by fail-fast validation)
cp .env.example .env

# Verify strict Compose configuration resolution
docker compose config -q

# Run Python unit tests (fast, zero network access)
python -m unittest discover -s configurator/tests -v

# Syntax-check all Python files
python -m compileall -q configurator/src configurator/tests

# Validate Bash syntax for the MongoDB init hook
bash -n init-db/01-restore.sh
docker run --rm --entrypoint bash -v "${PWD}/init-db:/init-db:ro" mongo:8.0 -n /init-db/01-restore.sh

# Build & run interactive configurator container
docker compose build configurator
docker compose run --rm configurator

# Non-interactive configurator run
docker compose run --rm configurator --select 1,8

# Start MongoDB and inspect seeding logs
docker compose up -d
docker compose logs -f mongodb
```

## Non-Negotiable Architectural Invariants

1. **Strict `.env` Enforcement (No Hardcoded Credentials or Runtime Versions):** Never add hardcoded fallback defaults for `MONGO_VERSION`, `PYTHON_VERSION`, `MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`, `MONGO_SAMPLE_URL`, `ARCHIVE_FILENAME`, `MONGO_CPU_LIMIT`, or `MONGO_MEMORY_LIMIT` inside `docker-compose.yml` or `configurator/Dockerfile`. Only `MONGO_HOST` and `MONGO_PORT` may carry fallback defaults.
2. **Never Hardcode Selectable Datasets:** Never replace dynamic `.archive` introspection with a fixed list of selectable datasets. Always discover restorable databases dynamically from the selected archive and fall back cleanly on uncatalogued custom databases.
3. **Never mount `/var/run/docker.sock`:** `configurator` must never invoke Docker commands, edit `docker-compose.yml`, or require elevated daemon access.
4. **Never parse `.archive` BSON payloads manually in Python:** Delegate binary decoding exclusively to the official MongoDB tools (`bsondump` / `mongorestore`) copied cleanly in `configurator/Dockerfile`.
5. **Sourced Shell Hook Safety:** Because `mongo`'s `docker-entrypoint.sh` loads `/docker-entrypoint-initdb.d/*.sh` using `.` (`source`), `init-db/01-restore.sh` MUST keep its logic inside `main()`, parse `seed.conf` safely without `eval` or `source`, and use `return 0` / `return 1` instead of top-level `exit`.
6. **Atomic Cross-OS File Contracts:**
   - Write `init-db/seed.conf` via a `.tmp` sibling file + `os.fsync()` + `os.chmod(..., 0o644)` + `os.replace()`.
   - Always enforce `newline="\n"` (LF line endings).
   - Stream downloads to `.tmp` first and clean up on errors or `KeyboardInterrupt`.
7. **Module Separation:** `configurator/src/core.py` must contain zero `rich` imports and remain testable without a TTY.

## Strict Language Policy

- **Inline `#` comments ONLY** inside Python (`*.py`), Bash (`init-db/01-restore.sh`), `configurator/Dockerfile`, `docker-compose.yml`, and `.env.example` MUST be written strictly in **Spanish**, explaining *why* non-obvious engineering choices exist.
- **Everything else** MUST be written strictly in **English**: identifiers, type names, docstrings (`"""..."""`), Rich UI messages, exception strings, logs, GitHub templates, ADRs, and all Markdown files.
