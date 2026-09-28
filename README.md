# SARAI: Sovereignty-Aware Risk Assessment Infrastructure

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23010102.svg)](https://doi.org/10.5281/zenodo.23010102)
[![verify](https://github.com/WganMe/sarai-framework/actions/workflows/verify.yml/badge.svg)](https://github.com/WganMe/sarai-framework/actions/workflows/verify.yml)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC%20BY%204.0-lightgrey.svg)](LICENSE)

Implementation code for reliable federated business intelligence and
sovereignty-aware AI risk assessment.

**Reproducibility status, and exactly what is and is not reproducible: see
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).**

## Quick start

```bash
# Analysis half only — no services needed (~30 s)
python3 tools/assert_published_values.py

# Full run: start the federated stack, load the data, verify the federation
# (the datasets arrive with the clone: git lfs pull)
./reproduce.sh
```

## Data

The five public source datasets are tracked **in Git LFS** (500 MB total; one file
is 144 MB, over GitHub's 100 MB per-file limit, so LFS is the only way it can live
here). A clone needs `git lfs pull`:

```bash
git lfs install          # once per machine
git clone <repo> && cd sarai-framework
git lfs pull             # materialises datasets/raw_tables/
```

`datasets/raw_tables/` is the canonical dataset: 8 fact tables in PostgreSQL and
14 dimension tables in MariaDB, covering all five domains. `tools/fetch_datasets.py`
fetches the same data from upstream instead, if you prefer not to use LFS; see
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).

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

The code is [CC BY 4.0](LICENSE). The archived artefact has a DOI:

> **10.5281/zenodo.23010102** — <https://doi.org/10.5281/zenodo.23010102>

`CITATION.cff` carries the same identifier, so GitHub's "Cite this repository"
button produces a correct citation. The five public datasets are **not**
redistributed here and keep their own upstream licences (two of them
non-commercial): four from Kaggle — Olist e-commerce, healthcare, credit-card
fraud, supply chain — and one from the UCI repository (online retail). Their
provenance is recorded in `datasets/metadata/`, and `REPRODUCIBILITY.md` says how
to obtain each one.
