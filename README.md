# SARAI: Sovereignty-Aware Risk Assessment Infrastructure

Implementation code for reliable federated business intelligence and
sovereignty-aware AI risk assessment.

**Reproducibility status, and exactly what is and is not reproducible: see
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).**

## Quick start

```bash
# Analysis half only — no services needed (~30 s)
python3 tools/assert_published_values.py

# Full run: fetch the frozen datasets, start the federated stack, verify it
export GH_TOKEN=...              # a token that can read this repository
./reproduce.sh
```

## Data

The 371 MB of source tables are not in the tree. They are published **frozen** as a
release asset, `<https://github.com/WganMe/sarai-framework/releases/tag/datasets-v1>`,
and `tools/fetch_datasets.py --only release` fetches it in one request. That route
needs no Kaggle account. Fetching each source individually from Kaggle and UCI is
also supported; see [`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

## Included

- Federated Text-to-SQL benchmark — 50 questions, 5 complexity tiers, 5 domains,
  24 of them genuine cross-engine joins (+ the gold SQL and per-question validators)
- SQL anomaly detection (13 rule-based detectors) and the other reliability
  mechanisms: schema-drift monitoring, confidence gating, feedback loops
- Statistical analysis: McNemar exact tests with Holm correction, Cochran's Q,
  Wilson intervals, Cohen's *h*, and the graded-sovereignty sensitivity analysis
- Database loading and deployment utilities
- `docker-compose.yml` — PostgreSQL + MariaDB + the federation engine, with the
  catalog configuration, so the stack comes up in one command
- Dataset provenance metadata

## Excluded

Credentials, the raw datasets, and the large per-run outputs. Connection settings
are read from the environment; no `.env` file is committed. `.gitignore` names
each exclusion explicitly rather than using broad globs, and the **one** benchmark
run the manuscript cites is deliberately tracked — without it the repository
could not reproduce its own reported numbers.

## Configuration

Everything defaults to `127.0.0.1` and the ports in `docker-compose.yml`, and
every value can be overridden:

| Variable | Used by | Default |
| --- | --- | --- |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | loaders, loaders, deployment | `127.0.0.1:5432` |
| `MARIADB_HOST/PORT/DB/USER/PASSWORD` | loaders, deployment | `127.0.0.1:3306` |
| `FEDERATION_URL` | benchmark, verifier, workflow | `http://127.0.0.1:8080` |
| `OLLAMA_URL` | benchmark, risk mechanisms | `http://127.0.0.1:11434` |
| `ENGINE_HEADER_STYLE` | `workflow.json` code node | `trino` |
| `RAW_TABLES_DIR` | loaders | `datasets/raw_tables` |
| `SOURCES_DIR` | `tools/fetch_datasets.py` | `datasets/sources` |
| `GH_TOKEN` / `GITHUB_TOKEN` | release-asset fetch | unset (CI sets it) |
| `RUNS_DIR`, `BENCHMARK_DIR`, `FIG_OUTDIR` | outputs | inside the checkout |

## The orchestrator

`framework/workflow.json` is an importable workflow definition: a webhook plus a
code node implementing the seven actions (`ask`, `chat`, `compile`, `dashboards`,
`health`, `help`, `metrics`, `stats`). Import it into n8n and set
`FEDERATION_URL` / `OLLAMA_URL` for your host. The `health` action probes the
federation engine, the local model server, the databases and the cache.

## License and citation

See `CITATION.cff` in the companion manuscript repository. The datasets are
public: four from Kaggle (Olist e-commerce, healthcare, credit-card fraud, supply
chain) and one from the UCI repository (online retail). Their provenance is
recorded in `datasets/metadata/`.
