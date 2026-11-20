"""Unit tests for dynamic archive discovery, introspection, and contract persistence."""

from __future__ import annotations

from email.message import Message
import gzip
import io
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

# Garantizar resolución de importaciones cuando unittest se invoca desde la raíz del repositorio.
CONFIGURATOR_ROOT = Path(__file__).resolve().parents[1]
if str(CONFIGURATOR_ROOT) not in sys.path:
    sys.path.insert(0, str(CONFIGURATOR_ROOT))

from src import core


class _FakeHTTPResponse:
    """Minimal in-memory HTTP response stub supporting context manager and chunk reads."""

    def __init__(self, payload: bytes, status: int = 200, content_length: int | None = None) -> None:
        self._buffer = io.BytesIO(payload)
        self.status = status
        headers = Message()
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        self.headers = headers

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        return None


class TestArchiveDiscoveryAndGzip(unittest.TestCase):
    """Verify .cache/ archive scanning, filename validation, and gzip magic detection."""

    def test_is_gzip_archive_detects_magic_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            gz_file = root / "backup.archive"
            raw_file = root / "raw.archive"
            gz_file.write_bytes(b"\x1f\x8b\x08\x00" + b"payload")
            raw_file.write_bytes(core.ARCHIVE_MAGIC_HEADER + b"payload")

            self.assertTrue(core.is_gzip_archive(gz_file))
            self.assertFalse(core.is_gzip_archive(raw_file))

    def test_list_cached_archives_filters_valid_archives_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            (cache_dir / ".gitkeep").write_bytes(b"")
            (cache_dir / "tiny.archive").write_bytes(b"short")
            (cache_dir / "partial.archive.tmp").write_bytes(b"x" * 2048)
            valid_a = cache_dir / "sampledata.archive"
            valid_b = cache_dir / "custom_backup.archive"
            valid_a.write_bytes(b"x" * 2048)
            valid_b.write_bytes(b"y" * 2048)

            found = core.list_cached_archives(cache_dir, min_size_bytes=1024)
            self.assertEqual([item.name for item in found], ["custom_backup.archive", "sampledata.archive"])

    def test_validate_safe_filename_rejects_traversal(self) -> None:
        self.assertEqual(core.validate_safe_filename("custom_v2.archive"), "custom_v2.archive")
        for unsafe in ("", "../secret.archive", "dir/file.archive", "file;rm.archive"):
            with self.assertRaises(core.ArchiveDownloadError):
                core.validate_safe_filename(unsafe)


class TestDynamicIntrospection(unittest.TestCase):
    """Verify dynamic database discovery, metadata enrichment, and mocked subprocess calls."""

    def test_parse_introspection_output_enriches_known_and_falls_back_on_custom(self) -> None:
        bsondump_lines = "\n".join(
            [
                '{"concurrent_collections":{"$numberInt":"1"},"version":"0.1"}',
                '{"db":"admin","collection":"system.users","type":"collection"}',
                '{"db":"local","collection":"startup_log","type":"collection"}',
                '{"db":"sample_mflix","collection":"movies","type":"collection"}',
                '{"db":"sample_mflix","collection":"users","type":"collection"}',
                '{"db":"university_erp","collection":"students","type":"collection"}',
                '{"db":"university_erp","collection":"enrollments","type":"collection"}',
                '{"db":"university_erp","collection":"courses","type":"collection"}',
            ]
        )

        discovered = core.parse_introspection_output(bsondump_lines)
        self.assertEqual([d.name for d in discovered], ["sample_mflix", "university_erp"])
        self.assertEqual([d.id for d in discovered], [1, 2])
        self.assertEqual(discovered[0].collection_count, 2)
        self.assertEqual(
            discovered[0].description,
            core.KNOWN_DATASET_METADATA["sample_mflix"][0],
        )
        self.assertEqual(discovered[1].collection_count, 3)
        self.assertEqual(discovered[1].description, core.FALLBACK_DESCRIPTION)
        self.assertEqual(discovered[1].use_case, core.FALLBACK_USE_CASE)

    def test_parse_introspection_output_supports_mongorestore_logs(self) -> None:
        log_output = "\n".join(
            [
                "2026-11-20T14:00:00.000+0000\treading metadata for custom_shop.orders from archive",
                "2026-11-20T14:00:00.001+0000\trestoring custom_shop.customers from archive",
                "2026-11-20T14:00:00.002+0000\treading metadata for config.system from archive",
            ]
        )
        discovered = core.parse_introspection_output(log_output)
        self.assertEqual(len(discovered), 1)
        self.assertEqual(discovered[0].name, "custom_shop")
        self.assertEqual(discovered[0].collection_count, 2)

    def test_parse_introspection_output_raises_when_no_user_dbs_found(self) -> None:
        with self.assertRaises(core.ArchiveInspectionError):
            core.parse_introspection_output('{"db":"admin","collection":"system.version"}\n')

    def test_inspect_archive_reads_gzip_and_allows_bsondump_nonzero_tail_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            gz_archive = Path(tmp_dir) / "course_backup.archive"
            synthetic_stream = core.ARCHIVE_MAGIC_HEADER + b"\x10\x00\x00\x00fake-bson-body"
            with gzip.open(gz_archive, "wb") as gz_handle:
                gz_handle.write(synthetic_stream)

            mock_result = subprocess.CompletedProcess(
                args=["bsondump", "--quiet"],
                returncode=1,
                stdout=b'{"db":"analytics_custom","collection":"events"}\n',
                stderr=b"truncated trailing chunk",
            )
            with patch("subprocess.run", return_value=mock_result) as mocked_run:
                catalog = core.inspect_archive(gz_archive)

            mocked_run.assert_called_once()
            passed_input = mocked_run.call_args.kwargs["input"]
            self.assertEqual(passed_input, b"\x10\x00\x00\x00fake-bson-body")
            self.assertEqual(len(catalog), 1)
            self.assertEqual(catalog[0].name, "analytics_custom")
            self.assertEqual(catalog[0].description, core.FALLBACK_DESCRIPTION)


class TestSelectionAndContract(unittest.TestCase):
    """Verify dynamic catalog selection and updated key-value seed.conf contracts."""

    def setUp(self) -> None:
        self.catalog = [
            core.Dataset(1, "sample_mflix", 5, "Movies", "Aggregations"),
            core.Dataset(2, "university_erp", 3, core.FALLBACK_DESCRIPTION, core.FALLBACK_USE_CASE),
        ]

    def test_parse_selection_supports_all_ids_and_names_with_dedup(self) -> None:
        self.assertEqual(core.parse_dataset_selection("all", self.catalog), self.catalog)
        selected = core.parse_dataset_selection("2, sample_mflix, university_erp", self.catalog)
        self.assertEqual([item.name for item in selected], ["university_erp", "sample_mflix"])

    def test_parse_rejects_empty_or_invalid_tokens(self) -> None:
        for invalid in ("", "   ", "99", "missing_db", "1,,2", "1,"):
            with self.assertRaises(core.InvalidSelectionError):
                core.parse_dataset_selection(invalid, self.catalog)

    def test_write_and_read_seed_contract_uses_lf_permissions_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            init_dir = Path(tmp_dir)
            contract_path = core.write_seed_contract(
                selected_datasets=self.catalog,
                init_db_dir=init_dir,
                archive_file="custom_lab.archive",
                archive_gzip=True,
            )

            raw_bytes = contract_path.read_bytes()
            # Comprobar ausencia estricta de CRLF protege contra fallos de lectura en contenedores Linux.
            self.assertNotIn(b"\r", raw_bytes)
            self.assertTrue(raw_bytes.endswith(b"\n"))
            self.assertIn(b"ARCHIVE_FILE=custom_lab.archive\n", raw_bytes)
            self.assertIn(b"ARCHIVE_GZIP=true\n", raw_bytes)
            self.assertIn(b"DATASETS=sample_mflix,university_erp\n", raw_bytes)

            parsed = core.read_seed_contract(init_dir)
            self.assertEqual(
                parsed,
                core.SeedContract(
                    archive_file="custom_lab.archive",
                    archive_gzip=True,
                    datasets=("sample_mflix", "university_erp"),
                ),
            )
            self.assertFalse((init_dir / "seed.conf.tmp").exists())

            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(contract_path.stat().st_mode), 0o644)
            else:
                self.assertTrue(os.access(contract_path, os.R_OK))


class TestDownloadAndEnvironment(unittest.TestCase):
    """Verify URL checks and atomic archive downloads without hitting external networks."""

    def test_get_sample_archive_url_rejects_file_scheme(self) -> None:
        with patch.dict(os.environ, {"MONGO_SAMPLE_URL": "file:///etc/passwd"}):
            with self.assertRaises(core.ArchiveDownloadError):
                core.get_sample_archive_url()

    def test_download_sample_archive_succeeds_and_cleans_tmp_on_failures(self) -> None:
        payload = b"mock-mongodb-archive-bytes" * 64
        progress_events: list[tuple[int, int | None]] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            cache_dir = Path(tmp_dir)
            fake_response = _FakeHTTPResponse(payload, status=200, content_length=len(payload))

            with patch("urllib.request.urlopen", return_value=fake_response):
                result_path = core.download_sample_archive(
                    url="https://example.org/custom.archive",
                    cache_dir=cache_dir,
                    archive_filename="custom.archive",
                    progress_callback=lambda done, total: progress_events.append((done, total)),
                    chunk_size=128,
                )

            self.assertEqual(result_path, cache_dir / "custom.archive")
            self.assertEqual(result_path.read_bytes(), payload)
            self.assertFalse((cache_dir / "custom.archive.tmp").exists())
            self.assertEqual(progress_events[-1], (len(payload), len(payload)))

            bad_length_response = _FakeHTTPResponse(b"partial", status=200, content_length=9999)
            with patch("urllib.request.urlopen", return_value=bad_length_response):
                with self.assertRaises(core.ArchiveDownloadError):
                    core.download_sample_archive(
                        url="https://example.org/broken.archive",
                        cache_dir=cache_dir,
                        archive_filename="broken.archive",
                    )
            self.assertFalse((cache_dir / "broken.archive.tmp").exists())

            with patch(
                "urllib.request.urlopen",
                side_effect=urllib.error.URLError("connection refused"),
            ):
                with self.assertRaises(core.ArchiveDownloadError):
                    core.download_sample_archive(
                        url="https://example.org/offline.archive",
                        cache_dir=cache_dir,
                        archive_filename="offline.archive",
                    )
            self.assertFalse((cache_dir / "offline.archive.tmp").exists())


if __name__ == "__main__":
    unittest.main()
