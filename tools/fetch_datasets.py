#!/usr/bin/env python3
"""
Fetch the five public source datasets the benchmark federates over, laid out
exactly where `framework/load_all_domains.py` expects to read them.

    python3 tools/fetch_datasets.py

    # just the source that needs no token:
    python3 tools/fetch_datasets.py --only uci

WHERE THINGS GO
    datasets/sources/healthcare/healthcare_dataset.csv
    datasets/sources/retail/data.csv
    datasets/sources/financial/creditcard.csv
    datasets/sources/supply_chain/DataCoSupplyChainDataset.csv
    datasets/sources/olist/olist_orders_dataset.csv   (9 files, names as published)

Those names and sub-directories are not free choices: they are what
`load_all_domains.py` opens, so changing them here silently breaks the ETL.

WHY THE DATA IS NOT IN THE REPOSITORY
    371 MB uncompressed. `datasets/sources/` is gitignored; this script fetches it.

AUTHENTICATION
    The `kaggle` CLI authenticates from ~/.kaggle/kaggle.json, or from the
    KAGGLE_USERNAME and KAGGLE_KEY environment variables. KAGGLE_API_TOKEN is not
    a CLI variable, so this script maps it onto those two when it is a
    `username:key` pair. A bare token with no username cannot be mapped; the
    script says so rather than failing obscurely.

EXIT CODES
    0  every expected file is present
    2  something is missing or unreadable (the message names it)
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = Path(os.environ.get("SOURCES_DIR", ROOT / "datasets" / "sources"))
# The bundle must live OUTSIDE the checkout: it is 143 MB, over GitHub's 100 MB
# per-file limit, so committing it would be rejected. Default to the system temp
# directory; override with BUNDLE_DIR if you want it kept between runs.
BUNDLE_DIR = Path(os.environ.get("BUNDLE_DIR", Path(tempfile.gettempdir()) / "sarai-bundles"))
UCI_RETAIL_URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"

# The frozen source bundle. Published as a release asset because 371 MB is far
# too large for the tree, and freezing matters: a newer Kaggle revision changes
# row counts and makes the gold-query validators fail in a way that looks like a
# code bug. This is the preferred source because it needs no Kaggle token.
RELEASE_REPO = os.environ.get("SARAI_REPO", "WganMe/sarai-framework")
RELEASE_TAG = "datasets-v1"
ASSET_NAME = "sarai-datasets-v1.tar.gz"

# slug -> destination sub-directory under datasets/sources/
KAGGLE = [
    ("olistbr/brazilian-ecommerce", "olist"),
    ("prasad22/healthcare-dataset", "healthcare"),
    ("mlg-ulb/creditcardfraud", "financial"),
    ("shashwatwork/dataco-smart-supply-chain-for-big-data-analysis", "supply_chain"),
]

# The exact paths load_all_domains.py opens, relative to datasets/sources/.
EXPECTED = [
    "healthcare/healthcare_dataset.csv",
    "retail/data.csv",
    "financial/creditcard.csv",
    "supply_chain/DataCoSupplyChainDataset.csv",
    "olist/olist_orders_dataset.csv",
    "olist/olist_order_items_dataset.csv",
    "olist/olist_customers_dataset.csv",
    "olist/olist_products_dataset.csv",
]


def say(msg):
    print(f"  {msg}")


# --------------------------------------------------------------------- helpers
def fetch_release_bundle() -> int:
    """Download and extract the frozen bundle from the release.

    Preferred over the per-source route: it is one request, needs no Kaggle
    token, and is pinned to the revisions the reported row counts were measured
    against. Uses `gh` when available (which authenticates from GITHUB_TOKEN in
    CI, or locally from `gh auth login`), falling back to curl with a token.
    """
    SOURCES.mkdir(parents=True, exist_ok=True)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BUNDLE_DIR / ASSET_NAME

    if shutil.which("gh"):
        cmd = ["gh", "release", "download", RELEASE_TAG, "--repo", RELEASE_REPO,
               "--pattern", ASSET_NAME, "--dir", str(BUNDLE_DIR), "--clobber"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or exc.stdout or "").strip().splitlines()
            raise RuntimeError(tail[-1][:160] if tail else "gh release download failed")
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        url = (f"https://api.github.com/repos/{RELEASE_REPO}/releases/tags/{RELEASE_TAG}")
        hdrs = ["-H", "Accept: application/vnd.github+json"]
        if token:
            hdrs += ["-H", f"Authorization: Bearer {token}"]
        try:
            meta = json.loads(subprocess.run(
                ["curl", "-sSL", *hdrs, url],
                check=True, capture_output=True, text=True).stdout)
            asset = next(a for a in meta["assets"] if a["name"] == ASSET_NAME)
        except Exception as exc:
            raise RuntimeError(f"could not read release metadata via curl: {exc}")
        # For a private repository the browser URL 404s without a token, so go
        # through the API asset endpoint when we have one.
        dl = asset["url"] if token else asset["browser_download_url"]
        dh = ["-H", "Accept: application/octet-stream"]
        if token:
            dh += ["-H", f"Authorization: Bearer {token}"]
        subprocess.run(["curl", "-sSL", *dh, "-o", str(tmp), dl],
                       check=True, capture_output=True, text=True)

    with tarfile.open(tmp) as tf:
        # The archive's root IS `sources/`, so extract into its PARENT and the
        # contents land at datasets/sources/... -- which is what the ETL reads.
        tf.extractall(SOURCES.parent)
    return len(list(SOURCES.rglob("*.csv")))


def _kaggle_env():
    """Expose the CLI's credential names from whichever form is configured."""
    env = dict(os.environ)
    if not env.get("KAGGLE_KEY"):
        tok = env.get("KAGGLE_API_TOKEN", "")
        if tok:
            if ":" in tok:                    # the documented `username:key` form
                user, key = tok.split(":", 1)
                env.setdefault("KAGGLE_USERNAME", user)
                env["KAGGLE_KEY"] = key
            elif env.get("KAGGLE_USERNAME"):
                env["KAGGLE_KEY"] = tok
    return env


def _auth_problem():
    if (Path.home() / ".kaggle" / "kaggle.json").exists():
        return None
    env = _kaggle_env()
    if env.get("KAGGLE_USERNAME") and env.get("KAGGLE_KEY"):
        return None
    if os.environ.get("KAGGLE_API_TOKEN") and not os.environ.get("KAGGLE_USERNAME"):
        return ("KAGGLE_API_TOKEN is set but has no username and is not a\n"
                "        `username:key` pair. Either set KAGGLE_USERNAME as well,\n"
                "        or place kaggle.json in ~/.kaggle/.")
    return "no Kaggle credentials (need kaggle.json, or KAGGLE_USERNAME + KAGGLE_KEY)"


def _flatten(dest: Path):
    """Move files out of any nested directory Kaggle created."""
    for sub in [d for d in dest.iterdir() if d.is_dir()]:
        for p in list(sub.rglob("*")):
            if p.is_file():
                shutil.move(str(p), str(dest / p.name))
        shutil.rmtree(sub, ignore_errors=True)


def _unzip_all(dest: Path):
    for z in list(dest.glob("*.zip")):
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        z.unlink()
    _flatten(dest)


def _gunzip_all(dest: Path):
    for g in list(dest.glob("*.gz")):
        if g.stem.endswith(".csv"):
            with gzip.open(g, "rb") as src, (dest / g.stem).open("wb") as dst:
                shutil.copyfileobj(src, dst)
            g.unlink()


def fetch_kaggle(slug: str, subdir: str) -> int:
    dest = SOURCES / subdir
    dest.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["kaggle", "datasets", "download", "-d", slug, "-p", str(dest), "--unzip"],
            check=True, env=_kaggle_env(), capture_output=True, text=True,
        )
    except FileNotFoundError:
        raise RuntimeError("the `kaggle` CLI is not installed (pip install kaggle)")
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or exc.stdout or "").strip().splitlines()
        raise RuntimeError(lines[-1][:150] if lines else "kaggle CLI failed")
    _unzip_all(dest)
    _gunzip_all(dest)
    return len(list(dest.glob("*.csv")))


def fetch_uci_retail() -> int:
    """UCI online+retail ships as an .xlsx; the loader wants data.csv."""
    dest = SOURCES / "retail"
    dest.mkdir(parents=True, exist_ok=True)
    target = dest / "data.csv"
    if target.exists() and target.stat().st_size > 100_000:
        say("retail/data.csv already present")
        return 1

    say(f"downloading {UCI_RETAIL_URL}")
    tmp = SOURCES / "_uci_retail.zip"
    urllib.request.urlretrieve(UCI_RETAIL_URL, tmp)
    with zipfile.ZipFile(tmp) as zf:
        zf.extractall(dest)
    tmp.unlink()
    _flatten(dest)

    # already a CSV under another name?
    candidates = [p for p in dest.glob("*.csv") if p.name != "data.csv"]
    if candidates and not list(dest.glob("*.xlsx")):
        shutil.move(str(candidates[0]), str(target))
        say(f"{candidates[0].name} -> data.csv")
        return 1

    xlsx = next(iter(dest.glob("*.xlsx")), None)
    if not xlsx:
        raise RuntimeError("the UCI archive contained neither a CSV nor an .xlsx")
    try:
        import pandas as pd
    except ImportError:
        raise RuntimeError(
            f"{xlsx.name} is an Excel file and pandas/openpyxl are not installed;\n"
            "        `pip install pandas openpyxl`, or convert it to data.csv by hand")
    df = pd.read_excel(xlsx, dtype=str)
    df.to_csv(target, index=False)
    xlsx.unlink()
    say(f"converted {xlsx.name} -> data.csv ({len(df):,} rows)")
    return 1


# ------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["release", "kaggle", "uci"],
                    help="fetch just one source group (default: release, then fallback)")
    ap.add_argument("--check", action="store_true",
                    help="report what is present and exit 0/2")
    args = ap.parse_args()

    SOURCES.mkdir(parents=True, exist_ok=True)
    print(f"target: {SOURCES}\n")

    if args.check:
        present = 0
        for rel in EXPECTED:
            ok = (SOURCES / rel).exists()
            present += ok
            print(f"  {'OK  ' if ok else 'MISS'} {rel}")
        print(f"\n  {present}/{len(EXPECTED)} expected files present")
        return 0 if present == len(EXPECTED) else 2

    problems = []

    # Preferred: the frozen bundle, one request, no Kaggle token.
    if args.only in (None, "release"):
        try:
            n = fetch_release_bundle()
            print(f"  OK   frozen bundle  {n} CSV(s)  <- release {RELEASE_TAG}")
        except Exception as exc:
            if args.only == "release":
                print(f"  FAIL frozen bundle  {type(exc).__name__}: {exc}")
                problems.append((f"release:{RELEASE_TAG}", str(exc)))
            else:
                print(f"  --   frozen bundle unavailable ({type(exc).__name__}); "
                      "falling back to per-source fetch")

    # Fallback: fetch each source ourselves. Only needed if the release is gone.
    need_fallback = any(not (SOURCES / rel).exists() for rel in EXPECTED)
    if need_fallback and args.only != "release":
        if args.only != "uci":
            problem = _auth_problem()
            if problem:
                print(f"  FAIL Kaggle authentication: {problem}")
                problems.append(("kaggle-auth", problem))
            else:
                for slug, subdir in KAGGLE:
                    try:
                        n = fetch_kaggle(slug, subdir)
                        print(f"  OK   {subdir:<13} {n} CSV(s)  <- {slug}")
                    except RuntimeError as exc:
                        print(f"  FAIL {subdir:<13} {exc}")
                        problems.append((slug, str(exc)))

        if args.only != "kaggle":
            try:
                fetch_uci_retail()
                print("  OK   retail        <- UCI online+retail (no token needed)")
            except Exception as exc:
                print(f"  FAIL retail        {type(exc).__name__}: {exc}")
                problems.append(("uci/online-retail", str(exc)))

    missing = [rel for rel in EXPECTED if not (SOURCES / rel).exists()]
    if problems or missing:
        print()
        for rel in missing:
            print(f"  MISSING {rel}")
        print(f"\n  {len(problems)} source problem(s); {len(missing)} of "
              f"{len(EXPECTED)} expected files absent.")
        print("  The benchmark cannot be reproduced without all five sources.")
        print("  This is dataset access, not a code defect -- see REPRODUCIBILITY.md.")
        return 2

    print(f"\n  all {len(EXPECTED)} expected files present. Next:")
    print("    python3 framework/load_all_domains.py    # source -> both databases")
    print("    python3 framework/load_federated_tables.py  # raw tables -> both databases")
    print("    python3 tools/verify_gold_queries.py     # execute the 50 gold queries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
