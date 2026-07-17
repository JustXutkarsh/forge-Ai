import argparse
import json
import sqlite3
from pathlib import Path

from forge.agent.executor import ask, weekly_report
from forge.agent.planner import TOOL_NAMES
from forge.analytics.schema import init_db
from forge.config import DB_PATH, OUTPUTS, ensure_dirs
from forge.config import EMBED_LIMIT
from forge.pipeline.github import ingest_github
from forge.pipeline.ingest import ingest_csv
from forge.pipeline.profile import write_profile


TOOLS = list(TOOL_NAMES)


def _render_ask(question: str, payload: dict) -> str:
    heading = "Summary" if "summarize" in payload.get("tool_calls", []) or "draft_report" in payload.get("tool_calls", []) else "Answer"
    lines = ["Question", question, "", heading, str(payload.get("answer", "")), "", "Evidence"]
    ticket_ids = payload.get("source_ticket_ids", [])
    if ticket_ids:
        lines.extend(f"• Ticket {ticket_id}" for ticket_id in ticket_ids)
    elif "query_structured" in payload.get("tool_calls", []):
        lines.append("• Structured SQLite query")
    else:
        lines.append("• No supporting evidence found")
    lines += ["", "Confidence", f"{float(payload.get('confidence', 0.0)):.2f}", "", "-" * 50]
    return "\n".join(lines)


def _status_payload(conn: sqlite3.Connection, db: str) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    embedded = conn.execute("SELECT COUNT(*) FROM tickets WHERE embedding_status = 'embedded'").fetchone()[0]
    pending = total - embedded
    latest = conn.execute("SELECT * FROM ingest_runs ORDER BY run_id DESC LIMIT 1").fetchone()
    if pending == 0:
        mode = "Complete"
    elif EMBED_LIMIT and embedded >= EMBED_LIMIT:
        mode = "Development (intentional limit)"
    elif EMBED_LIMIT:
        mode = f"Development (limit: {EMBED_LIMIT:,})"
    else:
        mode = "Development (pending work; no limit configured)"
    return {
        "database": db,
        "database_engine": "SQLite",
        "vector_store": "ChromaDB",
        "total_records": total,
        "embedded": embedded,
        "embedding_pending": pending,
        "embedding_mode": mode,
        "embedding_failures": 0,
        "last_ingest": latest["finished_at"] if latest else None,
        "freshness": "Up-to-date" if not latest or latest["changed_count"] == 0 else "Updated on last ingest",
    }


def _render_status(payload: dict) -> str:
    return "\n".join([
        "Forge Status", "=" * 50, "", "Pipeline", "Healthy", "", "Database", f"{payload['database_engine']} ({payload['database']})", "", "Vector Store", payload["vector_store"], "", "Records", f"{payload['total_records']:,}", "", "Embedded", f"{payload['embedded']:,}", "", "Pending", f"{payload['embedding_pending']:,}", "", "Embedding Mode", payload["embedding_mode"], "", "Last Ingest", str(payload["last_ingest"] or "Never"), "", "Embedding Failures", str(payload["embedding_failures"]), "", "Freshness", payload["freshness"], "", "=" * 50,
    ])


def _ingest_source(source: str, db: str) -> dict:
    if source.startswith("github:"):
        return ingest_github(source.removeprefix("github:"), db)
    return ingest_csv(source, db)


def _conn(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _fallback(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="forge")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("profile"); p.add_argument("--source", required=True); p.add_argument("--output", default="outputs/profile.json")
    p = sub.add_parser("ingest"); p.add_argument("--source", required=True); p.add_argument("--db", default=str(DB_PATH)); p.add_argument("--embed", action="store_true")
    p = sub.add_parser("ask", help="Ask a grounded support question."); p.add_argument("question"); p.add_argument("--db", default=str(DB_PATH)); p.add_argument("--json", action="store_true", help="Return the machine-readable JSON response.")
    p = sub.add_parser("status", help="Show pipeline and embedding health."); p.add_argument("--db", default=str(DB_PATH)); p.add_argument("--json", action="store_true", help="Return the machine-readable JSON response.")
    p = sub.add_parser("tools")
    run = sub.add_parser("run"); run_sub = run.add_subparsers(dest="run_command", required=True)
    report = run_sub.add_parser("report"); report.add_argument("--type", default="weekly-summary"); report.add_argument("--week", default=None); report.add_argument("--start"); report.add_argument("--end"); report.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args(argv)
    ensure_dirs()
    if args.command == "profile": print(json.dumps(write_profile(args.source, args.output), indent=2)); return
    if args.command == "ingest":
        result = _ingest_source(args.source, args.db)
        if args.embed:
            from forge.rag.embed import embed_pending
            result["embedded"] = embed_pending(args.db)
        print(json.dumps(result, indent=2)); return
    if args.command == "ask":
        conn = _conn(args.db); payload = ask(conn, args.question); print(json.dumps(payload, indent=2, default=str) if args.json else _render_ask(args.question, payload)); conn.close(); return
    if args.command == "tools": print("\n".join(TOOLS)); return
    if args.command == "status":
        conn = _conn(args.db)
        payload = _status_payload(conn, args.db); print(json.dumps(payload, indent=2) if args.json else _render_status(payload)); conn.close(); return
    if args.command == "run" and args.run_command == "report":
        conn = _conn(args.db); content, dates = weekly_report(conn, args.start, args.end)
        path = OUTPUTS / "reports" / f"weekly_summary_{dates[0]}_to_{dates[1]}.md"; path.write_text(content, encoding="utf-8")
        print(json.dumps({"report": str(path), "date_range": dates}, indent=2)); conn.close(); return


def _typer_main() -> None:
    import typer

    app = typer.Typer(help="Incremental support-ticket ingestion and grounded analytics.")
    run_app = typer.Typer(help="Run generated workflows.")
    app.add_typer(run_app, name="run")

    @app.command()
    def profile(source: str = typer.Option(..., "--source"), output: str = typer.Option("outputs/profile.json", "--output")):
        ensure_dirs()
        typer.echo(json.dumps(write_profile(source, output), indent=2))

    @app.command()
    def ingest(source: str = typer.Option(..., "--source"), db: str = typer.Option(str(DB_PATH), "--db"), embed: bool = typer.Option(False, "--embed")):
        ensure_dirs()
        result = _ingest_source(source, db)
        if embed:
            from forge.rag.embed import embed_pending
            result["embedded"] = embed_pending(db)
        typer.echo(json.dumps(result, indent=2))

    @app.command("ask")
    def ask_command(question: str, db: str = typer.Option(str(DB_PATH), "--db", help="SQLite database path."), json_output: bool = typer.Option(False, "--json", help="Return the machine-readable JSON response.")):
        """Ask a grounded support question."""
        conn = _conn(db)
        payload = ask(conn, question)
        typer.echo(json.dumps(payload, indent=2, default=str) if json_output else _render_ask(question, payload))
        conn.close()

    @app.command()
    def status(db: str = typer.Option(str(DB_PATH), "--db", help="SQLite database path."), json_output: bool = typer.Option(False, "--json", help="Return the machine-readable JSON response.")):
        """Show pipeline and embedding health."""
        conn = _conn(db)
        payload = _status_payload(conn, db)
        typer.echo(json.dumps(payload, indent=2) if json_output else _render_status(payload))
        conn.close()

    @app.command()
    def tools():
        typer.echo("\n".join(TOOLS))

    @run_app.command("report")
    def report(report_type: str = typer.Option("weekly-summary", "--type"), week: str | None = typer.Option(None, "--week"), start: str | None = typer.Option(None, "--start"), end: str | None = typer.Option(None, "--end"), db: str = typer.Option(str(DB_PATH), "--db")):
        if report_type != "weekly-summary":
            raise typer.BadParameter("only weekly-summary is supported in v1")
        conn = _conn(db)
        content, dates = weekly_report(conn, start, end)
        path = OUTPUTS / "reports" / f"weekly_summary_{dates[0]}_to_{dates[1]}.md"
        path.write_text(content, encoding="utf-8")
        typer.echo(json.dumps({"report": str(path), "date_range": dates}, indent=2))
        conn.close()

    app()


def main() -> None:
    try:
        import typer  # noqa: F401
    except ImportError:
        _fallback()
        return
    _typer_main()


if __name__ == "__main__":
    main()
