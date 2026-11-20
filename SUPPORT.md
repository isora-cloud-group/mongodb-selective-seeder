# Support Guide

Need help setting up your local MongoDB lab or troubleshooting an error? Use the resources below before opening a new issue.

## Self-Service Troubleshooting

1. **Start with [README.md](README.md)** for Quick Start commands, connection strings, and dataset reset instructions (`docker compose down -v`).
2. **Review [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** to understand how `configurator`, `./.cache/sampledata.archive`, and MongoDB's `/docker-entrypoint-initdb.d` initialization interact.
3. **Inspect container logs:**
   ```bash
   docker compose logs mongodb
   ```
4. **Verify your generated contract:**
   Confirm that `init-db/seed.conf` exists and lists the dataset names you expected.

## Common Questions

- **Why did new datasets not load after changing `seed.conf`?**
  MongoDB only executes `/docker-entrypoint-initdb.d/` scripts when the persistent volume (`mongo_data`) is empty on first boot. Run `docker compose down -v` and then `docker compose up -d` to re-initialize from scratch.
- **How do I avoid re-downloading the archive (~380-400 MB)?**
  Keep `./.cache/*.archive` intact. Running `docker compose run --rm configurator` automatically detects existing `.archive` files and lets you reuse them offline.
- **Can I seed my own MongoDB `.archive` backup instead of the Atlas sample archive?**
  Yes. Place any `mongodump --archive=...` file (raw or gzip-compressed) into `./.cache/` and select it in `docker compose run --rm configurator` (or pass `--archive your_file.archive`).
- **Docker Compose fails with `MONGO_VERSION must be set in .env`:**
  Copy `.env.example` to `.env` (`cp .env.example .env`). All versions and credentials are strictly read from `.env`.
- **Port 27017 is already in use on my machine:**
  Create a `.env` file from `.env.example` and set `MONGO_PORT=27018`.

## Where to Ask Questions

- **Classroom or coursework questions:** Consult your course instructor or lab teaching assistant first.
- **Bugs or broken links in this repository:** Open an issue using the **Bug Report** template in GitHub Issues.
- **Requests to include additional datasets or features:** Open an issue using the **Feature Request** template.
- **Security vulnerabilities:** Follow the private disclosure instructions in [SECURITY.md](SECURITY.md).
