"""Core business logic for archive discovery, dynamic introspection, and seed contracts."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import gzip
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib

DEFAULT_SAMPLE_URL: str = "https://atlas-education.s3.amazonaws.com/sampledata.archive"
DEFAULT_ARCHIVE_FILENAME: str = "sampledata.archive"
SEED_CONF_FILENAME: str = "seed.conf"
DEFAULT_MIN_CACHE_BYTES: int = 1024
DEFAULT_TIMEOUT_SECONDS: float = 30.0
DEFAULT_CHUNK_SIZE_BYTES: int = 65_536
DEFAULT_INTROSPECTION_TIMEOUT_SECONDS: float = 15.0
DEFAULT_PRELUDE_MAX_BYTES: int = 262_144

ARCHIVE_MAGIC_HEADER: bytes = b"\x6d\xe2\x99\x81"
GZIP_MAGIC_HEADER: bytes = b"\x1f\x8b"
SYSTEM_DATABASES: frozenset[str] = frozenset({"admin", "local", "config"})
SAFE_FILENAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9._-]+$")
MONGORESTORE_LOG_PATTERN: re.Pattern[str] = re.compile(
    r"(?:reading metadata for|restoring(?:\s+to)?|collection)\s+([a-zA-Z0-9_-]+)\.([^\s]+)"
)

FALLBACK_DESCRIPTION: str = "Custom / Uncatalogued dataset"
FALLBACK_USE_CASE: str = "Custom database collections discovered in archive"


class ConfiguratorError(Exception):
    """Base exception for all controlled configurator domain failures."""


class InvalidSelectionError(ConfiguratorError):
    """Raised when the user provides an empty, unrecognized, or malformed dataset selection."""


class ArchiveDownloadError(ConfiguratorError):
    """Raised when downloading or validating an archive fails."""


class ArchiveInspectionError(ConfiguratorError):
    """Raised when an archive cannot be read or contains no restorable user databases."""


class ContractWriteError(ConfiguratorError):
    """Raised when the declarative seed contract cannot be persisted safely."""


@dataclass(frozen=True, slots=True)
class Dataset:
    """Metadata descriptor for a restorable database discovered inside an archive."""

    id: int
    name: str
    collection_count: int
    description: str
    use_case: str


@dataclass(frozen=True, slots=True)
class SeedContract:
    """Parsed declarative seed contract stored inside init-db/seed.conf."""

    archive_file: str
    archive_gzip: bool
    datasets: tuple[str, ...]


# Diccionario opcional solo para enriquecer descripciones; la lista real proviene siempre del archivo .archive.
KNOWN_DATASET_METADATA: dict[str, tuple[str, str]] = {
    "sample_mflix": (
        "Movies, user comments, theaters, and sessions",
        "Aggregations, $lookup joins, and text search",
    ),
    "sample_airbnb": (
        "Vacation rental listings and guest reviews",
        "Deeply nested documents and pricing filters",
    ),
    "sample_analytics": (
        "Financial customers, accounts, and transactions",
        "Relational modeling and multi-collection joins",
    ),
    "sample_training": (
        "Routes, trips, grades, inspections, and posts",
        "Indexing benchmarks and mixed schema queries",
    ),
    "sample_weatherdata": (
        "Hourly atmospheric and meteorological telemetry",
        "Time-series queries and geospatial coordinates",
    ),
    "sample_restaurants": (
        "New York City restaurants, grades, and neighborhoods",
        "Geospatial indexing and nested array filters",
    ),
    "sample_supplies": (
        "Retail store sales, customer demographics, and items",
        "Grouping pipelines and array $unwind operations",
    ),
    "sample_geospatial": (
        "Shipwrecks with GeoJSON coordinates and depth data",
        "GeoJSON 2dsphere indexes and $near queries",
    ),
    "sample_guides": (
        "Solar system planets with orbital and physical metrics",
        "Numeric comparisons, sorting, and projection drills",
    ),
}


def validate_safe_filename(filename: str) -> str:
    """Validate that an archive filename is a safe basename without path traversal tokens."""
    cleaned = filename.strip()
    if not cleaned or ".." in cleaned or not SAFE_FILENAME_PATTERN.fullmatch(cleaned):
        raise ArchiveDownloadError(
            f"Invalid archive filename '{filename}': expected a plain filename without slashes or '..'."
        )
    return cleaned


def get_sample_archive_url() -> str:
    """Resolve and validate the sample archive download URL from environment or default."""
    raw_url = os.environ.get("MONGO_SAMPLE_URL", DEFAULT_SAMPLE_URL).strip()
    if not raw_url:
        raw_url = DEFAULT_SAMPLE_URL

    parsed = urllib.parse.urlparse(raw_url)
    # Restringir esquemas a HTTP/HTTPS evita que urllib lea rutas locales inesperadas como file://.
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ArchiveDownloadError(
            f"Invalid MONGO_SAMPLE_URL '{raw_url}': expected an HTTP or HTTPS URL."
        )
    return raw_url


def get_configured_archive_filename() -> str:
    """Resolve and validate the configured archive filename from ARCHIVE_FILENAME."""
    configured = os.environ.get("ARCHIVE_FILENAME", DEFAULT_ARCHIVE_FILENAME).strip()
    return validate_safe_filename(configured or DEFAULT_ARCHIVE_FILENAME)


def get_default_cache_dir() -> Path:
    """Resolve the cache directory path from CACHE_DIR or the repository default."""
    configured = os.environ.get("CACHE_DIR", ".cache").strip()
    return Path(configured or ".cache")


def get_default_init_db_dir() -> Path:
    """Resolve the init-db contract directory path from INIT_DB_DIR or the repository default."""
    configured = os.environ.get("INIT_DB_DIR", "init-db").strip()
    return Path(configured or "init-db")


def list_cached_archives(
    cache_dir: Path,
    min_size_bytes: int = DEFAULT_MIN_CACHE_BYTES,
) -> list[Path]:
    """Return sorted paths of valid .archive files currently stored in cache_dir."""
    if not cache_dir.is_dir():
        return []

    discovered: list[Path] = []
    try:
        for entry in sorted(cache_dir.glob("*.archive"), key=lambda path: path.name.lower()):
            if entry.is_file() and entry.stat().st_size >= min_size_bytes:
                discovered.append(entry)
    except OSError:
        return []
    return discovered


def is_archive_cached(
    cache_dir: Path,
    archive_filename: str | None = None,
    min_size_bytes: int = DEFAULT_MIN_CACHE_BYTES,
) -> bool:
    """Check whether a non-trivial cached archive already exists on disk."""
    target_name = validate_safe_filename(archive_filename) if archive_filename else get_configured_archive_filename()
    archive_path = cache_dir / target_name
    try:
        if not archive_path.is_file():
            return False
        return archive_path.stat().st_size >= min_size_bytes
    except OSError:
        return False


def is_gzip_archive(archive_path: Path) -> bool:
    """Inspect the first two bytes of an archive file to detect gzip compression."""
    try:
        with archive_path.open("rb") as file_handle:
            magic = file_handle.read(2)
    except OSError as err:
        raise ArchiveInspectionError(
            f"Unable to read header bytes from '{archive_path}': {err}"
        ) from err
    return magic == GZIP_MAGIC_HEADER


def read_archive_prelude_bytes(
    archive_path: Path,
    max_bytes: int = DEFAULT_PRELUDE_MAX_BYTES,
) -> bytes:
    """Read the uncompressed prelude BSON stream from a raw or gzipped MongoDB archive."""
    if not archive_path.is_file():
        raise ArchiveInspectionError(f"Archive file '{archive_path}' does not exist.")

    compressed = is_gzip_archive(archive_path)
    try:
        if compressed:
            with gzip.open(archive_path, "rb") as gz_handle:
                raw_prelude = gz_handle.read(max_bytes)
        else:
            with archive_path.open("rb") as raw_handle:
                raw_prelude = raw_handle.read(max_bytes)
    except (OSError, EOFError, zlib.error) as err:
        raise ArchiveInspectionError(
            f"Failed to read archive prelude from '{archive_path.name}': {err}"
        ) from err

    if len(raw_prelude) < 8:
        raise ArchiveInspectionError(
            f"Archive '{archive_path.name}' is too small or empty to inspect."
        )

    # Descartar la cabecera mágica de 4 bytes de mongodump sitúa el flujo exactamente en el primer BSON del preludio.
    if raw_prelude.startswith(ARCHIVE_MAGIC_HEADER):
        return raw_prelude[4:]
    return raw_prelude


def parse_introspection_output(raw_output: str) -> list[Dataset]:
    """Parse bsondump JSON lines or mongorestore verbose logs into enriched Dataset records."""
    collections_by_db: dict[str, set[str]] = {}

    for raw_line in raw_output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = None

            if isinstance(payload, dict):
                db_name = payload.get("db")
                collection_name = payload.get("collection")
                if isinstance(db_name, str) and isinstance(collection_name, str):
                    if db_name not in SYSTEM_DATABASES:
                        collections_by_db.setdefault(db_name, set()).add(collection_name)
                continue

        match = MONGORESTORE_LOG_PATTERN.search(line)
        if match:
            db_name, collection_name = match.group(1), match.group(2)
            if db_name not in SYSTEM_DATABASES:
                collections_by_db.setdefault(db_name, set()).add(collection_name)

    if not collections_by_db:
        raise ArchiveInspectionError(
            "No user databases were discovered in archive output. Ensure the file is a valid MongoDB archive."
        )

    datasets: list[Dataset] = []
    # Ordenar alfabéticamente asegura numeración estable aunque el preludio BSON altere el orden de colecciones.
    for index, db_name in enumerate(sorted(collections_by_db), start=1):
        description, use_case = KNOWN_DATASET_METADATA.get(
            db_name,
            (FALLBACK_DESCRIPTION, FALLBACK_USE_CASE),
        )
        datasets.append(
            Dataset(
                id=index,
                name=db_name,
                collection_count=len(collections_by_db[db_name]),
                description=description,
                use_case=use_case,
            )
        )
    return datasets


def inspect_archive(
    archive_path: Path,
    timeout: float = DEFAULT_INTROSPECTION_TIMEOUT_SECONDS,
) -> list[Dataset]:
    """Dynamically discover databases inside a MongoDB .archive using official bsondump."""
    prelude_bytes = read_archive_prelude_bytes(archive_path)

    try:
        # No usar check=True porque bsondump retorna código distinto de 0 al topar con el delimitador del cuerpo tras leer el preludio.
        completed = subprocess.run(
            ["bsondump", "--quiet"],
            input=prelude_bytes,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as err:
        raise ArchiveInspectionError(
            "Official 'bsondump' binary not found in PATH. Rebuild the configurator image."
        ) from err
    except subprocess.TimeoutExpired as err:
        raise ArchiveInspectionError(
            f"Archive inspection timed out after {timeout}s for '{archive_path.name}'."
        ) from err
    except OSError as err:
        raise ArchiveInspectionError(
            f"Failed to execute 'bsondump' for '{archive_path.name}': {err}"
        ) from err

    stdout_raw = completed.stdout
    stderr_raw = completed.stderr
    stdout_text = stdout_raw.decode("utf-8", errors="replace") if isinstance(stdout_raw, bytes) else (stdout_raw or "")
    stderr_text = stderr_raw.decode("utf-8", errors="replace") if isinstance(stderr_raw, bytes) else (stderr_raw or "")

    combined = f"{stdout_text}\n{stderr_text}"
    return parse_introspection_output(combined)


def parse_dataset_selection(
    raw_input: str,
    catalog: Sequence[Dataset],
) -> list[Dataset]:
    """Parse user selection input into a deduplicated ordered list of Dataset objects."""
    if not catalog:
        raise InvalidSelectionError("Cannot select datasets from an empty catalog.")

    cleaned = raw_input.strip()
    if not cleaned:
        raise InvalidSelectionError(
            "Selection cannot be empty. Enter comma-separated IDs, dataset names, or 'all'."
        )

    if cleaned.lower() == "all":
        return list(catalog)

    by_id: dict[int, Dataset] = {dataset.id: dataset for dataset in catalog}
    by_name: dict[str, Dataset] = {dataset.name.lower(): dataset for dataset in catalog}

    selected: list[Dataset] = []
    seen_names: set[str] = set()

    for raw_token in cleaned.split(","):
        token = raw_token.strip()
        if not token:
            raise InvalidSelectionError(
                "Malformed comma-separated list: empty item encountered."
            )

        matched: Dataset | None = None
        if token.isdigit():
            matched = by_id.get(int(token))
        else:
            matched = by_name.get(token.lower())

        if matched is None:
            raise InvalidSelectionError(
                f"Unrecognized dataset token '{token}'. Valid IDs are 1-{len(catalog)} or discovered database names."
            )

        # Preservar el orden elegido por el usuario evitando duplicar argumentos --nsInclude.
        if matched.name not in seen_names:
            selected.append(matched)
            seen_names.add(matched.name)

    return selected


def download_sample_archive(
    url: str,
    cache_dir: Path,
    archive_filename: str | None = None,
    progress_callback: Callable[[int, int | None], None] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    chunk_size: int = DEFAULT_CHUNK_SIZE_BYTES,
) -> Path:
    """Stream the target .archive file to disk atomically using a .tmp staging file."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ArchiveDownloadError(f"Invalid archive URL '{url}': must use HTTP or HTTPS.")

    safe_filename = validate_safe_filename(archive_filename) if archive_filename else get_configured_archive_filename()
    target_path = cache_dir / safe_filename
    tmp_path = cache_dir / f"{safe_filename}.tmp"

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        # Eliminar restos temporales de ejecuciones previas abortadas para iniciar desde cero.
        tmp_path.unlink(missing_ok=True)
    except OSError as err:
        raise ArchiveDownloadError(
            f"Unable to prepare cache directory '{cache_dir}': {err}"
        ) from err

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "mongodb-selective-seeder/1.0"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = getattr(response, "status", 200)
            if status_code != 200:
                raise ArchiveDownloadError(
                    f"Unexpected HTTP status {status_code} while downloading '{url}'."
                )

            raw_length = response.headers.get("Content-Length")
            total_bytes: int | None = None
            if raw_length is not None and raw_length.strip().isdigit():
                parsed_length = int(raw_length.strip())
                if parsed_length > 0:
                    total_bytes = parsed_length

            bytes_written = 0
            if progress_callback is not None:
                progress_callback(0, total_bytes)

            with tmp_path.open("wb") as file_handle:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    file_handle.write(chunk)
                    bytes_written += len(chunk)
                    if progress_callback is not None:
                        progress_callback(bytes_written, total_bytes)

                file_handle.flush()
                os.fsync(file_handle.fileno())

        if bytes_written <= 0:
            raise ArchiveDownloadError(
                f"Downloaded archive from '{url}' is empty (0 bytes)."
            )

        # Validar tamaño recibido frente a Content-Length previene cachés truncados silenciosos.
        if total_bytes is not None and bytes_written != total_bytes:
            raise ArchiveDownloadError(
                f"Incomplete archive download: expected {total_bytes} bytes, received {bytes_written} bytes."
            )

        # Garantizar permisos legibles (0644) para que contenedores sin privilegios puedan montar en solo lectura.
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target_path)
        return target_path
    except KeyboardInterrupt:
        tmp_path.unlink(missing_ok=True)
        raise
    except ArchiveDownloadError:
        tmp_path.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as err:
        tmp_path.unlink(missing_ok=True)
        raise ArchiveDownloadError(
            f"Failed to download sample archive from '{url}': {err}"
        ) from err
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def write_seed_contract(
    selected_datasets: Sequence[Dataset],
    init_db_dir: Path,
    archive_file: str = DEFAULT_ARCHIVE_FILENAME,
    archive_gzip: bool = False,
) -> Path:
    """Atomically write init-db/seed.conf with key-value contract, LF endings, and 0o644 mode."""
    if not selected_datasets:
        raise ContractWriteError(
            "Cannot write seed contract without at least one selected dataset."
        )

    try:
        safe_archive_file = validate_safe_filename(archive_file)
    except ArchiveDownloadError as err:
        raise ContractWriteError(str(err)) from err

    target_path = init_db_dir / SEED_CONF_FILENAME
    tmp_path = init_db_dir / f"{SEED_CONF_FILENAME}.tmp"

    dataset_list = ",".join(dataset.name for dataset in selected_datasets)
    gzip_value = "true" if archive_gzip else "false"
    lines = [
        "# Declarative dataset seed contract consumed by init-db/01-restore.sh",
        "# Regenerate via: docker compose run --rm configurator",
        f"ARCHIVE_FILE={safe_archive_file}",
        f"ARCHIVE_GZIP={gzip_value}",
        f"DATASETS={dataset_list}",
    ]
    payload = "\n".join(lines) + "\n"

    try:
        init_db_dir.mkdir(parents=True, exist_ok=True)
        tmp_path.unlink(missing_ok=True)

        # Forzar newline='\n' evita errores de parsing Bash cuando el configurador corre en Windows.
        with tmp_path.open("w", encoding="utf-8", newline="\n") as file_handle:
            file_handle.write(payload)
            file_handle.flush()
            os.fsync(file_handle.fileno())

        # Asignar 0644 explícito asegura lectura desde el usuario mongodb dentro del contenedor oficial.
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target_path)
        return target_path
    except OSError as err:
        tmp_path.unlink(missing_ok=True)
        raise ContractWriteError(
            f"Failed to write seed contract at '{target_path}': {err}"
        ) from err
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def read_seed_contract(init_db_dir: Path) -> SeedContract | None:
    """Parse an existing seed.conf file into a SeedContract, returning None if absent or empty."""
    target_path = init_db_dir / SEED_CONF_FILENAME
    if not target_path.is_file():
        return None

    archive_file = DEFAULT_ARCHIVE_FILENAME
    archive_gzip = False
    datasets: list[str] = []

    with target_path.open("r", encoding="utf-8") as file_handle:
        for raw_line in file_handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if key == "ARCHIVE_FILE" and value:
                    archive_file = value
                elif key == "ARCHIVE_GZIP":
                    archive_gzip = value.lower() in {"true", "1", "yes"}
                elif key == "DATASETS":
                    datasets.extend(item.strip() for item in value.split(",") if item.strip())
            else:
                datasets.append(line)

    if not datasets:
        return None

    return SeedContract(
        archive_file=archive_file,
        archive_gzip=archive_gzip,
        datasets=tuple(datasets),
    )
