# SARAI — reproducibility

The manuscript claims **"every reported number is regenerated rather than
transcribed."** That breaks into two claims, and it is worth being exact about
which one this repository proves, where, and which parts cannot be reproduced by
anyone.

| | Claim | Needs | Where it runs |
| --- | --- | --- | --- |
| **A** | The **analysis** reproduces — latency statistics, cost model, graded-sovereignty ladder | the committed run data + matplotlib | anywhere, ~30 s |
| **B** | The **benchmark** reproduces — 50 gold queries through the federated engine against a model | PostgreSQL + MariaDB + a federation engine (+ a model for the model half) | `reproduce.sh` locally, or the CI `federation` job (data half needs no model) |

## Run it

```bash
# A — no services required, ~30 s
python3 tools/assert_published_values.py

# both halves, from a clean clone
python3 tools/fetch_datasets.py --only release   # one request, no Kaggle token
docker compose up -d
python3 tools/wait_for_engine.py          # waits for "starting": false
python3 framework/real_infra_load.py      # 22 tables, with typed DDL
python3 tools/verify_gold_queries.py      # executes all 50 gold queries

# or all of the above
./reproduce.sh
```

The loader creates **8 fact tables in PostgreSQL and 14 dimension tables in
MariaDB** — the same shape the manuscript reports. The column types are
load-bearing: with every column typed as TEXT, the engine fails with
*"Unexpected parameters (varchar) for function avg"*, because it resolves function
signatures by type. That is why `real_infra_load.py`, which carries explicit typed
DDL for all 22 tables, is the loader to use.

> **CI.** `.github/workflows/verify.yml` runs the analysis half and the federation
  half on every push. The federation job starts PostgreSQL, MariaDB and PrestoDB,
  loads the 22 tables from the frozen dataset release, and executes all 50 gold
  queries; it needs no model and no Kaggle token, which is what makes it
  runnable in CI. The status is the badge in the README — a claim that lives in a
  badge cannot go stale the way a sentence in a frozen archive does.

Measured on a clean clone before publishing:

```
analysis : 16 published values reproduce from the committed run data.
federation: 50/50 gold queries executed and validated in 60.6s
            cross-engine joins: 24/50   (tier 3: 10/10, tier 4: 10/10, tier 5: 4/10)
```

### Where the source data comes from

The five public datasets are **not in this tree**. They are 500 MB under three
different upstream licences, two of them non-commercial, so they are published
frozen as the `datasets-v1` release asset (143 MiB, 15 files) and fetched in one
command:

```bash
python3 tools/fetch_datasets.py --only release
```

`framework/real_infra_load.py` then builds the form the benchmark actually
queries: **8 PostgreSQL fact tables and 14 MariaDB dimension tables**, covering
all five domains — including the e-commerce tables `load_all_domains.py` does not
build, since that script covers four domains. `datasets/raw_tables_manifest.json`
records the expected row and column count of each of the 22.

`tools/fetch_datasets.py` also fetches from upstream instead of the release
asset: four of the five sources need a Kaggle token, and only the UCI one does
not. [`DATA_SOURCES.md`](DATA_SOURCES.md) documents all three routes and the
licence of each source.

> **`datasets/raw_tables/` is tracked in Git LFS, so a plain clone leaves pointers
> until `git lfs pull` runs.** The dataset paths are marked `export-ignore`, so no
> archive of this repository claims to ship them. LFS downloads are metered
> against the owner's monthly quota; when that is exhausted the command fails with
> *"this repository exceeded its LFS budget"*, and Route 1 above needs neither LFS
> nor a Kaggle token.

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
`framework/real_infra_load.py` output.

## Why the data half is the strongest CI check available

It is deterministic. Given fixed inputs, 50/50 gold queries either pass or fail —
there is no sampling, no model variance, no service that can silently change
underneath it. That makes it the largest part of the claim a badge can honestly
carry.

## Files

| Path | Role |
| --- | --- |
| `datasets/raw_tables/` | LFS stubs in the index; built by `real_infra_load.py` from the release asset (8 + 14 tables) |
| `docker-compose.yml` | PostgreSQL 13 + MariaDB 10.11 + PrestoDB 0.284 |
| `framework/presto/etc/` | the engine's full config: config, jvm, node, catalog |
| `framework/real_infra_load.py` | loads `datasets/raw_tables/` into both, with typed DDL |
| `tools/wait_for_engine.py` | waits for `"starting": false`, not just HTTP 200 |
| `tools/verify_gold_queries.py` | executes and validates all 50 gold queries |
| `tools/assert_published_values.py` | the 16 analysis assertions (claim A) |
| `tools/fetch_datasets.py` | alternative: pull the data from Kaggle/UCI |
| `.github/workflows/verify.yml` | both jobs, with their scope stated in the header |
| `reproduce.sh` | the whole thing, in order |
