# SARAI — reproducibility

The manuscript claims **"every reported number is regenerated rather than
transcribed."** That breaks into two claims, and it is worth being exact about
which one this repository proves, where, and which parts cannot be reproduced by
anyone.

| | Claim | Needs | Where it runs |
| --- | --- | --- | --- |
| **A** | The **analysis** reproduces — latency statistics, cost model, graded-sovereignty ladder | the committed run data + matplotlib | GitHub Actions, anytime |
| **B** | The **benchmark** reproduces — 50 gold queries through the federated engine against a model | PostgreSQL + MariaDB + a federation engine (+ a model for the model half) | `reproduce.sh`, or the CI `federation` job (data half only) |

## Run it

```bash
# A — no services required, ~30 s
python3 tools/assert_published_values.py

# both halves, from a clean clone
export GH_TOKEN=...                   # a token that can read the repository
python3 tools/fetch_datasets.py --only release   # one 143 MB asset
python3 framework/load_all_domains.py            # source -> both databases
docker compose up -d
python3 framework/load_federated_tables.py       # raw tables -> both engines
python3 tools/verify_gold_queries.py             # execute all 50 gold queries

# or all of the above
./reproduce.sh
```

The loader produces **8 fact tables in PostgreSQL and 14 dimension tables in
MariaDB** — the same shape the manuscript reports, read from the CSV headers
rather than from a schema file.

Measured on a clean clone before publishing:

```
analysis : 16 published values reproduce from the committed run data.
federation: 50/50 gold queries executed and validated in 60.6s
            cross-engine joins: 24/50   (tier 3: 10/10, tier 4: 10/10, tier 5: 4/10)
```

### Where the source data comes from

371 MB of source tables are **not** in the tree. They are published, **frozen**, as
a release asset:

> `https://github.com/WganMe/sarai-framework/releases/tag/datasets-v1`
> → `sarai-datasets-v1.tar.gz` (143 MB, 15 CSVs)

`tools/fetch_datasets.py --only release` fetches it. That route needs **no Kaggle
account**: it uses `gh`, which authenticates from `GITHUB_TOKEN` in CI or from
`gh auth login` locally. In CI the workflow's own `secrets.GITHUB_TOKEN` is enough,
so the `federation` job runs with no extra configuration. (The repository is
private, so the plain browser URL returns 404 without a token — use `gh`, or the
API asset endpoint with the `Accept: application/octet-stream` header.)

#### Why frozen rather than fetched live

| | Frozen release asset | Live fetch from Kaggle/UCI |
| --- | --- | --- |
| Needs a Kaggle token | **no** | yes, for 4 of the 5 sources |
| Reproduces the reported row counts | **yes** | only if the dataset revision has not changed |
| Runs unattended in CI | **yes** | only with a stored secret |

The trap this avoids: if a fetcher pulls a *newer* revision of a Kaggle dataset,
the row counts change and the gold-query validators fail — a false negative that
looks like a code bug. The counts in the manuscript are pinned to specific
revisions, so the exact files matter.

`tools/fetch_datasets.py` (without `--only release`) still supports fetching each
source individually, and falls back to that automatically if the release is
unavailable. The five upstream sources and their licences:

| Domain | Source | Licence |
| --- | --- | --- |
| E-Commerce | Kaggle `olistbr/brazilian-ecommerce` | CC BY-NC-SA 4.0 |
| Healthcare | Kaggle `prasad22/healthcare-dataset` | CC0-1.0 |
| Retail | UCI dataset 352 `online+retail` | CC BY 4.0 |
| Financial | Kaggle `mlg-ulb/creditcardfraud` | DbCL-1.0 |
| Supply Chain | Kaggle `shashwatwork/dataco-smart-supply-chain-...` | CC BY-NC-SA 4.0 |

Each source keeps its upstream licence; this repository's licence does not
relicense them.

## What is deliberately *not* covered, and why

These are limits of the claim, not omissions from the code.

**1. The published model accuracies (60% / 74% / 90%).** They come from hosted
models called over HTTP. The scripts name them:

```
google/gemma-3-27b-it:free
meta-llama/llama-3.3-70b-instruct:free
deepseek/deepseek-r1-0528:free
```

A free tier endpoint can change or be withdrawn without notice, so **no one can
reproduce these numbers** unless the exact model versions are pinned and archived.
Running a local model instead would not reproduce them either — it would only
show the harness works, while inviting the reader to believe something untrue.
This is stated rather than papered over.

**2. Latency.** Timing is hardware-bound. `llama3.1:8b` took **92.8 s** per
question on a CPU-only box against the published **23.71 s**. Correctness is
reproducible; timing is not, and the CI does not assert it.

**3. The dashboard and the orchestration layer.** Neither is on the path that
produced any reported number. `setup_superset*.py` provisions datasets, charts
and dashboards; `workflow.json` is an importable orchestrator definition. Both
are provided so the described system can be rebuilt, but the reported results do
not depend on them.

## The federation engine — read this before comparing versions

The patent specifies **PrestoDB 0.284**. The `docker-compose.yml` here runs
**PrestoDB 0.284** for that reason, and so does CI, so a green badge means the
same thing locally and in CI.

The framework is engine-agnostic by construction: connections come from the
environment, queries go to the standard `/v1/statement` REST endpoint, and the
header family is configurable —

| Client | Header style |
| --- | --- |
| Python harness | `X-Trino-*` (accepted by both PrestoDB and Trino) |
| `workflow.json` code node | `X-Trino-*` by default; set `ENGINE_HEADER_STYLE=presto` for `X-Presto-*` |

Both products implement the same protocol, so the same code and the same SQL run
unchanged against either. The engine in use at any moment is recorded, not
assumed — `reproduce.sh` prints `nodeVersion` and `environment` from `/v1/info`.

## What was verified once, on real hardware

The benchmark run the manuscript cites (2026-02-19) was executed on a dedicated
testbed, not on a CI runner. That deployment has since been retired and the
hardware replaced; the surviving evidence is:

- `datasets/benchmark_results_20260219_054729.json` — the run itself, carried
  through the move intact (identical checksum in both working copies)
- the orchestration layer's own directory and startup log, recording
  `n8n ready on ::, port 5678`, its version, and successful authenticated logins
- the deployment configuration, which names each component and version

This is why the version list in the manuscript differs from what any one machine
shows today: it is a record of the deployment as built, across more than one
host, over a period of months. The row and table counts are the part that must
match a specific database — and those are the numbers to check against
`load_federated_tables.py` output.

## Why the data half is the strongest CI check available

It is deterministic. Given fixed inputs, 50/50 gold queries either pass or fail —
there is no sampling, no model variance, no service that can silently change
underneath it. That makes it the largest part of the claim a badge can honestly
carry.

## Files

| Path | Role |
| --- | --- |
| `docker-compose.yml` | PostgreSQL 13 + MariaDB 10.11 + PrestoDB 0.284 |
| `framework/presto/catalog/*.properties` | the `postgresql` and `mysql` connectors |
| `framework/load_federated_tables.py` | loads `datasets/raw_tables/` into both |
| `tools/verify_gold_queries.py` | executes and validates all 50 gold queries |
| `tools/assert_published_values.py` | the 16 analysis assertions (claim A) |
| `.github/workflows/verify.yml` | both jobs, with their scope stated in the header |
| `reproduce.sh` | the whole thing, in order |
