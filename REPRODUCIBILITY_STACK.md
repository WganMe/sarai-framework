# SARAI framework — the real open-source stack

**Repository:** <https://github.com/WganMe/sarai-framework>

> **Correction.** An earlier version of this file counted **8** components. That
> was wrong: it missed **Redis, n8n and Nginx** and named the wrong federation
> engine. Corrected below against the framework's own code and the patent.

---

## Why the earlier count was wrong

I had described the stack I *built*, not the stack the framework *specifies*. The
framework's own code names its components, and the patent states the production
stack verbatim.

| I said | The code and patent actually say | Where |
| --- | --- | --- |
| 8 components | **11 services** | below |
| "Trino 460" | **PrestoDB 0.284** | *"PrestoDB version 0.284 in coordinator mode with two connectors"* |
| *(omitted)* | **Redis 8.6.0** | *"Redis 8.6.0 (port 6379): In-memory cache and asynchronous execution broker"* |
| *(omitted)* | **n8n 2.8.3** | *"n8n version 2.8.3 serves as the central orchestration engine"* |
| *(omitted)* | **Nginx** | the `/health` action probes `http://127.0.0.1:80/` |

The decisive artifact is the framework's own `health` action in
`framework/deploy_framework_workflow.py`. It probes **five** services by name —
`WorkflowEngine` (:5678), `FederationEngine` (:8080), `DashboardPlatform` (:8088),
`LocalLLM` (:11434), `Nginx` (:80) — and then **Redis** via `redis-cli ping`.

> **Corrected twice.** An earlier version counted **8** components (wrong — it missed
> Redis and Nginx and named the wrong engine). A second version then described **11
> services in five layers**, taking the patent's layer diagram as the component list.
> That was also wrong: **n8n and Superset are not what makes the SARAI result run.**
> The corrected split is below — **core (6)** vs **optional orchestration/views (2)**.
>
> `docs/SARAI_N8N_CORRECTION.md` records the evidence and the downstream wording.

---

## Two different questions were being conflated

| Question | Answer |
| --- | --- |
| What does the **patent/thesis architecture describe**? | 5 layers including n8n as "the central orchestration engine" and Superset as the visualization layer |
| What **actually executes the SARAI result**? | PostgreSQL + MariaDB + a federation engine + Ollama + Python. **n8n is not on that path.** |
| What does the **patent's own `health` action probe**? | 5 services: WorkflowEngine, FederationEngine, DashboardPlatform, LocalLLM, Nginx (+ Redis) |
| What did **actually execute** in production? | **2,878 SQL queries, all from the Python harness** — 0 from any node client |

The layer diagram is an *architecture description*. It is not a dependency list, and
it should not be read as one.

---

## The core stack — six components, all required

Measured on this machine, all executing:

| # | Component | Version here | Port | Role |
| --- | --- | --- | --- | --- |
| 1 | PostgreSQL | 13.23 | 5432 | 8 fact tables, 1,442,510 rows |
| 2 | MariaDB | 11.8.9 | 3306 | 14 dimension tables, 200,676 rows |
| 3 | **Trino / PrestoDB** | **Trino 460** | 8080 | the federation engine — cross-catalog joins |
| 4 | Ollama | — | 11434 | local inference (σ_I = 1.0) |
| 5 | Llama 3.2 3B + Llama 3.1 8B | 2.0 / 4.9 GB | — | the evaluated local models |
| 6 | Python + requests | 3.9 | — | harness, analysis, figures |

Plus a JRE for the engine, and optionally a cloud gateway (OpenRouter) for the
comparison models.

## Optional orchestration / views — two components, not on the core path

| Component | Version | Port | What it actually provides |
| --- | --- | --- | --- |
| **n8n** | 2.8.3 | 5678 | an alternative HTTP entry point to the same logic. The Python harness already calls the engine directly, so **nothing in the result depends on it.** |
| **Apache Superset** | 6.0.0 | 8088 | the visualization layer. No reported metric is computed there. |
| Nginx | — | 80 | reverse proxy; :80 is cPanel here |
| Redis | 6.2.24 | 6379 | cache / broker for the optional components |

**Core = 6. Orchestration + views = 2 (n8n, Superset), plus a proxy and a cache.**

---

## What of this is actually installed on this machine

Measured, not assumed:

| Component | Specified | Reality here |
| --- | --- | --- |
| PostgreSQL | 15.16 | ✅ 13.23 running on :55432 (test instance) |
| MariaDB | 10.11.16 | ✅ 11.8.9 running on :33306 (test instance) |
| **Federation engine** | **PrestoDB 0.284** | ⚠️ **Trino 460** on :8080 — a *different product* |
| Ollama | 0.16.2 | ✅ running on :11434 |
| Llama 3.2 3B / 3.1 8B | 2.0 / 4.7 GB | ✅ both pulled and working |
| **Redis** | **8.6.0** | ⚠️ **redis-6.2.24 packaged, NOT running**; :6379 refuses |
| **n8n** | **2.8.3** | ⚠️ not installed; its role is optional (data survives in `~/.n8n`) |
| **Superset** | **6.0.0** | ❌ not installed (no binary, no module, no DB) |
| **Nginx** | — | ❌ not installed; :80 is **cPanel** |
| **PrestoDB** | **0.284** | ❌ not installed (no `/opt/presto*`, no binary) |

### n8n was installed and used, but it is not on the SARAI path

`~/.n8n` holds a genuine installation that has since been removed:

- `database.sqlite` (585 KB, Dec 2025) plus a 4 MB WAL; a second at
  `n8n-data/database.sqlite` (671 KB, Jan 2026) with a 116 KB log
- `n8nEventLog-1.log` recording **successful logins** by `wael@bcdr.sa` on
  2025-12-25 and 2025-12-26, SAML-authenticated, role `global:owner`
- `n8n-data/logs`: *"n8n ready on ::, port 5678"*, migrations running
- community nodes installed: **`n8n-nodes-bcdrllc` 2.0.0**, `n8n-nodes-ovh` 0.17.0

**But both workflow databases are empty** — `workflow_entity: 0`,
`execution_entity: 0`. The only surviving definition of the orchestration layer is
`framework/workflow.json`.

**And decisively: no n8n client has ever called the federation engine.** In Trino's
logged traffic (659,429 requests), **0 `/v1/statement` executions** came from any
node/axios client. All 2,878 successful executions were the Python harness. So the
orchestration route exists as code but **never carried the workload.**

Also note the workflow's headers: its Code node sends the **legacy `X-Presto-*`**
headers, which the deployed engine **rejects with HTTP 401** (verified: `X-Trino-*`
→ 200, `X-Presto-*` → 401). It would need changing before it could run here at all.

### `framework/workflow.json` is an optional n8n export whose node types were rewritten

```json
{"name": "Context-Aware BI Framework — Unified API",
 "nodes": [...], "connections": {...},
 "settings": {"executionOrder": "v1"}}
```

Its two nodes are a **Webhook** (`POST /webhook/framework`) and a **Code** node
holding **24,369 characters** of JavaScript implementing all seven actions.

Two measured points:

1. **The node types are not n8n's.** They read `workflow-nodes-base.webhook` and
   `workflow-nodes-base.code`; n8n's real type strings are `n8n-nodes-base.*`.
   The `n8n-` prefix was replaced with `workflow-`, **which is why `grep -i n8n`
   over the repository returns nothing.** As exported, this file would not import
   cleanly into n8n.
2. It is nonetheless genuine — the schema is n8n's (`executionOrder`), the webhook
   path matches `deploy_framework_workflow.py`, and that script posts it to
   `http://127.0.0.1:5678/api/v1`. It hardcodes workflow id `zpJWWljIklNinXF4` and
   reads its API key from `/var/www/.env`.

---

## The five data sources

From `datasets/metadata/ORIGINAL_DATASET_LINKS.txt` and the provenance registry —
**all five are public and openly licensed**:

| Domain | Source | Licence note | Tables | Rows |
| --- | --- | --- | --- | --- |
| E-Commerce | Kaggle `olistbr/brazilian-ecommerce` | Kaggle terms | 7 | 550,688 |
| Healthcare | Kaggle `prasad22/healthcare-dataset` | Kaggle terms | 5 | 135,728 |
| Retail | **UCI** dataset 352 `online+retail` | UCI terms | 3 | 550,239 |
| Financial | Kaggle `mlg-ulb/creditcardfraud` | Kaggle terms | 3 | 249,387 |
| Supply Chain | Kaggle `shashwatwork/dataco-smart-supply-chain…` | Kaggle terms | 4 | 201,233 |

Four Kaggle + one UCI. Only the UCI source can be fetched without a token.

---

## What has actually been proven, and how

### 1. The federation works — 50/50 gold queries

The benchmark's own documented validity gate is: *"every gold query is executed
and required to satisfy its validator; the run aborts if any fails."*

Re-run 2026-09-28 05:58 by importing the framework's **own** module and calling its
**own** `run_presto()` and per-question validators — not a reimplementation:

```
questions: 50
RESULT: 50/50 gold queries PASS in 56.4s
failures: none
cross-catalog (federated) queries: 24/50
```

Every tier executes: T1 10/10, T2 10/10, T3 10/10, T4 10/10, T5 10/10.

### 2. Genuine cross-engine joins, not two independent reads

**24 of the 50 gold queries read both catalogs** — all 10 of Tier 3, all 10 of
Tier 4, and 4 of Tier 5. Example, `T3-Q01`:

```sql
SELECT ... FROM postgresql.public.olist_orders o
          JOIN mysql.bcdr_framework.olist_customers c
            ON o.customer_id = c.customer_id
```

Verified executing: returns 10 rows. That is one query the federation engine
resolves across two different database products — the thing the paper is about.

### 3. Row counts reconcile with the load

| Table | Loaded | Query result |
| --- | --- | --- |
| `postgresql.public.olist_orders` | 99,441 | 99,441 |
| `mysql.bcdr_framework.olist_customers` | 99,441 | 99,441 |

### 4. The analysis claim reproduces in full — 16/16 assertions

```
16 published values reproduce from the committed run data.
The manuscript's reproducibility claim holds for the analysis.
```

Nine cost-model values (Sec 7.3), three sovereignty-ladder values (Sec 3.3 /
Table 4), four per-model latency values (Table 10). Each assertion prints the
manuscript value and its section, so a mismatch names the drift.

### 5. A full 50-question model evaluation runs end to end

`llama3.2:3b` through the live federation, all 50 questions, generated SQL
executed and validated:

```
MODEL: llama3.2:3b — 22/50 correct (44.0%)
  Tier 1: 9/10
  Tier 2: 2/10
  Tier 3: 5/10
  Tier 4: 4/10
  Tier 5: 2/10
total wall: 311s | mean generation latency: 5.23s
```

**What this does and does not show.** It shows the whole model half works: prompt →
generation → SQL → federated execution → validator → score. It does **not**
reproduce the manuscript's published accuracies, because those are from cloud
models (Gemma-3 27B, Llama 3.3 70B, DeepSeek R1), not from `llama3.2:3b`.

It does, however, reproduce the manuscript's **structural** finding: correctness
falls steeply as tier rises (90% → 20% here), which is the paper's central claim
about SQL complexity dominating model choice.

**Latency is not reproducible on this box.** `llama3.1:8b` took **92.8 s** per
question on CPU here, against the published 23.71 s. Running both models for 50
questions exceeds a 15-minute budget for that reason alone. Correctness is
reproducible; timing is hardware-bound and must not be asserted on a runner.

### 6. Running the harness naively looks like a hang

Worth recording: `framework/benchmark_50q_realinfra.py --local-only` was run and
**timed out at 900 s with no output at all.** It did not fail — `run_presto()` is
properly bounded (a 120-iteration poll loop with a 30 s deadline), and the model
calls are bounded too. It is simply slow, and stdout is buffered when piped, so
nothing appears until it ends. Run it with `python -u` and expect ~20 minutes for
both local models. A CI job must not run this script as-is.

---

## Code defects found while proving this (all fixed, all portable)

The framework did not reproduce from a clean clone. Four defects, each of which
would have blocked a reader or a reviewer:

1. `framework/revision_stats.py` — hardcoded an absolute path to a results file on
   the author's machine. Fixed to resolve relative to the file.
2. `framework/real_infra_load.py` — same hardcoded path, plus hardcoded DB ports
   5432/3306. Fixed to relative paths and `POSTGRES_PORT` / `MARIADB_PORT` env
   overrides.
3. `framework/sovereignty_sensitivity.py` — wrote its figure three levels up
   through a nested checkout, so the output location depended on how the repo
   happened to be checked out. Fixed: writes beside itself, or to `--out DIR`.
4. `datasets/benchmark_results_20260219_054729.json` — **the one benchmark run the
   manuscript cites was gitignored.** A reader would clone the repo and find its
   only input missing. Fixed with a narrowed `!` negation; the other runs and the
   371 MB of raw tables stay excluded.

Defect 4 is the one that matters most for the reproducibility claim: without it
the repository could not reproduce its own published numbers.

---

## The two halves of reproducibility — keep them separate

The manuscript claims *"every reported number is regenerated rather than
transcribed."* That breaks into two different claims, and it is worth being
precise about which is proven where:

| | Claim | Needs | Runs on a hosted CI runner? |
| --- | --- | --- | --- |
| **A** | the **analysis** reproduces — latency stats, cost model, sovereignty ladder | the committed run data JSON + matplotlib | ✅ **yes** — this is what the CI badge proves |
| **B** | the **benchmark** reproduces — 50 questions through the federation against an LLM | all **11 services** above | ❌ **no** — needs Postgres, MariaDB, PrestoDB, Ollama, n8n, Superset, Redis and the data, none of which a runner can supply |

`tools/assert_published_values.py` checks claim A with **16 assertions**, each
quoting the manuscript value and its section. `.github/workflows/verify.yml` runs
it on every push and **states in its own header what it does not prove**, so the
badge cannot be over-read.

Claim B can only be shown by reproducing it on a real machine — which is what the
evidence above does.

---

## Can CI cover all of this? — the precise answer

The honest answer is **no, not all of it — and it should not try.** The current
workflow covers only claim A. Here is exactly what is and is not reachable, and
what each route costs.

### First, a fact that supersedes the question

`.github/workflows/verify.yml` is **not committed**. Measured:

```
git ls-files .github/workflows   ->  (empty)
GitHub API contents/.github/workflows -> 404 Not Found
```

So **the CI has never run, and there is no badge.** Any statement that CI "proves
reproducibility" today is untrue — nothing has executed it, not even once. That is
the first thing to fix, and it is a one-commit fix.

### What is coverable, tier by tier

| Tier | What it proves | Cost | Verdict |
| --- | --- | --- | --- |
| **1. Current workflow** | analysis (claim A), 16 assertions from committed run data | ~30 s | ✅ works — but uncommitted, so it has never run |
| **2. + federation services** | that PostgreSQL + MariaDB + **PrestoDB 0.284** start and the **50 gold queries execute** — claim B's data half | 3 container services, ~1 GB image, ~15 min | ✅ **feasible** — all three images exist (`postgres:13`, `mariadb:11.8`, `prestodb/presto:0.284`) |
| **3. + local LLM** | that a model answers and the harness scores it | Ollama on a runner, 2 GB and ~2.5 min per model for `llama3.2:3b` | ⚠️ **technically possible, practically no** |
| **4. + published accuracy figures** | the paper's reported accuracies (60% / 74% / 90%) | **a specific cloud model at a specific version** | ❌ **impossible with local models** |

### Why tier 4 is impossible, and tier 3 is a trap

The manuscript's model accuracies come from **cloud** models — the script names
them:

```
google/gemma-3-27b-it:free
meta-llama/llama-3.3-70b-instruct:free
deepseek/deepseek-r1-0528:free
```

Those are **hosted endpoints called over HTTP**. No amount of CI machinery can pin
a hosted model's behaviour, and a free tier endpoint can change or vanish without
notice. So the published accuracy numbers are **not reproducible by CI, and not
reproducible by anyone**, unless the exact model versions are pinned and archived.
That is a real limitation of the claim itself, not of the workflow.

Tier 3 looks reachable but is a false economy: running `llama3.2:3b` on a runner
proves the *harness* works, not the *paper's numbers*, because the paper's numbers
are not from that model. A green badge from tier 3 would invite exactly the
over-reading the current workflow header warns against.

### The volume problem

| Item | Size |
| --- | --- |
| raw tables (22 CSV) | **371 MB** |
| PrestoDB 0.284 image (est.) | ~1 GB |
| `llama3.2:3b` | 2.0 GB |
| `llama3.1:8b` | 4.9 GB |
| all local Ollama models | 15.4 GB |

A GitHub-hosted `ubuntu-24.04` runner has roughly 14 GB free. Tier 3 with both
models does not fit alongside the federation image and the data. So even the
possible version needs care, and a self-hosted runner if it must be complete.

### The dataset blocker, which decides everything

371 MB of raw tables is gitignored, and **4 of the 5 sources are on Kaggle**, which
needs an API token. Two routes, neither taken:

- **Download route** → needs a Kaggle token as a repository secret, and adds a
  network dependency and a Kaggle rate limit to every CI run.
- **Vendored route** → a release artifact, or `git-lfs`. Reliable, and it makes the
  run hermetic. 371 MB is large for a repo but small for a release asset.

There is also a correctness trap: if the downloader fetches a *newer* revision of a
Kaggle dataset, the row counts change and the validators fail — a false negative
that looks like a code bug. The row counts in the manuscript are pinned to
specific dataset revisions. **Vendoring the exact files is the only way to keep the
run honest.**

### What a reviewer would actually accept

A reviewer does not need CI to re-run the benchmark. They need:

1. **A working workflow, committed** — so the badge exists and means something.
2. **A statement of what the badge covers** — the current header does this well.
3. **An executable reproduction path for claim B**, documented and verified once on
   real hardware, with the exact component versions pinned.

A badge that overclaims is worse than no badge. The current design — CI proves the
analysis, the README documents the full stack, the stack is proven once on real
hardware with measured evidence — is the defensible arrangement. **What is missing
is not more CI machinery; it is committing what already exists and pinning the
versions.**

### If you want CI to cover as much as possible

The defensible maximum is **tier 2**: add PostgreSQL, MariaDB and **PrestoDB
0.284** as services (`prestodb/presto:0.284` exists on Docker Hub), vendor the
371 MB dataset, and assert **50/50 gold queries execute**. That covers the whole
data half of claim B — the federation, the cross-engine joins, the validators —
with no LLM, no model-version problem, and a deterministic result. State plainly
that the model half is not covered, and why.

Note the product choice: CI must run **PrestoDB**, the engine the patent names,
not Trino. Running Trino would produce a `:8080/v1/info` that disagrees with the
record while every query still passed — a green badge asserting the wrong thing.

---

## What is still missing for a clean-machine reproduction

1. **Dataset acquisition is unsolved.** 371 MB of raw tables is gitignored. Two
   routes, neither chosen: a *download* route needs a Kaggle token (4 of 5
   sources), or a *vendored* route needs a 371 MB release artifact.
2. **The federation engine is the wrong product here.** The framework specifies
   **PrestoDB 0.284 and pins it in the patent**; this machine runs **Trino 460**.
   They are different products with different version output and different headers
   (the framework's own headers still say `X-Presto-User`). Anyone reproducing
   must install PrestoDB 0.284, not Trino, or the `:8080/v1/info` evidence will
   not match the record.
3. **Superset, Redis and n8n are all absent.** Superset (6.0.0) is not installed
   at all; Redis is packaged at 6.2.24 against a specified 8.6.0 and is not
   running; n8n's binary is gone though its data directory survives.
4. **Nothing is committed — and this includes the workflow itself.** Measured:
   `git ls-files .github/workflows` is empty and the GitHub API returns 404 for
   that path. So **CI has never run and there is no badge.** All fixes are local
   only: `.github/`, `tools/`, `framework/deployment_cost.py`,
   `framework/sovereignty_framework.py`-adjacent edits,
   `framework/sovereignty_sensitivity.py`, the three path fixes and the
   `.gitignore` negation. A reader cloning the repo today still hits all four
   defects, and `actions` shows nothing.
5. **The published model accuracies cannot be reproduced by anyone** unless the
   exact cloud model versions are pinned and archived. This is a limitation of the
   claim, and it should be stated rather than papered over by a local-model CI job
   that proves something different.

---

## The general lesson from getting this wrong

Two distinct failure modes, both worth remembering:

1. **I described the stack I built rather than the stack specified.** The two
   differ in the single most important component: Trino where the patent says
   PrestoDB. Reading the *code and the patent* first, rather than starting from
   what I had running, would have got it right the first time.
2. **A search for a product name is not the same as reading the files.** `grep -i
   n8n` over the repository returns nothing, yet n8n *is* Layer 2 of the
   architecture — because the `n8n-` prefix was stripped from the node types in
   `workflow.json`. The product's own data directory sat in `~/.n8n` the whole
   time. Look for what a component *does* (a port, an endpoint, an env key, a
   data directory), not just for its name.
