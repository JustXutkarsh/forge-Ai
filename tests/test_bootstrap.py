import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile

from fastapi.testclient import TestClient

from forge.api.app import create_app
from forge.bootstrap import ensure_runtime_assets
from forge.config import CHROMA_PATH, DB_PATH


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        midpoint = max(1, len(self.payload) // 2)
        return iter((self.payload[:midpoint], self.payload[midpoint:]))


def _chroma_zip() -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr("chroma.sqlite3", "vector metadata")
        archive.writestr("index/header.bin", b"index")
    return output.getvalue()


class BootstrapTests(unittest.TestCase):
    def test_api_bootstraps_before_runtime_startup(self):
        events = []
        runtime = Mock()
        runtime.semantic_ready = True
        runtime.startup.side_effect = lambda: events.append("runtime")
        runtime.shutdown.side_effect = lambda: events.append("shutdown")

        with patch("forge.api.app.ForgeRuntime", return_value=runtime), patch("forge.api.app.ensure_runtime_assets", side_effect=lambda *_paths: events.append("bootstrap")) as bootstrap:
            with TestClient(create_app()):
                self.assertEqual(events, ["bootstrap", "runtime"])

        bootstrap.assert_called_once_with(DB_PATH, CHROMA_PATH)
        self.assertEqual(events[-1], "shutdown")

    def test_downloads_and_extracts_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            db_path = root_path / "data" / "forge.db"
            chroma_path = root_path / "data" / "chroma.rebuilt"
            responses = [_Response(b"sqlite database"), _Response(_chroma_zip())]

            with patch.dict(os.environ, {"FORGE_DB_URL": "https://example.test/forge.db", "FORGE_CHROMA_URL": "https://example.test/chroma.zip"}, clear=False), patch("forge.bootstrap.requests.get", side_effect=responses) as get:
                ensure_runtime_assets(db_path, chroma_path)

            self.assertEqual(db_path.read_bytes(), b"sqlite database")
            self.assertTrue((chroma_path / "chroma.sqlite3").exists())
            self.assertTrue((chroma_path / "index" / "header.bin").exists())
            self.assertFalse((root_path / "data" / "chroma.zip").exists())
            self.assertEqual(get.call_count, 2)

    def test_existing_artifacts_skip_network(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            db_path = root_path / "data" / "forge.db"
            chroma_path = root_path / "data" / "chroma.rebuilt"
            db_path.parent.mkdir(parents=True)
            db_path.write_bytes(b"existing")
            chroma_path.mkdir()
            (chroma_path / "chroma.sqlite3").write_bytes(b"existing")

            with patch("forge.bootstrap.requests.get") as get:
                ensure_runtime_assets(db_path, chroma_path)

            get.assert_not_called()

    def test_download_retries_three_times_before_failing(self):
        with tempfile.TemporaryDirectory() as root:
            db_path = Path(root) / "data" / "forge.db"
            failure = ConnectionError("offline")
            with patch.dict(os.environ, {"FORGE_DB_URL": "https://example.test/forge.db"}, clear=False), patch("forge.bootstrap.requests.get", side_effect=failure), patch("forge.bootstrap.time.sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
                    ensure_runtime_assets(db_path, Path(root) / "data" / "chroma.rebuilt")

            self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
