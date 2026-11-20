"""Enterprise utilitarian Rich terminal presentation layer for the archive configurator."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from src.core import Dataset, InvalidSelectionError, SeedContract, parse_dataset_selection

ACCENT_BLUE: str = "#0F62FE"
BORDER_MUTED: str = "#525252"
TEXT_MUTED: str = "#8D8D8D"
STATUS_OK: str = "#24A148"
STATUS_WARN: str = "#F1C21B"
STATUS_ERROR: str = "#DA1E28"

PROJECT_NAME: str = "MongoDB Selective Seeder"
PROJECT_SLOGAN: str = "Selective dataset provisioning for MongoDB."

FOOTER_CREDITS: str = (
    "Architect: Sandra Gabriela Puerto Torres (SGPT)  |  "
    "Organization: Isora Cloud Group (ICG)  |  "
    "Powered by: Google Antigravity"
)

# Sobrescribir estilos por defecto de Rich evita colores arcoíris en barras de progreso y prompts.
ENTERPRISE_THEME: Theme = Theme(
    {
        "progress.description": "bold",
        "progress.download": TEXT_MUTED,
        "progress.data.speed": TEXT_MUTED,
        "progress.remaining": TEXT_MUTED,
        "progress.percentage": TEXT_MUTED,
        "progress.filesize": TEXT_MUTED,
        "progress.filesize.total": TEXT_MUTED,
        "progress.spinner": ACCENT_BLUE,
        "prompt": "bold",
        "prompt.default": ACCENT_BLUE,
    }
)


class ConfiguratorUI:
    """Encapsulates structured enterprise terminal rendering and interactive prompting."""

    def __init__(self, console: Console | None = None, interactive: bool = True) -> None:
        """Initialize the UI layer with a sober enterprise theme and interactivity mode."""
        self.console = console or Console(theme=ENTERPRISE_THEME)
        self.interactive = interactive
        self._existing_contract: SeedContract | None = None

    def set_existing_contract(self, contract: SeedContract | None) -> None:
        """Store an existing seed.conf summary so each step header stays context-aware."""
        self._existing_contract = contract

    def render_step_header(self, step_tag: str, step_title: str) -> None:
        """Clear interactive TTY screens cleanly and render a centered corporate step banner."""
        # Limpiar consola solo en TTY interactiva evita perder trazas al ejecutar --select o redirigir logs.
        if self.interactive and self.console.is_terminal:
            self.console.clear()

        header_lines = [
            f"[bold]{PROJECT_NAME}[/bold]",
            f"[{TEXT_MUTED}]{PROJECT_SLOGAN}[/{TEXT_MUTED}]",
            f"[bold {ACCENT_BLUE}][{step_tag}][/bold {ACCENT_BLUE}]  [{TEXT_MUTED}]{step_title}[/{TEXT_MUTED}]",
        ]
        if self._existing_contract is not None:
            formatted_dbs = ", ".join(self._existing_contract.datasets)
            compression = "gzip" if self._existing_contract.archive_gzip else "raw"
            header_lines.append(
                f"[{TEXT_MUTED}]ACTIVE CONTRACT:[/{TEXT_MUTED}] "
                f"{self._existing_contract.archive_file} ({compression}) -> {formatted_dbs}"
            )

        # Centrar el contenido con Text + Align.center adapta el encabezado al ancho real de la terminal.
        centered_header = Align.center(
            Text.from_markup("\n".join(header_lines), justify="center"),
            vertical="middle",
        )
        self.console.print(
            Panel(
                centered_header,
                box=box.SQUARE,
                border_style=BORDER_MUTED,
                padding=(0, 2),
                expand=True,
            )
        )

    def render_footer(self) -> None:
        """Render a restrained rule and centered engineering attribution footer."""
        self.console.print()
        self.console.print(Rule(style=BORDER_MUTED))
        self.console.print(
            Align.center(Text(FOOTER_CREDITS, style=TEXT_MUTED, justify="center"))
        )

    def prompt_archive_source(
        self,
        cached_archives: Sequence[Path],
        configured_filename: str,
        configured_url: str,
    ) -> Path | None:
        """Present cached local archives or URL download inside a sharp Step 1/3 table."""
        self.render_step_header("STEP 1/3", "ARCHIVE SOURCE")
        self.console.print(f"\n[bold {TEXT_MUTED}]DISCOVERED ARCHIVES IN .CACHE/[/bold {TEXT_MUTED}]")

        table = Table(
            box=box.SQUARE,
            border_style=BORDER_MUTED,
            header_style="bold",
            padding=(0, 1),
            expand=True,
        )
        table.add_column("OPTION", justify="right", style=f"bold {ACCENT_BLUE}", no_wrap=True)
        table.add_column("ARCHIVE FILE", style="bold", no_wrap=True)
        table.add_column("SIZE / SOURCE", justify="right", no_wrap=False)

        for idx, archive_path in enumerate(cached_archives, start=1):
            size_mb = archive_path.stat().st_size / (1024 * 1024)
            table.add_row(str(idx), archive_path.name, f"{size_mb:.1f} MB")

        table.add_row(
            "d",
            f"Download / Refresh {configured_filename}",
            f"[{TEXT_MUTED}]{configured_url}[/{TEXT_MUTED}]",
        )
        self.console.print(table)
        self.render_footer()
        self.console.print()

        # Mantener bucle explícito para que una entrada inválida no aborte el contenedor interactivo.
        while True:
            raw_choice = Prompt.ask("Select archive source", console=self.console, default="1").strip()
            if raw_choice.lower() == "d":
                return None
            if raw_choice.isdigit():
                index = int(raw_choice)
                if 1 <= index <= len(cached_archives):
                    return cached_archives[index - 1]
            self.console.print(
                f"[bold {STATUS_ERROR}][ERROR][/bold {STATUS_ERROR}] "
                f"Invalid option '{raw_choice}'. Enter 1-{len(cached_archives)} or 'd'."
            )

    def begin_transfer_step(self) -> None:
        """Render a clean Step 2/3 screen before archive download or introspection."""
        self.render_step_header("STEP 2/3", "ARCHIVE TRANSFER & INSPECTION")
        self.console.print()

    def show_cache_hit(self, archive_path: str) -> None:
        """Log reuse of an existing cached archive using semantic status tagging."""
        self.console.print(
            f"[bold {STATUS_OK}][OK][/bold {STATUS_OK}] Using cached archive: [bold]{archive_path}[/bold]"
        )

    def show_inspecting_archive(self, archive_name: str, is_gzip: bool) -> None:
        """Log offline introspection start before invoking bsondump."""
        encoding_label = "gzip-compressed" if is_gzip else "uncompressed"
        self.console.print(
            f"[bold {ACCENT_BLUE}][INFO][/bold {ACCENT_BLUE}] "
            f"Inspecting [bold]{archive_name}[/bold] ([{TEXT_MUTED}]{encoding_label}[/{TEXT_MUTED}]) via official bsondump..."
        )

    def create_download_progress(self) -> Progress:
        """Build a sober corporate Progress bar using single cobalt accent fill."""
        # Limitar el ancho y usar un único color de acento mantiene la barra sobria en terminales anchas.
        return Progress(
            SpinnerColumn(style=ACCENT_BLUE),
            TextColumn("[bold]{task.description}"),
            BarColumn(
                bar_width=36,
                style=BORDER_MUTED,
                complete_style=ACCENT_BLUE,
                finished_style=STATUS_OK,
                pulse_style=ACCENT_BLUE,
            ),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=self.console,
        )

    def render_dataset_table(
        self,
        catalog: Sequence[Dataset],
        archive_name: str,
        is_gzip: bool,
    ) -> None:
        """Render Step 3/3 with discovered databases inside a structured square grid."""
        self.render_step_header("STEP 3/3", "DATABASE SELECTION")
        format_tag = "GZIP" if is_gzip else "RAW"
        self.console.print(
            f"\n[bold {TEXT_MUTED}]DISCOVERED DATABASES IN {archive_name.upper()} ({format_tag})[/bold {TEXT_MUTED}]"
        )

        table = Table(
            box=box.SQUARE,
            border_style=BORDER_MUTED,
            header_style="bold",
            padding=(0, 1),
            expand=True,
        )
        table.add_column("ID", justify="right", style=f"bold {ACCENT_BLUE}", no_wrap=True)
        table.add_column("DATABASE", style="bold", no_wrap=True)
        table.add_column("COLLECTIONS", justify="right", no_wrap=True)
        table.add_column("DESCRIPTION")
        table.add_column("USE CASE", style=TEXT_MUTED)

        for dataset in catalog:
            table.add_row(
                str(dataset.id),
                dataset.name,
                str(dataset.collection_count),
                dataset.description,
                dataset.use_case,
            )

        self.console.print(table)

    def prompt_dataset_selection(self, catalog: Sequence[Dataset]) -> list[Dataset]:
        """Display concise instructions and footer, then prompt until selection is valid."""
        self.console.print(
            f"\n[{TEXT_MUTED}]Enter comma-separated IDs (e.g. 1,2), database names, or 'all'.[/{TEXT_MUTED}]"
        )
        self.render_footer()
        self.console.print()

        # Bucle de reintento explícito para que errores tipográficos del usuario no aborten el contenedor.
        while True:
            raw_choice = Prompt.ask("Select datasets", console=self.console, default="1")
            try:
                return parse_dataset_selection(raw_choice, catalog=catalog)
            except InvalidSelectionError as err:
                self.console.print(f"[bold {STATUS_ERROR}][ERROR][/bold {STATUS_ERROR}] {err}")

    def render_summary(
        self,
        selected: Sequence[Dataset],
        contract_path: str,
        archive_name: str,
        is_gzip: bool,
        archive_size_bytes: int = 0,
        total_collections: int = 0,
    ) -> None:
        """Clear previous step and display final declarative contract summary and next commands."""
        self.render_step_header("COMPLETE", "CONTRACT SUMMARY")
        self.console.print()

        selected_collections = sum(item.collection_count for item in selected)
        dataset_lines = [
            f"  - [bold]{item.name}[/bold] "
            f"[{TEXT_MUTED}]({item.collection_count} {'collection' if item.collection_count == 1 else 'collections'})[/{TEXT_MUTED}]"
            for item in selected
        ]

        summary_lines = [
            f"[bold {STATUS_OK}][OK][/bold {STATUS_OK}] [bold]Declarative contract generated successfully[/bold]",
            "",
            f"[{TEXT_MUTED}]CONTRACT PATH   :[/{TEXT_MUTED}] {contract_path}",
            f"[{TEXT_MUTED}]ARCHIVE SOURCE  :[/{TEXT_MUTED}] {archive_name} (gzip={'true' if is_gzip else 'false'})",
        ]

        if archive_size_bytes > 0 and total_collections > 0:
            archive_mb = archive_size_bytes / (1024 * 1024)
            # Estimar proporción usando solo el tamaño real en disco y colecciones seleccionadas sin cifras fijas.
            proportional_mb = archive_mb * (selected_collections / total_collections)
            summary_lines.append(
                f"[{TEXT_MUTED}]IMPORT WORKLOAD :[/{TEXT_MUTED}] "
                f"{selected_collections}/{total_collections} collections (~{proportional_mb:.1f} MB share of {archive_mb:.1f} MB archive)"
            )
            if proportional_mb >= 100.0:
                summary_lines.append(
                    f"[bold {ACCENT_BLUE}][INFO][/bold {ACCENT_BLUE}] "
                    f"[{TEXT_MUTED}]Large first-boot restore may take 1-3 minutes depending on disk/CPU.[/{TEXT_MUTED}]"
                )

        summary_lines.extend(
            [
                "",
                f"[bold {TEXT_MUTED}]DATABASES QUEUED FOR FIRST-BOOT IMPORT[/bold {TEXT_MUTED}]",
                *dataset_lines,
                "",
                f"[bold {TEXT_MUTED}]NEXT STEPS[/bold {TEXT_MUTED}]",
                f"  1. Start & wait ready: [bold {ACCENT_BLUE}]docker compose up -d --wait[/bold {ACCENT_BLUE}]",
                f"  2. Watch live import : [bold {ACCENT_BLUE}]docker compose logs -f mongodb[/bold {ACCENT_BLUE}]",
                f"  3. Reset & re-seed   : [bold {ACCENT_BLUE}]docker compose down -v[/bold {ACCENT_BLUE}]",
            ]
        )

        self.console.print(
            Panel(
                "\n".join(summary_lines),
                box=box.SQUARE,
                border_style=BORDER_MUTED,
                padding=(1, 2),
                expand=True,
            )
        )
        self.render_footer()

    def render_error(self, message: str) -> None:
        """Render a crisp error box without wiping diagnostic context above it."""
        self.console.print()
        self.console.print(
            Panel(
                f"[bold {STATUS_ERROR}][ERROR][/bold {STATUS_ERROR}] {message}",
                box=box.SQUARE,
                border_style=STATUS_ERROR,
                padding=(0, 2),
                expand=True,
            )
        )
        self.render_footer()

    def render_interrupted(self) -> None:
        """Render a clean cancellation notice when aborted with Ctrl+C."""
        self.console.print(
            f"\n[bold {STATUS_WARN}][CANCELLED][/bold {STATUS_WARN}] "
            "Setup aborted by user. Partial temporary files were cleaned up."
        )
        self.render_footer()
