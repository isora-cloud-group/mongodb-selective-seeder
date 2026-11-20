# ADR 0001: Declarative Seed Architecture

- **Status:** Accepted
- **Date:** 2026-11-20
- **Deciders:** Repository Architecture & Maintainers

## Context

Students learning MongoDB need reproducible local access to the official MongoDB Atlas Sample Datasets (`sample_mflix`, `sample_airbnb`, etc.) using standard Docker workflows across Windows, macOS, and Linux hosts. Requiring every student to create an Atlas cloud account or manually extract 200+ MB of data introduces classroom friction, while loading all datasets unconditionally wastes disk space and boot time.

We evaluated how a Python setup tool should coordinate selective dataset seeding with a containerized `mongo:8.0` server.

## Considered Options

### Option A: Docker Socket Orchestration from Python
Mount `/var/run/docker.sock` inside the Python setup container so Python directly starts containers, waits for health checks, and executes `docker exec ... mongorestore`.
- **Rejected:** Grants container-escape host root privileges via the Docker socket, breaks rootless Docker / Podman security expectations, couples Python business logic tightly to container runtime APIs, and fails easily across Docker Desktop version differences.

### Option B: Custom Python BSON / Archive Binary Slicing
Download `sampledata.archive` and implement a custom parser in Python to decompress and extract selected namespaces into BSON/JSON dumps before mounting.
- **Rejected:** MongoDB's `archive` format is an interleaved binary stream of BSON metadata and compressed collection chunks managed internally by `mongorestore`. Re-implementing or reverse-engineering binary archive parsing in userland Python introduces brittle maintenance overhead and risks subtle schema corruption (`ObjectId`, `Decimal128`, `Date` types).

### Option C: Declarative Contract (`seed.conf`) + Official `mongorestore --nsInclude` (Chosen)
Separate the setup wizard (`configurator` profile) from the database lifecycle (`mongodb` service). Python caches the untouched `sampledata.archive` locally and writes selected database names to a plain-text contract (`init-db/seed.conf`). On first boot, MongoDB's native `/docker-entrypoint-initdb.d/01-restore.sh` invokes official `mongorestore --nsInclude` inside the container.

## Decision

Adopt **Option C (Declarative Contract Architecture)** as an invariant across the repository:

1. `configurator` communicates solely via `./.cache/sampledata.archive` and `./init-db/seed.conf`.
2. `mongodb` leverages native `/docker-entrypoint-initdb.d` semantics so seeding runs automatically and exclusively when `/data/db` is empty.
3. Selective namespace filtering uses MongoDB's official `--nsInclude="<db>.*"` flag inside `mongorestore`.

## Consequences

### Positive
- **Zero Privilege Escalation:** No Docker socket mounts anywhere in `docker-compose.yml`.
- **Native Idempotency:** MongoDB guarantees first-boot initialization runs once; container restarts cannot duplicate collections or corrupt existing student homework.
- **100% Data Fidelity:** Official `mongorestore` preserves indexes, BSON types, and metadata directly from MongoDB's canonical archive.
- **High Testability:** `configurator/src/core.py` has zero Docker or CLI dependencies and runs deterministic unit tests natively in milliseconds.

### Negative / Trade-offs
- **Full Cache Footprint (~200 MB):** Even when selecting a 1 MB dataset (`sample_supplies`), the master `sampledata.archive` is downloaded once into `./.cache/` before filtering occurs via `--nsInclude`. This trade-off is mitigated by persistent local caching and explicit `--refresh` control.
- **Volume Reset Required to Change Selection:** Because `/docker-entrypoint-initdb.d` intentionally skips initialized volumes, changing datasets requires running `docker compose down -v`. This trade-off prioritizes data safety over silent overwrites.
