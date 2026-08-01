"""Tests for noninteractive source materialization."""

import json
import sys
import tempfile
import unittest
from email.message import Message
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from download_sources import DownloadError, download_sources  # noqa: E402


FIXTURE = ROOT / "tests" / "fixtures" / "compute-service.tea-schema.json"


def candidate(source_key: str, url: str) -> dict:
    return {
        "source_key": source_key,
        "title": f"Source {source_key}",
        "authors": "Example Institute",
        "year": 2026,
        "publisher_or_journal": "Example Reports",
        "source_url": url,
        "doi": "",
        "quality_estimate": "B",
        "access_notes": "open access full text verified",
        "field_coverage": [{"entity": "compute_hardware", "parameters": ["monthly_cost"]}],
        "rationale": "Test source.",
    }


class FakeResponse:
    def __init__(self, body: bytes, content_type: str, final_url: str):
        self.body = body
        self.final_url = final_url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, amount: int) -> bytes:
        return self.body[:amount]

    def geturl(self) -> str:
        return self.final_url


class DownloadSourcesTests(unittest.TestCase):
    def _search_file(self, root: Path) -> Path:
        path = root / "master-list.json"
        path.write_text(
            json.dumps(
                {
                    "schema_tea_id": "compute-service",
                    "candidates": [
                        candidate("public-report", "https://example.test/landing"),
                        candidate("not-approved", "https://example.test/other"),
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_downloads_only_approved_key_without_browser_filename_matching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def opener(request, timeout):
                calls.append((request.full_url, timeout))
                return FakeResponse(b"%PDF-test", "application/pdf", request.full_url)

            result = download_sources(
                schema_path=FIXTURE,
                input_path=self._search_file(root),
                output_dir=root / "master list sources",
                approved_source_keys=["public-report"],
                opener=opener,
            )

            self.assertEqual(calls, [("https://example.test/landing", 30)])
            self.assertEqual(result["failed"], [])
            downloaded = result["downloaded"][0]
            self.assertEqual(downloaded.path.name, "compute_hardware_public-report.pdf")
            self.assertEqual(downloaded.path.read_bytes(), b"%PDF-test")

    def test_requires_an_explicit_approved_key_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(DownloadError, "at least one screened source"):
                download_sources(
                    schema_path=FIXTURE,
                    input_path=self._search_file(root),
                    output_dir=root / "sources",
                    approved_source_keys=[],
                )

    def test_oversized_response_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def opener(_request, _timeout=None, **_kwargs):
                return FakeResponse(
                    b"123456", "application/octet-stream", "https://example.test/blob"
                )

            result = download_sources(
                schema_path=FIXTURE,
                input_path=self._search_file(root),
                output_dir=root / "sources",
                approved_source_keys=["public-report"],
                max_bytes=5,
                opener=opener,
            )

            self.assertEqual(result["downloaded"], [])
            self.assertIn("download limit", result["failed"][0]["error"])
            self.assertEqual(list((root / "sources").iterdir()), [])

    def test_private_host_is_rejected_before_network_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            search_path = root / "master-list.json"
            search_path.write_text(
                json.dumps(
                    {
                        "schema_tea_id": "compute-service",
                        "candidates": [candidate("private-report", "http://127.0.0.1/report.pdf")],
                    }
                ),
                encoding="utf-8",
            )
            called = False

            def opener(_request, **_kwargs):
                nonlocal called
                called = True
                raise AssertionError("private URL should not be opened")

            result = download_sources(
                schema_path=FIXTURE,
                input_path=search_path,
                output_dir=root / "sources",
                approved_source_keys=["private-report"],
                opener=opener,
            )

            self.assertFalse(called)
            self.assertIn("private", result["failed"][0]["error"])


if __name__ == "__main__":
    unittest.main()
