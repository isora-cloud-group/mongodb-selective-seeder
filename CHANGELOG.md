# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Strict `.env` Parameterization:** Removed hardcoded image versions and credential fallbacks from `docker-compose.yml` and `configurator/Dockerfile`, enforcing explicit `.env` configuration via `${VAR:?error}` syntax (retaining defaults solely for `MONGO_HOST` and `MONGO_PORT`).
- **Multi-Stage Tooling in Configurator:** Refactored `configurator/Dockerfile` to copy official `mongorestore` and `bsondump` binaries from `mongo:${MONGO_VERSION}` into `python:${PYTHON_VERSION}-slim` with `libgssapi-krb5-2`.
- **Dynamic Archive Introspection:** Replaced the hardcoded dataset menu in `configurator/src/core.py` with offline `bsondump` prelude inspection (`inspect_archive`), gzip magic-byte auto-detection (`\x1f\x8b`), local `.cache/*.archive` multi-archive discovery, and `KNOWN_DATASET_METADATA` enrichment with `"Custom / Uncatalogued dataset"` fallback for arbitrary backups.
- **Key-Value Declarative Contract:** Updated `init-db/seed.conf` and `init-db/01-restore.sh` to exchange `ARCHIVE_FILE`, `ARCHIVE_GZIP`, and `DATASETS` safely without `eval` or `source`, supporting `--gzip` conditionally and `--archive` CLI selection.
- **Documentation & Governance:** Added [ADR 0002](docs/adr/0002-dynamic-archive-introspection.md) and updated `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`, and expanded unit tests in `configurator/tests/test_core.py`.

## [1.0.0] - 2026-11-20

### Added

- Declarative Contract Architecture separating the interactive configurator (`configurator/`) from MongoDB container initialization (`init-db/01-restore.sh`).
- `docker-compose.yml` running `mongo:8.0` with persistent `mongo_data` volume, read-only `./.cache` mount, and optional `setup` profile for the Python configurator.
- `configurator/src/core.py` providing immutable `Dataset` metadata, atomic streaming archive caching via `urllib.request`, and atomic LF-enforced `init-db/seed.conf` contract generation with `0o644` permissions.
- `configurator/src/ui.py` implementing the `rich` terminal UI with a catalog table, interactive prompt loop, and streaming download progress bar.
- `configurator/src/main.py` offering interactive execution plus `--select`, `--refresh`, `--cache-dir`, and `--init-db-dir` CLI options.
- Unit tests (`configurator/tests/test_core.py`) covering selection parsing, atomic writes, permissions, cache checks, and mocked download recovery.
- Cross-OS Git hygiene (`.gitattributes`, `.editorconfig`, `.gitignore`, `.cache/.gitkeep`, `init-db/.gitkeep`).
- Corporate open-source governance suite (`LICENSE`, `NOTICE`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`), GitHub templates (`.github/`), architecture documentation (`docs/`), and AI agent specifications (`AGENTS.md`, `CLAUDE.md`).
