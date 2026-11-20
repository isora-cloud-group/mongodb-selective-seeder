"""Thin CLI entrypoint orchestrating archive selection, dynamic introspection, and contracts."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import sys

from src.core import (
    ArchiveInspectionError,
    ConfiguratorError,
    download_sample_archive,
    get_configured_archive_filename,
    get_default_cache_dir,
    get_default_init_db_dir,
    get_sample_archive_url,
    inspect_archive,
    is_archive_cached,
    is_gzip_archive,
    list_cached_archives,
    parse_dataset_selection,
    read_seed_contract,
    validate_safe_filename,
    write_seed_contract,
)
from src.ui import ConfiguratorUI


def build_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line parser supporting interactive and scripted execution."""
    parser = argparse.ArgumentParser(
        prog="configurator",
        description="Inspect any MongoDB .archive and configure selective first-boot seeding.",
    )
    parser.add_argument(
        "--archive",
        type=str,
        default=None,
        help="Archive filename inside .cache/ to inspect non-interactively (defaults to ARCHIVE_FILENAME).",
    )
    parser.add_argument(
        "--select",
        type=str,
        default=None,
        help="Non-interactive database selection (comma-separated IDs, database names, or 'all').",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force re-download from MONGO_SAMPLE_URL even if an archive is already cached.",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Override directory storing .archive files (defaults to CACHE_DIR or .cache).",
    )
    parser.add_argument(
        "--init-db-dir",
        type=Path,
        default=None,
        help="Override directory receiving seed.conf (defaults to INIT_DB_DIR or init-db).",
    )
    return parser


def _download_configured_archive(
    ui: ConfiguratorUI,
    cache_dir: Path,
    archive_filename: str,
    url: str,
) -> Path:
    """Download the target archive file from URL while rendering Rich streaming progress."""
    with ui.create_download_progress() as progress:
        task_id = progress.add_task(f"Downloading {archive_filename}", total=None)

        def on_progress(downloaded: int, total: int | None) -> None:
            progress.update(task_id, completed=downloaded, total=total)

        return download_sample_archive(
            url=url,
            cache_dir=cache_dir,
            archive_filename=archive_filename,
            progress_callback=on_progress,
        )


def _resolve_target_archive(
    args: argparse.Namespace,
    ui: ConfiguratorUI,
    cache_dir: Path,
) -> Path:
    """Resolve the .archive path from CLI flags, local cache discovery, or remote download."""
    configured_filename = get_configured_archive_filename()
    url = get_sample_archive_url()

    if args.archive is not None:
        safe_name = validate_safe_filename(args.archive)
        explicit_path = cache_dir / safe_name
        if explicit_path.is_file() and not args.refresh:
            ui.begin_transfer_step()
            ui.show_cache_hit(str(explicit_path))
            return explicit_path
        if args.refresh and safe_name == configured_filename:
            ui.begin_transfer_step()
            return _download_configured_archive(ui, cache_dir, configured_filename, url)
        raise ArchiveInspectionError(
            f"Requested archive '{explicit_path}' does not exist in cache directory '{cache_dir}'."
        )

    if args.refresh:
        ui.begin_transfer_step()
        return _download_configured_archive(ui, cache_dir, configured_filename, url)

    cached_archives = list_cached_archives(cache_dir)
    if args.select is not None:
        ui.begin_transfer_step()
        if is_archive_cached(cache_dir, archive_filename=configured_filename):
            target_path = cache_dir / configured_filename
            ui.show_cache_hit(str(target_path))
            return target_path
        return _download_configured_archive(ui, cache_dir, configured_filename, url)

    if cached_archives:
        chosen_path = ui.prompt_archive_source(cached_archives, configured_filename, url)
        ui.begin_transfer_step()
        if chosen_path is not None:
            ui.show_cache_hit(str(chosen_path))
            return chosen_path
        return _download_configured_archive(ui, cache_dir, configured_filename, url)

    ui.begin_transfer_step()
    return _download_configured_archive(ui, cache_dir, configured_filename, url)


def run(argv: Sequence[str] | None = None, ui: ConfiguratorUI | None = None) -> int:
    """Execute the configurator workflow and return an OS exit status code."""
    parser = build_argument_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    # Desactivar limpieza automática en modo --select evita borrar mensajes previos cuando corre en CI/scripts.
    active_ui = ui or ConfiguratorUI(interactive=(args.select is None))

    cache_dir: Path = args.cache_dir or get_default_cache_dir()
    init_db_dir: Path = args.init_db_dir or get_default_init_db_dir()

    try:
        existing_contract = read_seed_contract(init_db_dir)
        active_ui.set_existing_contract(existing_contract)

        archive_path = _resolve_target_archive(args, active_ui, cache_dir)
        archive_gzip = is_gzip_archive(archive_path)

        # Descubrir bases de datos dinámicamente desde el binario evita mantener catálogos desactualizados.
        active_ui.show_inspecting_archive(archive_path.name, is_gzip=archive_gzip)
        catalog = inspect_archive(archive_path)

        if args.select is not None:
            selected = parse_dataset_selection(args.select, catalog=catalog)
        else:
            active_ui.render_dataset_table(catalog, archive_name=archive_path.name, is_gzip=archive_gzip)
            selected = active_ui.prompt_dataset_selection(catalog)

        contract_path = write_seed_contract(
            selected_datasets=selected,
            init_db_dir=init_db_dir,
            archive_file=archive_path.name,
            archive_gzip=archive_gzip,
        )
        active_ui.render_summary(
            selected=selected,
            contract_path=str(contract_path),
            archive_name=archive_path.name,
            is_gzip=archive_gzip,
            archive_size_bytes=archive_path.stat().st_size,
            total_collections=sum(item.collection_count for item in catalog),
        )
        return 0
    except KeyboardInterrupt:
        active_ui.render_interrupted()
        return 130
    except ConfiguratorError as err:
        active_ui.render_error(str(err))
        return 1


if __name__ == "__main__":
    sys.exit(run())
