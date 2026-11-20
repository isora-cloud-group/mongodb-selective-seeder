<h1 align="center">MongoDB Selective Seeder</h1>

<p align="center">
  <strong>Selective dataset provisioning for MongoDB</strong><br>
  Declarative <code>.env</code>-driven Docker orchestration and dynamic <code>.archive</code> introspection via official MongoDB Database Tools
</p>

<p align="center">
  <a href="CHANGELOG.md"><img src="https://img.shields.io/badge/Version-1.0.0-0284c7.svg?style=flat-square" alt="Version 1.0.0" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache--2.0-059669.svg?style=flat-square" alt="License Apache-2.0" /></a>
  <a href=".env.example"><img src="https://img.shields.io/badge/Config-Strict%20.env-0f766e.svg?style=flat-square" alt="Strict .env Configuration" /></a>
  <a href="configurator/tests/test_core.py"><img src="https://img.shields.io/badge/Tests-12%20Passed%20%7C%20unittest-4338ca.svg?style=flat-square" alt="Unit Tests" /></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-334155.svg?style=flat-square" alt="Supported OS" />
  <img src="https://img.shields.io/badge/Runtime-Docker%20Compose%20v2-1e293b.svg?style=flat-square" alt="Docker Compose v2" />
</p>

---

## 1. Executive Summary & Operational Scope

**MongoDB Selective Seeder** is a cross-platform, containerized MongoDB provisioning environment engineered by **Isora Cloud Group** for university coursework, local engineering labs, and reproducible database workshops. It enables students and developers to inspect any MongoDB `.archive` backup—official Atlas sample datasets or custom `mongodump` archives—and selectively seed only the required databases on first boot without Atlas cloud accounts, host Python installations, or local database binaries.

### Why Engineering Teams & Instructors Choose MongoDB Selective Seeder

| Engineering Criterion | Manual Atlas / `mongorestore` Setup | MongoDB Selective Seeder (`v1.0.0`) |
| :--- | :--- | :--- |
| **Host Dependencies** | Local Python, `mongosh`, `mongorestore`, and OS-specific scripts | **Docker & Docker Compose v2 only** (zero host runtimes required) |
| **Archive Discovery** | Hardcoded dataset menus or manual CLI guesswork | **Dynamic offline `bsondump` introspection** + gzip magic-byte detection (`\x1f\x8b`) |
| **Configuration Discipline** | Implicit defaults and scattered environment overrides | **Strict fail-fast `.env` validation** (`${VAR:?error}`) for versions & credentials |
| **Container Security** | Elevated Docker socket mounts (`/var/run/docker.sock`) | **Zero Docker socket access**, read-only cache mount (`:ro`), `127.0.0.1` loopback |
| **First-Boot Idempotency** | Risk of duplicate documents or partial writes on restarts | **Native `/docker-entrypoint-initdb.d` contract** + `healthcheck`-gated `--wait` readiness |
| **Cross-OS Compatibility** | CRLF script failures and UID permission mismatches on Windows | **Atomic `.tmp` + `fsync` + `0o644` + LF (`\n`) contracts** enforced programmatically |

> **Scope Note:** Default credentials in `.env.example` are provided strictly for isolated local coursework on `127.0.0.1`. They must not be reused in shared, staging, or production deployments.

### Core Engineering Requirements
* **Declarative Contract Architecture:** Decouples the interactive setup container (`configurator`, profile `setup`) from the database runtime (`mongodb`), communicating exclusively through `.cache/*.archive` and `init-db/seed.conf`.
* **No Custom BSON Binary Parsers:** Delegates all archive decoding and selective namespace restoration (`--nsInclude`) to official `bsondump` and `mongorestore` binaries copied via a multi-stage Docker build from `mongo:${MONGO_VERSION}`.
* **Strict Domain/UI Separation:** Isolates testable business logic inside `configurator/src/core.py` (zero `rich` imports) from the IBM Carbon-inspired terminal presentation layer in `configurator/src/ui.py`.
* **Sourced Entrypoint Safety:** Encapsulates `init-db/01-restore.sh` inside `main()` with `return` semantics and array-built arguments without `eval` or `source` execution of `seed.conf`.

---

## 2. Architecture & Security Model

```mermaid
flowchart TD
    subgraph Layer1["1. Configuration & Setup Stage (Compose Profile: setup)"]
        Env[".env (Required Versions & Credentials)"]
        Wizard["configurator Container (Python + Rich + bsondump)"]
        Remote["MONGO_SAMPLE_URL (HTTPS Stream)"]
        Custom["Instructor / Custom .archive"]
    end

    subgraph Layer2["2. Local Cache & Declarative Contract"]
        Cache[("./.cache/*.archive (Atomic .tmp -> 0o644)")]
        Contract[("./init-db/seed.conf (Key-Value LF + 0o644)")]
    end

    subgraph Layer3["3. MongoDB Runtime & First-Boot Seeding"]
        Entrypoint["mongo:MONGO_VERSION (/usr/local/bin/docker-entrypoint.sh)"]
        InitHook["init-db/01-restore.sh (Safe Key-Value Parser)"]
        Restore["mongorestore [--gzip] --nsInclude"]
        Volume[("Named Volume: mongo_data (/data/db)")]
    end

    Env --> Wizard
    Env --> Entrypoint
    Remote -->|"Atomic Streaming"| Cache
    Custom --> Cache
    Wizard -->|"Gzip Magic Check + bsondump Prelude"| Cache
    Wizard -->|"Atomic LF Write"| Contract
    Cache -->|"Read-Only Mount :ro"| InitHook
    Contract -->|"Parsed via Bash Arrays"| InitHook
    Entrypoint -->|"First Boot Only - /data/db Empty"| InitHook
    InitHook --> Restore --> Volume
```

### Security Controls & Boundaries
1. **Zero Docker Socket Exposure:** The `configurator` service never mounts `/var/run/docker.sock` and holds zero privileges over the host Docker daemon.
2. **Read-Only Cache & Input Sanitization:** `mongodb` mounts `./.cache` as read-only (`:ro`). `init-db/01-restore.sh` validates `ARCHIVE_FILE` against `^[a-zA-Z0-9._-]+$` (rejecting `..` traversal) and database names against `^[a-zA-Z0-9_-]+$` before building `mongorestore` arrays.
3. **Strict `.env` Enforcement & Loopback Binding:** Missing `MONGO_VERSION`, `PYTHON_VERSION`, credentials, or archive configuration causes `docker compose` to fail immediately. Port `27017` binds strictly to `127.0.0.1` (`MONGO_HOST`) by default.
4. **Init-Gated Healthcheck:** `mongodb` checks that `/tmp/docker-entrypoint-temp-mongod.pid` is absent before reporting `healthy`, preventing clients like MongoDB Compass from connecting prematurely while `mongorestore` is still importing.

---

## 3. Quick Start & Operational Workflow

### Step 1: Create Local `.env` Configuration

```bash
cp .env.example .env
```

### Step 2: Inspect Archive & Select Databases

Run the interactive `configurator` wizard (scans `./.cache/` for existing `.archive` files or streams from `MONGO_SAMPLE_URL`):

```bash
docker compose run --rm configurator
```

For scripted, non-interactive selection:

```bash
docker compose run --rm configurator --select 1,7
```

### Step 3: Boot MongoDB & Wait for Readiness

Start `mongodb` and wait automatically until first-boot seeding finishes and the container reports `healthy`:

```bash
docker compose up -d --wait
```

To stream live `mongorestore` progress in another terminal:

```bash
docker compose logs -f mongodb
```

### Connecting to MongoDB

* **Connection URI (MongoDB Compass / PyMongo / VS Code):**
  ```text
  mongodb://admin:change_me_local_only@localhost:27017/?authSource=admin
  ```
* **Shell Verification (`mongosh` inside container, single quotes for PowerShell/macOS/Linux parity):**
  ```bash
  docker compose exec mongodb mongosh -u admin -p change_me_local_only --authenticationDatabase admin --quiet --eval 'db.adminCommand({ listDatabases: 1 }).databases.map(d => d.name)'
  ```

### Resetting & Re-Seeding Different Databases

MongoDB executes `/docker-entrypoint-initdb.d/` **only when `mongo_data` is empty**. Normal `stop`/`start` cycles preserve your data. To wipe the database volume and re-seed from cached archives:

```bash
# Warning: -v permanently deletes mongo_data while keeping ./.cache/*.archive intact
docker compose down -v
docker compose run --rm configurator
docker compose up -d --wait
```

---

## 4. Configuration & CLI Reference

### `.env` Environment Variables

| Variable | Required | Default (`.env.example`) | Description |
| :--- | :---: | :--- | :--- |
| `MONGO_VERSION` | Yes | `8.0` | Official `mongo` image tag and matching multi-stage tools source |
| `PYTHON_VERSION` | Yes | `3.12` | Official `python` slim image tag for `configurator` |
| `MONGO_INITDB_ROOT_USERNAME` | Yes | `admin` | Root administrator username created on first boot |
| `MONGO_INITDB_ROOT_PASSWORD` | Yes | `change_me_local_only` | Root administrator password created on first boot |
| `MONGO_SAMPLE_URL` | Yes | `https://atlas-education.s3.amazonaws.com/sampledata.archive` | Direct HTTP/HTTPS URL for `.archive` download |
| `ARCHIVE_FILENAME` | Yes | `sampledata.archive` | Local filename written inside `./.cache/` |
| `MONGO_HOST` | No | `127.0.0.1` | Host interface bound by Docker port mapping |
| `MONGO_PORT` | No | `27017` | Host TCP port mapped to container port `27017` |

### `configurator` CLI Options

| Flag | Default | Behavior |
| :--- | :--- | :--- |
| `--archive <filename>` | `ARCHIVE_FILENAME` | Select a specific `.archive` file inside `./.cache/` non-interactively |
| `--select <ids\|names\|all>` | Interactive prompt | Select comma-separated IDs, database names, or `all` without prompts |
| `--refresh` | `false` | Force fresh download from `MONGO_SAMPLE_URL` even if cached |
| `--cache-dir <path>` | `/app/.cache` | Override archive cache directory |
| `--init-db-dir <path>` | `/app/init-db` | Override output directory for `seed.conf` |

### Declarative Contract Schema (`init-db/seed.conf`)

```ini
# Declarative dataset seed contract consumed by init-db/01-restore.sh
# Regenerate via: docker compose run --rm configurator
ARCHIVE_FILE=sampledata.archive
ARCHIVE_GZIP=false
DATASETS=sample_mflix,sample_supplies
```

---

## 5. Dynamic `.archive` Introspection & Discovered Catalog

Any `mongodump --archive=...` file (uncompressed or `--gzip`) placed inside `./.cache/` or fetched via `MONGO_SAMPLE_URL` is inspected offline using `bsondump`. Standard Atlas databases receive enriched descriptions via `KNOWN_DATASET_METADATA`, while custom databases appear automatically with `"Custom / Uncatalogued dataset"`.

Below are the **9 databases** dynamically discovered inside the official Atlas `sampledata.archive`:

| Database Name | Collections | Enriched Description | Typical Academic Use Case |
| :--- | :---: | :--- | :--- |
| `sample_airbnb` | `1` | Vacation rental listings and guest reviews | Deeply nested documents and pricing filters |
| `sample_analytics` | `3` | Financial customers, accounts, and transactions | Relational modeling and multi-collection joins |
| `sample_geospatial` | `1` | Shipwrecks with GeoJSON coordinates and depth data | GeoJSON `2dsphere` indexes and `$near` queries |
| `sample_guides` | `1` | Solar system planets with orbital and physical metrics | Numeric comparisons, sorting, and projection drills |
| `sample_mflix` | `6` | Movies, user comments, theaters, and sessions | Aggregations, `$lookup` joins, and text search |
| `sample_restaurants` | `2` | New York City restaurants, grades, and neighborhoods | Geospatial indexing and nested array filters |
| `sample_supplies` | `1` | Retail store sales, customer demographics, and items | Grouping pipelines and array `$unwind` operations |
| `sample_training` | `7` | Routes, trips, grades, inspections, and posts | Indexing benchmarks and mixed schema queries |
| `sample_weatherdata` | `1` | Hourly atmospheric and meteorological telemetry | Time-series queries and geospatial coordinates |

---

## 6. Quality Assurance & Verification

The repository includes an offline `unittest` suite, Compose configuration validation, and Bash syntax verification:

```bash
# Run Python unit tests (zero network access required)
python -m unittest discover -s configurator/tests -v

# Validate Compose configuration and Bash hook syntax
docker compose config -q
docker run --rm --entrypoint bash -v "${PWD}/init-db:/init-db:ro" mongo:8.0 -n /init-db/01-restore.sh
```

```text
Test Summary: Passed=12, Failed=0, Total=12
- TestArchiveDiscoveryAndGzip : Gzip magic-byte detection, .cache/ scanning, filename traversal guard
- TestDynamicIntrospection    : bsondump JSON & mongorestore log parsing, custom fallback metadata
- TestSelectionAndContract    : ID/name deduplication, atomic LF + 0o644 seed.conf generation
- TestDownloadAndEnvironment  : URL scheme validation and atomic .tmp download error cleanup
```

Further architectural specifications and decisions are documented in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**, **[ADR 0001](docs/adr/0001-declarative-seed-architecture.md)**, and **[ADR 0002](docs/adr/0002-dynamic-archive-introspection.md)**.

---

## 7. Authorship, Sole Architecture & AI Code Generation Disclosure

* **Sole System Architect, Security Designer & Technical Direction:** **Sandra Gabriela Puerto Torres** ([sandrapuerto.com](https://sandrapuerto.com) · [LinkedIn](https://www.linkedin.com/in/sandra-puerto/) · [GitHub: @sandra-puerto](https://github.com/sandra-puerto)) is the **sole architect** (*única arquitecta*) of MongoDB Selective Seeder, responsible for the declarative contract architecture, container security boundaries, `.env` governance, dynamic introspection design, and end-to-end verification.
* **Code Generation & Implementation Engine:** **Google Antigravity** — Source code generation, modular refactoring, and unit test assembly are carried out by **Google Antigravity** under the direct architectural specification, engineering governance, and human review of **Sandra Gabriela Puerto Torres**.
* **Commercial Brand & Distribution:** Isora Cloud Group ([isora.com.co](https://isora.com.co))

---

## 8. Repository Structure

```text
mongodb-selective-seeder/
├── .cache/
│   └── .gitkeep                                  # Preserves local .archive cache directory in Git
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.yml                        # Structured GitHub bug report form
│   │   ├── config.yml                            # Issue chooser links to SUPPORT.md and SECURITY.md
│   │   └── feature_request.yml                   # Structured feature/enhancement proposal form
│   ├── CODEOWNERS                                # Default Pull Request review ownership
│   └── PULL_REQUEST_TEMPLATE.md                  # PR verification and architectural checklist
├── configurator/
│   ├── src/
│   │   ├── __init__.py                           # Package metadata and version
│   │   ├── core.py                               # Domain logic: discovery, bsondump introspection, atomic writes
│   │   ├── main.py                               # Thin CLI entrypoint and workflow orchestration
│   │   └── ui.py                                 # Enterprise Rich TUI presentation layer
│   ├── tests/
│   │   └── test_core.py                          # Offline unittest suite (12 tests)
│   ├── Dockerfile                                # Multi-stage build (mongo tools + python slim)
│   └── requirements.txt                          # Pinned Rich dependency (rich==13.9.4)
├── docs/
│   ├── adr/
│   │   ├── 0001-declarative-seed-architecture.md # ADR 0001: Declarative seed.conf contract
│   │   └── 0002-dynamic-archive-introspection.md # ADR 0002: Multi-stage dynamic introspection
│   └── ARCHITECTURE.md                           # System overview, data flow, and permission model
├── init-db/
│   ├── .gitkeep                                  # Preserves init-db contract directory in Git
│   └── 01-restore.sh                             # Safe first-boot restore hook sourced by mongo
├── .editorconfig                                 # Consistent UTF-8, LF, and indentation rules
├── .env.example                                  # Template for required versions and credentials
├── .gitattributes                                # Enforces LF on scripts/code and binary on .archive
├── .gitignore                                    # Excludes .env, .cache/*.archive, and seed.conf
├── AGENTS.md                                     # Architectural invariants & instructions for AI agents
├── CHANGELOG.md                                  # Semantic versioning release notes
├── CLAUDE.md                                     # Agent entrypoint importing AGENTS.md
├── CODE_OF_CONDUCT.md                            # Contributor Covenant v2.1 participation standards
├── CONTRIBUTING.md                               # Setup, coding standards, and PR workflow
├── docker-compose.yml                            # Orchestration for mongodb and setup configurator
├── LICENSE                                       # Apache License, Version 2.0
├── NOTICE                                        # Copyright and third-party attributions
├── README.md                                     # Main repository specification and usage guide
├── SECURITY.md                                   # Security boundaries and vulnerability reporting
└── SUPPORT.md                                    # Self-service troubleshooting and FAQ guide
```

---

## 9. Security Policy & Responsible Disclosure

Security vulnerabilities, container boundary concerns, or credential handling issues should be reported privately in accordance with **[SECURITY.md](SECURITY.md)**:

* **Security Operations:** [security@isora.com.co](mailto:security@isora.com.co)
* **General Contact:** [contact@isora.com.co](mailto:contact@isora.com.co)
* **Response Commitment:** Initial receipt acknowledgment within 72 hours; coordinated remediation prior to public disclosure.

---

## 10. Intellectual Property & License

* **Commercial Brand & Distribution:** Isora Cloud Group ([isora.com.co](https://isora.com.co))
* **Sole Architect & Copyright Holder:** Sandra Gabriela Puerto Torres ([sandrapuerto.com](https://sandrapuerto.com) · [LinkedIn](https://www.linkedin.com/in/sandra-puerto/))
* **Code Generation Engine:** Google Antigravity (under the sole architectural direction of Sandra Gabriela Puerto Torres)
* **License:** Distributed under the terms of the **[Apache License, Version 2.0](LICENSE)**. See [NOTICE](NOTICE) for project and third-party attributions.
