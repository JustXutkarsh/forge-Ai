"""GitHub Issues source adapter for the shared Forge ingestion pipeline."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from forge.pipeline.ingest import ingest_records


API_ROOT = "https://api.github.com"
PER_PAGE = 100


class GitHubAPIError(RuntimeError):
    """A user-facing GitHub API or network failure."""

    def __init__(self, message: str, kind: str = "github_error") -> None:
        super().__init__(message)
        self.kind = kind


def _validate_repo(repo: str) -> str:
    """Validate and return an ``owner/repository`` identifier."""
    parts = repo.split("/")
    if len(parts) != 2 or not all(parts) or any(part.strip() != part for part in parts):
        raise ValueError("GitHub repository must use the format owner/repository")
    return repo


def _headers() -> dict[str, str]:
    """Build GitHub API headers, adding optional token authentication."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "forge-cli",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(url: str) -> tuple[Any, Any]:
    """Fetch one GitHub JSON response and convert failures to clear errors."""
    request = Request(url, headers=_headers())
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response), response.headers
    except HTTPError as exc:
        if exc.code == 404:
            raise GitHubAPIError("repository not found or is private", "not_found") from exc
        if exc.code in {401, 403}:
            remaining = exc.headers.get("X-RateLimit-Remaining")
            message = "GitHub API rate limit reached" if remaining == "0" else "GitHub authentication failed"
            raise GitHubAPIError(message, "rate_limit" if remaining == "0" else "authentication") from exc
        raise GitHubAPIError(f"GitHub API request failed with HTTP {exc.code}", "api_error") from exc
    except (URLError, TimeoutError) as exc:
        raise GitHubAPIError(f"could not reach GitHub: {exc}", "network") from exc


def _next_link(headers: Any) -> str | None:
    """Extract the RFC 5988 ``next`` URL from GitHub response headers."""
    link_header = headers.get("Link", "") if headers else ""
    for link in link_header.split(","):
        if 'rel="next"' not in link:
            continue
        start, _, rest = link.partition(">")
        if start.startswith("<"):
            return start[1:]
    return None


def _issues_url(repo: str, page: int) -> str:
    """Build a paginated issues endpoint URL."""
    return f"{API_ROOT}/repos/{quote(repo, safe='/')}/issues?state=all&per_page={PER_PAGE}&page={page}"


def _comment_url(repo: str, number: int, page: int) -> str:
    """Build a paginated issue-comments endpoint URL."""
    return f"{API_ROOT}/repos/{quote(repo, safe='/')}/issues/{number}/comments?per_page={PER_PAGE}&page={page}"


def fetch_closing_comment(repo: str, number: int) -> str:
    """Return the latest non-empty comment when GitHub exposes issue comments."""
    url = _comment_url(repo, number, 1)
    latest = ""
    while url:
        payload, headers = _request_json(url)
        if not isinstance(payload, list):
            break
        for comment in payload:
            body = str(comment.get("body") or "").strip()
            if body:
                latest = body
        url = _next_link(headers)
    return latest


def _label_name(label: Any) -> str:
    """Read a GitHub label from either its API object or a test fixture string."""
    return str(label.get("name", "") if isinstance(label, dict) else label).strip()


def _priority(labels: list[str]) -> str:
    """Derive the most specific supported priority from issue labels."""
    values = {label.lower() for label in labels}
    if any(keyword in label for label in values for keyword in ("urgent", "critical", "p0")):
        return "Urgent"
    if any(keyword in label for label in values for keyword in ("high", "p1")):
        return "High"
    if any(keyword in label for label in values for keyword in ("low", "p3")):
        return "Low"
    return "Medium"


def map_github_issue(issue: dict[str, Any], repo: str, closing_comment: str = "") -> dict[str, Any]:
    """Normalize one GitHub issue into the existing Forge ticket schema."""
    labels = [_label_name(label) for label in issue.get("labels", [])]
    labels = [label for label in labels if label]
    state = str(issue.get("state") or "open").lower()
    title = str(issue.get("title") or "").strip()
    body = str(issue.get("body") or "").strip()
    description = "\n\n".join(part for part in (title, body) if part)
    comment = str(closing_comment or issue.get("closing_comment") or "").strip()
    resolution = f"{state.title()} on GitHub."
    if comment:
        resolution += f" Closing comment: {comment}"
    repository_name = repo.split("/", 1)[1]
    return {
        "ticket_id": str(issue.get("id") or issue.get("number") or ""),
        "customer_name": "",
        "customer_email": "",
        "product": repository_name,
        "category": labels[0] if labels else "Uncategorized",
        "issue_description": description,
        "resolution_notes": resolution,
        "priority": _priority(labels),
        "status": state.title(),
        "channel": "GitHub",
        "region": "Unknown",
        "customer_age": "",
        "customer_gender": "",
        "subscription_type": "",
        "customer_tenure_months": "",
        "previous_tickets": "",
        "customer_satisfaction_score": "",
        "first_response_time_hours": "",
        "resolution_time_hours": "",
        "ticket_created_date": str(issue.get("created_at") or "")[:10],
        "updated_date": str(issue.get("updated_at") or ""),
        "ticket_resolved_date": str(issue.get("closed_at") or "")[:10] if state == "closed" else "",
        "escalated": "No",
        "sla_breached": "No",
        "operating_system": "",
        "browser": "",
        "payment_method": "",
        "language": "",
        "preferred_contact_time": "",
        "issue_complexity_score": "",
        "customer_segment": "",
    }


def fetch_github_issues(repo: str, max_pages: int | None = None) -> list[dict[str, Any]]:
    """Download all non-pull-request issues from a public or authorized repo."""
    repo = _validate_repo(repo)
    records: list[dict[str, Any]] = []
    url = _issues_url(repo, 1)
    page = 1
    while url and (max_pages is None or page <= max_pages):
        payload, headers = _request_json(url)
        if not isinstance(payload, list):
            raise GitHubAPIError("GitHub returned an invalid issues response", "api_error")
        for issue in payload:
            if "pull_request" in issue:
                continue
            closing_comment = ""
            if issue.get("state") == "closed" and issue.get("comments", 0):
                try:
                    closing_comment = fetch_closing_comment(repo, int(issue["number"]))
                except GitHubAPIError:
                    closing_comment = ""
            records.append(map_github_issue(issue, repo, closing_comment))
        url = _next_link(headers)
        if not url and len(payload) == PER_PAGE:
            page += 1
            url = _issues_url(repo, page)
        else:
            page += 1
    return records


def _error_result(repo: str, error: Exception) -> dict[str, Any]:
    """Return a stable non-throwing result for CLI and automation callers."""
    kind = getattr(error, "kind", "invalid_repo" if isinstance(error, ValueError) else "github_error")
    return {
        "source": f"github:{repo}",
        "loaded": 0,
        "new": 0,
        "changed": 0,
        "skipped": 0,
        "embedding_candidates": 0,
        "errors": 1,
        "error_type": kind,
        "error": str(error),
    }


def ingest_github(repo: str, db_path: str) -> dict[str, Any]:
    """Fetch GitHub Issues and send normalized records through shared ingestion."""
    try:
        normalized_repo = _validate_repo(repo)
        records = fetch_github_issues(normalized_repo)
        return ingest_records(records, f"github:{normalized_repo}", db_path)
    except (GitHubAPIError, ValueError) as exc:
        return _error_result(repo, exc)
