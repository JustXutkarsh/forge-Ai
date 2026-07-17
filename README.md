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
python -m forge.cli ingest --source github:owner/public-repo
```

The local core uses SQLite and the standard library. Install `requirements.txt` into `.venv`, copy `.env.example` to `.env`, set `OPENAI_API_KEY`, then run `--embed`. Never commit `.env`.

The pipeline stores all ticket metadata in SQLite, embeds only issue/resolution/category/product/priority, tracks both `record_hash` and `retrieval_hash`, and excludes customer names/emails from retrieval outputs and reports.

Set `FORGE_EMBED_LIMIT=100000` when intentionally running a development-limited embedding pass; `forge status` will label pending embeddings as intentional rather than failed.

Run the dependency-free tests with:

```bash
python -m unittest discover -s tests -v
python eval/run_eval.py --db data/forge.db
```
