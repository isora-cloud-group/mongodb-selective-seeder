# ADR 0002: Dynamic Archive Introspection via Multi-Stage Official Tools

- **Status:** Accepted
- **Date:** 2026-11-20
- **Deciders:** Repository Architecture & Maintainers

## Context

In the initial implementation (`ADR 0001`), the interactive configurator maintained a hardcoded `AVAILABLE_DATASETS` catalog of 8 Atlas sample databases. Empirical inspection of `sampledata.archive` revealed two limitations:

1. Upstream Atlas archives evolve over time (for example, `sampledata.archive` now includes `sample_guides` alongside the original 8 databases).
2. Instructors and students frequently need to seed custom course backups created with `mongodump --archive=... --gzip` containing arbitrary database names not known in advance.

## Considered Options

### Option A: Expand Hardcoded Catalog Only
Continue maintaining `AVAILABLE_DATASETS` statically in Python.
- **Rejected:** Silently hides newly added upstream databases (such as `sample_guides`) and fails completely for custom instructor `.archive` backups.

### Option B: Custom Python BSON Archive Decoder
Implement a pure-Python reader to traverse `mongodump`'s archive header format (`0x6de29981` + BSON records).
- **Rejected:** Violates the non-negotiable invariant forbidding custom BSON binary parsing in Python and introduces fragile format maintenance.

### Option C: Multi-Stage Official MongoDB Tool Copy + Dynamic Introspection (Chosen)
Use a multi-stage `Dockerfile` (`FROM mongo:${MONGO_VERSION} AS mongo-tools`) to copy official `mongorestore` and `bsondump` binaries into the Python `configurator` container (`python:${PYTHON_VERSION}-slim` + `libgssapi-krb5-2`). Python detects gzip magic bytes (`\x1f\x8b`), extracts the archive prelude stream, invokes official `bsondump` via `subprocess.run(..., shell=False)` offline, and builds the selectable menu exclusively from discovered databases — enriched optionally via a non-restrictive lookup map with clean fallbacks for custom databases.

## Empirical Finding During Verification

Testing `mongorestore --dryRun -v` directly against `sampledata.archive` in Database Tools `100.16.1` without a running database showed that `mongorestore` attempts server selection on `localhost:27017` and fails after 30 seconds before scanning archive collections. Copying `bsondump` alongside `mongorestore` from the identical `mongo:${MONGO_VERSION}` stage allows instant offline inspection of the official BSON archive metadata prelude with zero database dependency.

## Consequences

### Positive
- **100% Archive Agnostic:** Works seamlessly with Atlas sample archives (including `sample_guides`), updated future releases, and custom compressed or uncompressed `mongodump` backups.
- **No Custom BSON Parser:** Parsing remains delegated to official MongoDB binaries compiled by MongoDB, Inc.
- **Cross-Version Parity:** `MONGO_VERSION` from `.env` guarantees identical tool compatibility between `configurator` and `mongodb`.

### Negative / Trade-offs
- **Slightly Larger Setup Image:** Installing `libgssapi-krb5-2` and copying `mongorestore` / `bsondump` adds ~80 MB to the optional `configurator` image while leaving the runtime `mongodb` image untouched.
- **Pre-Download Introspection Order:** When `.cache/` is empty, the target archive must be downloaded before its internal database menu can be displayed.
