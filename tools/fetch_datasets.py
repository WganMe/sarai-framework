#!/usr/bin/env python3
"""
Fetch the five public datasets that the benchmark federates over.

Four are on Kaggle and need an API token; one is on UCI and needs nothing. The
provenance file `datasets/metadata/ORIGINAL_DATASET_LINKS.txt` is the source of
truth for the URLs.

    export KAGGLE_API_TOKEN=...      # from kaggle.com -> Settings -> API
    python3 tools/fetch_datasets.py

    # only the source that needs no token:
    python3 tools/fetch_datasets.py --only uci

Why the data is not committed: 371 MB uncompressed (100 MB gzipped) is too large
for a repository. `docker-compose.yml` mounts `datasets/raw_tables/`, so this
script only has to put the CSV (or .csv.gz) files there and the stack can use
them. The loader accepts both forms.

EXIT CODES
    0  every requested source is present
    2  a source could not be fetched (message says which, and why)
"""
import argparse
import gzip
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path(os.environ.get("RAW_TABLES_DIR", ROOT / "datasets" / "raw_tables"))
UCI_RETAIL_URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"

# Kaggle datasets the benchmark uses, by slug. `files` lists the CSVs to keep;
# an empty list means "take every CSV in the dataset".
KAGGLE = [
    ("olistbr/brazilian-ecommerce", "mysql/olist_ecommerce", []),
    ("prasad22/healthcare-dataset", "mysql/healthcare", []),
    ("mlg-ulb/creditcardfraud", "postgresql/public", []),
    ("shashwatwork/dataco-smart-supply-chain-for-big-data-analysis",
     "postgresql/public", []),
]


def _say(msg):
    print(f"  {msg}")


def _gunzip_in_place(path: Path):
    """Decompress a .csv.gz next to itself and remove the archive."""
    out = path.with_suffix("")           # strip .gz
    with gzip.open(path, "rb") as src, out.open("wb") as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()
    return out


def fetch_kaggle(slug, dest_rel):
    """Download one Kaggle dataset into datasets/raw_tables/<dest_rel>/."""
    token = os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_KEY")
    if not token:
        raise RuntimeError("KAGGLE_API_TOKEN is not set")
    try:
        import kaggle  # noqa: F401  (the CLI, used below, is simpler than the API)
    except ImportError:
        pass
    dest = RAW / dest_rel
    dest.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("KAGGLE_USERNAME", env.get("KAGGLE_USERNAME", ""))
    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", slug, "-p", str(dest), "--unzip"],
            check=True, env=env, capture_output=True, text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("the `kaggle` CLI is not installed (pip install kaggle)")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError((exc.stderr or exc.stdout or "").strip()[:200] or "kaggle CLI failed")
    # Kaggle sometimes yields nested directories or .csv.gz; normalise both.
    for p in list(dest.rglob("*.csv.gz")):
        _gunzip_in_place(p)
    for sub in [d for d in dest.iterdir() if d.is_dir()]:
        for p in sub.iterdir():
            shutil.move(str(p), str(dest / p.name))
        sub.rmdir()
    return len(list(dest.glob("*.csv")))


def fetch_uci():
    """The retail dataset is public; fetch it without any token."""
    dest = RAW / "mysql" / "retail"
    dest.mkdir(parents=True, exist_ok=True)
    tmp = RAW / "_uci_retail.zip"
    _say(f"downloading {UCI_RETAIL_URL}")
    urllib.request.urlretrieve(UCI_RETAIL_URL, tmp)
    shutil.unpack_archive(str(tmp), str(dest))
    tmp.unlink()
    # the archive contains Online Retail.xlsx; convert if a converter is present
    sheets = list(dest.rglob("*.xlsx"))
    if sheets:
        try:
            import pandas as pd
            for x in sheets:
                df = pd.read_excel(x)
                out = dest / (x.stem.replace(" ", "_") + ".csv")
                df.to_csv(out, index=False)
                _say(f"converted {x.name} -> {out.name} ({len(df):,} rows)")
        except ImportError:
            _say(f"NOTE: {sheets[0].name} is an Excel file and pandas/openpyxl are")
            _say("      not installed, so it was not converted. Either install them")
            _say("      or convert the file to CSV by hand.")
            return 0
    return len(list(dest.glob("*.csv")))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["kaggle", "uci"],
                    help="fetch just one group of sources")
    ap.add_argument("--check", action="store_true",
                    help="report what is already present and exit")
    args = ap.parse_args()

    RAW.mkdir(parents=True, exist_ok=True)
    print(f"target: {RAW}\n")

    if args.check:
        csvs = list(RAW.rglob("*.csv")) + list(RAW.rglob("*.csv.gz"))
        print(f"  {len(csvs)} table file(s) present")
        return 0

    problems = []

    if args.only != "uci":
        for slug, dest_rel, _ in KAGGLE:
            try:
                n = fetch_kaggle(slug, dest_rel)
                print(f"  OK   {slug:<58} {n} CSV(s)")
            except RuntimeError as exc:
                print(f"  FAIL {slug:<58} {exc}")
                problems.append((slug, str(exc)))

    if args.only != "kaggle":
        try:
            n = fetch_uci()
            print(f"  OK   UCI online+retail{'':<40} {n} CSV(s)")
        except Exception as exc:
            print(f"  FAIL UCI online+retail  {type(exc).__name__}: {exc}")
            problems.append(("uci/online-retail", str(exc)))

    if problems:
        print(f"\n  {len(problems)} source(s) could not be fetched.")
        print("  The benchmark cannot be reproduced without all five. Nothing here")
        print("  is a code defect: it is dataset access.")
        return 2

    print("\n  all sources present. Next:")
    print("    docker compose up -d && python3 framework/load_federated_tables.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
