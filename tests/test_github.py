import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from forge.pipeline.github import fetch_github_issues, ingest_github, map_github_issue


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        import json
        return json.dumps(self.payload).encode()


def issue(issue_id=123, body="Cannot log in", labels=None, state="open"):
    return {
        "id": issue_id,
        "number": issue_id,
        "title": "Login failure",
        "body": body,
        "state": state,
        "labels": [{"name": value} for value in (labels or ["bug", "priority: high"])],
        "created_at": "2024-01-02T03:04:05Z",
        "updated_at": "2024-01-03T03:04:05Z",
        "closed_at": "2024-01-04T03:04:05Z" if state == "closed" else None,
        "comments": 0,
    }


class GitHubIngestionTests(unittest.TestCase):
    def test_issue_mapping_uses_existing_schema(self):
        mapped = map_github_issue(issue(state="closed"), "microsoft/vscode", "Fixed in the next release.")
        self.assertEqual(mapped["ticket_id"], "123")
        self.assertEqual(mapped["category"], "bug")
        self.assertEqual(mapped["product"], "vscode")
        self.assertIn("Login failure", mapped["issue_description"])
        self.assertIn("Fixed in the next release", mapped["resolution_notes"])
        self.assertEqual(mapped["priority"], "High")
        self.assertEqual(mapped["status"], "Closed")
        self.assertEqual(mapped["channel"], "GitHub")
        self.assertEqual(mapped["region"], "Unknown")
        self.assertEqual(mapped["ticket_created_date"], "2024-01-02")
        self.assertEqual(mapped["updated_date"], "2024-01-03T03:04:05Z")

    def test_pagination_and_pull_request_filtering(self):
        page_two_url = "https://api.github.com/repos/acme/app/issues?state=all&per_page=100&page=2"

        def fake_urlopen(request, timeout):
            if "&page=1" in request.full_url:
                return FakeResponse([issue(1), {**issue(2), "pull_request": {}}], {"Link": f"<{page_two_url}>; rel=\"next\""})
            return FakeResponse([issue(3)])

        with patch("forge.pipeline.github.urlopen", side_effect=fake_urlopen):
            records = fetch_github_issues("acme/app")

        self.assertEqual([record["ticket_id"] for record in records], ["1", "3"])

    def test_incremental_hash_reuse_and_metadata_only_update(self):
        temp = tempfile.TemporaryDirectory()
        db_path = Path(temp.name) / "forge.db"
        current = issue()
        with patch("forge.pipeline.github.fetch_github_issues", return_value=[map_github_issue(current, "acme/app")]):
            first = ingest_github("acme/app", str(db_path))
        self.assertEqual((first["new"], first["embedding_candidates"]), (1, 1))

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE tickets SET embedding_status='embedded'")
        conn.commit()
        conn.close()

        with patch("forge.pipeline.github.fetch_github_issues", return_value=[map_github_issue(current, "acme/app")]):
            unchanged = ingest_github("acme/app", str(db_path))
        self.assertEqual((unchanged["skipped"], unchanged["embedding_candidates"]), (1, 0))

        body_changed = copy.deepcopy(current)
        body_changed["body"] = "The login failure is still present."
        with patch("forge.pipeline.github.fetch_github_issues", return_value=[map_github_issue(body_changed, "acme/app")]):
            changed = ingest_github("acme/app", str(db_path))
        self.assertEqual((changed["changed"], changed["embedding_candidates"]), (1, 1))

        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE tickets SET embedding_status='embedded'")
        conn.commit()
        conn.close()

        metadata_changed = map_github_issue(body_changed, "acme/app")
        metadata_changed["updated_date"] = "2024-01-05T03:04:05Z"
        with patch("forge.pipeline.github.fetch_github_issues", return_value=[metadata_changed]):
            metadata = ingest_github("acme/app", str(db_path))
        self.assertEqual((metadata["changed"], metadata["embedding_candidates"]), (1, 0))
        temp.cleanup()

    def test_invalid_repository_returns_error_result(self):
        result = ingest_github("not-a-repository", ":memory:")
        self.assertEqual(result["error_type"], "invalid_repo")
        self.assertEqual(result["errors"], 1)


if __name__ == "__main__":
    unittest.main()
