# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :---: |
| `1.0.x` | Yes |

## Security Architecture Boundaries

This repository is engineered specifically for **local academic and development environments** while enforcing strong container isolation defaults:

1. **No Docker Socket Exposure:** The interactive `configurator` container never mounts `/var/run/docker.sock` and holds no Docker daemon privileges.
2. **Read-Only Cache Mount:** The `mongodb` service mounts `./.cache` as read-only (`:ro`), preventing database processes from mutating cached archive files.
3. **Loopback Port Binding by Default:** `docker-compose.yml` binds port `27017` to `127.0.0.1` (`MONGO_HOST`) so the database is not exposed to external LAN/public interfaces unless explicitly overridden in `.env`.
4. **Input Validation in Init Hook:** `init-db/01-restore.sh` parses `seed.conf` key-value lines safely without `source` or `eval`, validates `ARCHIVE_FILE` (`^[a-zA-Z0-9._-]+$`) and dataset tokens (`^[a-zA-Z0-9_-]+$`), and constructs `mongorestore` arguments via Bash arrays.
5. **Strict HTTP/HTTPS URL Validation:** `configurator/src/core.py` restricts `MONGO_SAMPLE_URL` to `http` or `https` schemes to prevent unintended local file reads via `file://`.

## Educational Default Credentials Warning

The example username (`admin`) and password (`change_me_local_only`) defined in `.env.example` exist solely for frictionless local coursework (`docker-compose.yml` enforces `.env` with zero hardcoded credential fallbacks).

- Never reuse these example credentials in shared, staging, or production environments.
- Copy `.env.example` to `.env` and choose custom credentials before changing `MONGO_HOST` away from `127.0.0.1`.
- Never commit `.env` to version control (`.gitignore` excludes it automatically).

## Reporting a Vulnerability

If you discover a security vulnerability, insecure default, or injection vector, please do **not** open a public GitHub issue.

Report the finding privately to security@isora.com.co with:

- A description of the vulnerability and affected file(s).
- Steps or a minimal proof of concept to reproduce the issue.
- Your assessment of potential impact.

You can expect an initial acknowledgment within 72 hours and a coordinated remediation plan once validated.
