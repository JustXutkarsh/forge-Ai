# Forge

Forge is a CLI for incremental support-ticket ingestion, exact structured analytics, and grounded retrieval.

## Quick start

```bash
python -m forge.cli profile --source /path/to/customer_support_tickets.csv
python -m forge.cli ingest --source /path/to/customer_support_tickets.csv
python -m forge.cli status
python -m forge.cli ask "What are the top complaint categories?"
python -m forge.cli ask "Summarize login issues" --json
python -m forge.cli run report --type weekly-summary --week latest
python -m forge.cli ingest --source github --repo microsoft/vscode --embed
```

The local core uses SQLite and the standard library. Install `requirements.txt` into `.venv`. Never commit `.env`.

## Configuration

Create the project-root environment file from the example:

```bash
cp .env.example .env
```

`OPENAI_API_KEY` is required for `forge ingest --embed` and `forge ask`:

```dotenv
OPENAI_API_KEY=your_openai_api_key_here
```

`GITHUB_TOKEN` is optional. Public GitHub repositories work without it; configure it when accessing private repositories or when a higher API rate limit is needed:

```dotenv
GITHUB_TOKEN=your_optional_github_token_here
```

Forge loads `.env` automatically before initializing OpenAI or GitHub clients. If the OpenAI key is missing, the CLI prints setup instructions instead of a traceback.

The pipeline stores all ticket metadata in SQLite, embeds only issue/resolution/category/product/priority, tracks both `record_hash` and `retrieval_hash`, and excludes customer names/emails from retrieval outputs and reports.

Set `FORGE_EMBED_LIMIT=100000` when intentionally running a development-limited embedding pass; `forge status` will label pending embeddings as intentional rather than failed.

## GitHub Issues

Public repositories require no authentication:

```bash
forge ingest --source github --repo owner/repository --embed
```

Forge follows GitHub API pagination, ignores pull requests, and sends normalized issues through the same SQLite hashing and Chroma embedding pipeline as CSV records. Set `GITHUB_TOKEN` in `.env` when accessing private repositories or when a higher GitHub API rate limit is needed:

```bash
GITHUB_TOKEN=github_pat_... \
forge ingest --source github --repo JustXutkarsh/Forge --embed
```

The token is optional and is never written to ticket metadata or ingestion logs.

Run the dependency-free tests with:

```bash
python -m unittest discover -s tests -v
python eval/run_eval.py --db data/forge.db
```

## Evaluation

Forge includes a 50-question evaluation dataset covering structured analytics, semantic retrieval, summaries, anomaly detection, and unsupported questions. Run it against the indexed SQLite database:

```bash
python eval/run_eval.py --db data/forge.db
```

The terminal report includes Recall@5, Precision@5, Planner Accuracy, Structured Query Accuracy, Grounded Responses, Hallucination Rate, and average response latency. Use `--json` for machine-readable per-question details.
