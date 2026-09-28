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
git lfs install && git lfs pull           # the datasets are tracked in LFS
python3 framework/load_federated_tables.py
python3 tools/verify_gold_queries.py

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

The five public datasets are tracked **in Git LFS**, in `datasets/raw_tables/` —
500 MB, and `creditcard.csv` alone is 144 MB, which is over GitHub's 100 MB
per-file limit for ordinary git. So LFS is not a preference here: it is the only
way that file can live in the repository at all, and a plain `git clone` without
`git lfs pull` yields 134-byte pointers instead of data.

`datasets/raw_tables/` is the **canonical** dataset and the one the benchmark
queries. It holds 8 PostgreSQL fact tables and 14 MariaDB dimension tables
covering all five domains, including the e-commerce tables that
`load_all_domains.py` does not build (that script covers four domains).

`tools/fetch_datasets.py` is the alternative route: it pulls the same data
straight from Kaggle and UCI into `datasets/sources/`. Four of the five sources
need a Kaggle token and only the UCI one does not, so LFS is the easier path for a
reader. Both are supported.

**Metering caveat, for the repository owner.** LFS download bandwidth is charged
to the repository owner and resets each month (10 GiB on Free and Pro alike, and
CI downloads count against it), so roughly 20 full fetches a month fit inside the
free quota. If that becomes a problem, the `datasets-v1` release asset holds the
same files and is unmetered.

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
| `datasets/raw_tables/` | the canonical dataset, in Git LFS (8 + 14 tables) |
| `docker-compose.yml` | PostgreSQL 13 + MariaDB 10.11 + PrestoDB 0.284 |
| `framework/presto/etc/` | the engine's full config: config, jvm, node, catalog |
| `framework/load_federated_tables.py` | loads `datasets/raw_tables/` into both |
| `tools/verify_gold_queries.py` | executes and validates all 50 gold queries |
| `tools/assert_published_values.py` | the 16 analysis assertions (claim A) |
| `tools/fetch_datasets.py` | alternative: pull the data from Kaggle/UCI |
| `.github/workflows/verify.yml` | both jobs, with their scope stated in the header |
| `reproduce.sh` | the whole thing, in order |
