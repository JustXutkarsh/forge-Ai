import json
from urllib.parse import quote
from urllib.request import Request, urlopen

from forge.pipeline.ingest import ingest_records


def fetch_github_issues(repo: str, max_pages: int = 10) -> list[dict]:
    records = []
    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{quote(repo, safe='/')}/issues?state=all&per_page=100&page={page}"
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "forge-cli"})
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        if not payload:
            break
        for issue in payload:
            if "pull_request" in issue:
                continue
            labels = {label.get("name", "").lower() for label in issue.get("labels", [])}
            priority = "Urgent" if "urgent" in labels else "High" if "high" in labels else "Medium"
            body = issue.get("body") or ""
            records.append({
                "ticket_id": f"github:{repo}:{issue['number']}",
                "customer_name": "", "customer_email": "", "product": repo,
                "category": "GitHub Issue", "issue_description": f"{issue.get('title', '')}. {body}",
                "resolution_notes": "Issue closed on GitHub." if issue.get("state") == "closed" else "Issue remains open.",
                "priority": priority, "status": "Closed" if issue.get("state") == "closed" else "Open",
                "channel": "GitHub", "region": "", "customer_age": "", "customer_gender": "",
                "subscription_type": "", "customer_tenure_months": "", "previous_tickets": "",
                "customer_satisfaction_score": "", "first_response_time_hours": "",
                "resolution_time_hours": "", "ticket_created_date": issue.get("created_at", "")[:10],
                "ticket_resolved_date": (issue.get("closed_at") or "")[:10], "escalated": "No",
                "sla_breached": "No", "operating_system": "", "browser": "", "payment_method": "",
                "language": "", "preferred_contact_time": "", "issue_complexity_score": "",
                "customer_segment": "",
            })
    return records


def ingest_github(repo: str, db_path: str) -> dict:
    return ingest_records(fetch_github_issues(repo), f"github:{repo}", db_path)
