# SARAI: Sovereignty-Aware Risk Assessment Infrastructure

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23839422.svg)](https://doi.org/10.5281/zenodo.23839422)
[![License: CC BY 4.0](https://img.shields.io/badge/License/CC%20BY%204.0-lightgrey.svg)](LICENSE)

<!-- No CI badge. The workflow is correct and both jobs pass when run by hand,
     but GitHub currently refuses to start them: "the job was not started
     because your account is locked due to a billing issue". A badge that renders
     red for a billing reason says "this code is broken", which is not what is
     true. Restore the badge once Actions runs again:
     [![verify](.../verify.yml/badge.svg)](.../verify.yml) -->

Implementation code for reliable federated business intelligence and
sovereignty-aware AI risk assessment.

**Reproducibility status, and exactly what is and is not reproducible: see
[`REPRODUCIBILITY.md`](REPRODUCIBILITY.md).**

## Quick start

```bash
# Analysis half only — no services needed (~30 s)
python3 tools/assert_published_values.py

# Full run: fetch the data, start the federated stack, verify the federation
python3 tools/fetch_datasets.py    # see DATA_SOURCES.md for the three routes
./reproduce.sh
```

## Data

The five public source datasets are **not** in this tree: 500 MB under three
different upstream licences, two of them non-commercial. They are frozen as a
release asset and fetched in one command.

```bash
python3 tools/fetch_datasets.py --only release   # unmetered, no Kaggle token
```

[`DATA_SOURCES.md`](DATA_SOURCES.md) documents all three routes, the licence of
each source, and why the data is not bundled. `datasets/raw_tables/` in the git
index holds only LFS pointers — those paths are `export-ignore`, so no archive
of this repository ever claims to ship data it does not contain.

`framework/real_infra_load.py` builds the canonical form from the source CSVs:
8 fact tables in PostgreSQL and 14 dimension tables in MariaDB.
`datasets/raw_tables_manifest.json` records the expected row and column count of
each, so a reader can check their build against the reported one.

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

The code is [CC BY 4.0](LICENSE).

**Cite the version of record for now.** The manuscript this code accompanies is
published, and it names this repository as the artefact location:

> Alnahari, W., Arbaaeen, A., Hasanin, T., and Jambi, S. (2026). *SARAI:
> Sovereignty-Aware Risk Assessment Infrastructure for Reliable Federated
> Business Intelligence*. Results in Engineering 32, 113508.
> <https://doi.org/10.1016/j.rineng.2026.113508>

The code is archived at:

> **10.5281/zenodo.23839422** — <https://doi.org/10.5281/zenodo.23839422>

Cite that **concept DOI**, not a version DOI. It always resolves to the latest
archived snapshot, so it stays correct as new versions are published — which
matters here, because each archive contains this file and therefore contains the
identifier it is cited by. A version DOI written into the tree would be
self-referential and wrong the moment the next version is minted.

`CITATION.cff` carries it, so GitHub's "Cite this repository" button produces a
correct citation. [`ZENODO_DEPOSIT.md`](ZENODO_DEPOSIT.md) lists the version DOIs
and what each snapshot contains.

The five public datasets are **not** redistributed here and keep their own
upstream licences (two of them non-commercial): four from Kaggle — Olist
e-commerce, healthcare, credit-card fraud, supply chain — and one from the UCI
repository (online retail). Their provenance is recorded in
`datasets/metadata/`, and [`DATA_SOURCES.md`](DATA_SOURCES.md) says how to obtain
each one.
