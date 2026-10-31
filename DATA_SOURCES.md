# Where the data is, and how to obtain it

This repository is the **code**. The benchmark data is tracked separately, in Git
LFS, and is deliberately absent from every archive of the repository. That is a
licensing decision, not an oversight, and it is why an archive here is small: see
[Why the data is not inside an archive](#why-the-data-is-not-inside-an-archive).

Every file the benchmark reads is reachable from a permanent address listed here.
There are three routes; `tools/fetch_datasets.py` automates all of them.

## The two forms of the data

| Form | What it is | Where |
| --- | --- | --- |
| **Source CSVs** | The five public datasets exactly as published upstream. 500 MB, 15 files. | Git LFS (`datasets/sources/`), **and** GitHub release [`datasets-v1`](https://github.com/WganMe/sarai-framework/releases/tag/datasets-v1), asset `sarai-datasets-v1.tar.gz` (143 MiB) |
| **Federated tables** | The 22 tables the benchmark actually queries: 8 PostgreSQL fact tables + 14 MariaDB dimension tables. | Git LFS (`datasets/raw_tables/`), or rebuilt from the source CSVs by `framework/real_infra_load.py`, which carries typed DDL for all 22 |

The second form is derived. `datasets/raw_tables_manifest.json` records the
expected shape of every table — name, row count and column count — so a reader
can check their own copy against the one the manuscript reports. Measured on a
full `git lfs pull`: all 22 row counts match the manifest, and all 15 source CSVs
are byte-identical to the frozen release asset.

> **Both data directories are marked `export-ignore` in `.gitattributes`, so they
> never appear in an archive.** This is deliberate: an archive containing 134-byte
> LFS pointer files would look complete and be silently empty. The v1.0.0 Zenodo
> payload made exactly that mistake and was withdrawn. A clone, by contrast, does
> have the files — as pointers until `git lfs pull` runs.

## Route 1 — the frozen release asset (recommended)

Unmetered, and frozen: the row counts stay what the manuscript reports.

```bash
curl -L -o /tmp/sarai-datasets-v1.tar.gz \
  https://github.com/WganMe/sarai-framework/releases/download/datasets-v1/sarai-datasets-v1.tar.gz
tar -xzf /tmp/sarai-datasets-v1.tar.gz -C datasets/sources --strip-components=1
python3 tools/fetch_datasets.py --check    # exit 0 means every file is in place
```

Freezing matters. A newer revision of a live Kaggle dataset changes row and
column counts, and the gold-query validators then fail in a way that looks like
a code bug rather than a data drift.

## Route 2 — `git lfs pull`

The same source files are tracked in Git LFS, so a clone can materialise them
in place:

```bash
git lfs install
git clone https://github.com/WganMe/sarai-framework.git
cd sarai-framework
git lfs pull
```

> **LFS bandwidth is metered against the repository owner** and resets monthly
> (10 GiB on Free and Pro alike, and CI downloads count against it). A clone can
> therefore fail with *"this repository exceeded its LFS budget"* near the end
> of a month even though the route itself is sound — that is a quota event, not a
> broken repository. Route 1 needs no quota at all and is the one to use when
> this happens.

## Route 3 — upstream, with `tools/fetch_datasets.py`

Four of the five sources need a Kaggle token; the UCI one does not.

```bash
export KAGGLE_USERNAME=... KAGGLE_KEY=...    # or ~/.kaggle/kaggle.json
python3 tools/fetch_datasets.py
```

## The five sources and their licences

None of these are relicensed by this repository. Two are non-commercial, which
is the second reason the data is not bundled: a single deposit carries a single
licence field and could not describe all five accurately.

| Domain | Dataset | Upstream | Licence |
| --- | --- | --- | --- |
| E-Commerce | Brazilian E-Commerce Public Dataset by Olist | [kaggle.com/datasets/olistbr/brazilian-ecommerce](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) | CC BY-NC-SA 4.0 |
| Healthcare | Healthcare Dataset | [kaggle.com/datasets/prasad22/healthcare-dataset](https://www.kaggle.com/datasets/prasad22/healthcare-dataset) | CC0 1.0 |
| Retail | Online Retail Data Set | [archive.ics.uci.edu/dataset/352](https://archive.ics.uci.edu/dataset/352/online+retail) | CC BY 4.0 |
| Financial | Credit Card Fraud Detection | [kaggle.com/datasets/mlg-ulb/creditcardfraud](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud) | DbCL 1.0 |
| Supply Chain | DataCo Smart Supply Chain for Big Data Analysis | [kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis](https://www.kaggle.com/datasets/shashwatwork/dataco-smart-supply-chain-for-big-data-analysis) | CC BY-NC-SA 4.0 |

Machine-readable provenance, including a row-count total per domain and the
table-name pattern each source feeds, is in
[`datasets/metadata/dataset_provenance_registry.csv`](datasets/metadata/dataset_provenance_registry.csv).

## Why the data is not inside an archive

Two reasons, and neither is storage:

1. **Licences.** Two sources are CC BY-NC-SA 4.0. A single Zenodo licence field
   cannot describe five sources under three different licences.
2. **A pointer is worse than an absence.** LFS-tracked files expand into real
   content only if the archiving machine has the LFS filters configured. When
   they do not, `git archive` emits 134-byte stubs. The result passes every
   file-count check and fails every read. Excluding the data and saying where it
   is removes the failure mode instead of documenting it.
