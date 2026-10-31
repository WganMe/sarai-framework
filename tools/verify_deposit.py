#!/usr/bin/env python3
"""
Check that a published Zenodo snapshot still matches the tag it claims to name.

    python3 tools/verify_deposit.py 10.5281/zenodo.23839523 v1.2.0

Why this exists
---------------
The v1.1.0 and v1.2.0 tags were both moved *after* their payload had been
archived, to write the version DOI into ZENODO_DEPOSIT.md. Each move was
reasonable in isolation and each made the sentence "tag vX matches the archived
tree" false, in a file that was by then immutable.

The loop is structural: the archive contains the notes that record the DOI, and
the DOI is only known after the archive exists. Two properties break it, and
this script enforces both.

1. **Cite the concept DOI, never a version DOI, in the tree.** The concept DOI
   is stable across versions, so it can be written before the version exists.
2. **Never move a tag after its archive is published.** If the notes need the
   version DOI, that is a new version, not an amendment.

Exit codes: 0 consistent, 1 inconsistent, 2 could not check.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as fh:
        return json.load(fh)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    doi, tag = sys.argv[1], sys.argv[2]

    rec_id = doi.rsplit(".", 1)[-1]
    try:
        rec = get(f"https://zenodo.org/api/records/{rec_id}")
    except urllib.error.HTTPError as exc:
        print(f"FAIL  cannot read Zenodo record {rec_id}: HTTP {exc.code}", file=sys.stderr)
        return 2
    except urllib.error.URLError as exc:
        print(f"SKIP  Zenodo unreachable ({exc.reason}); nothing verified", file=sys.stderr)
        return 2

    fails: list[str] = []
    checks = 0

    def ok(msg: str) -> None:
        nonlocal checks
        checks += 1
        print(f"  ok  {msg}")

    def bad(msg: str) -> None:
        nonlocal checks
        checks += 1
        fails.append(msg)
        print(f"  FAIL  {msg}")

    # ---------------------------------------------------------------- identity
    if rec.get("status") == "published":
        ok("record is published")
    else:
        bad(f"record status is {rec.get('status')!r}, not 'published'")

    files = rec.get("files", [])
    if len(files) == 1:
        ok(f"exactly one file: {files[0]['key']} ({files[0]['size']} bytes)")
    else:
        bad(f"expected exactly one file, found {len(files)}")

    if not files:
        return 1

    f0 = files[0]
    name = f0["key"]
    if name.startswith(f"sarai-framework-{tag.lstrip('v')}"):
        ok(f"filename {name} names tag {tag}")
    else:
        bad(f"filename {name} does not name tag {tag}")

    # ---------------------------------------------------------------- download
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / name
        url = f"https://zenodo.org/records/{rec_id}/files/{name}?download=1"
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as exc:                      # noqa: BLE001
            print(f"SKIP  download failed ({exc}); upload not verified", file=sys.stderr)
            return 2

        md5 = hashlib.md5(dest.read_bytes()).hexdigest()
        declared = (f0.get("checksum") or "").replace("md5:", "")
        if md5 == declared:
            ok(f"md5 matches Zenodo's copy: {md5}")
        else:
            bad(f"md5 {md5} != Zenodo's declared {declared}")

        # ------------------------------------------------------------ tree
        # Compare the archived file set against what `git archive` produces for
        # the tag *now*. Ask git rather than listing `ls-tree`, because the
        # dataset paths carry `export-ignore` in .gitattributes and a plain
        # ls-tree comparison reports every intentionally excluded file as a
        # failure. git is the authority on what an archive of this tag contains.
        #
        # Compare CONTENT as well as names. Comparing names alone passed a tag
        # that had been moved to change one line of ZENODO_DEPOSIT.md: every file
        # was present and one of them said something different from the archive,
        # which is exactly the drift this script exists to catch.
        prefix = name[: -len(".tar.gz")] + "/"
        archived: dict[str, str] = {}
        with tarfile.open(dest) as tf:
            for m in tf.getmembers():
                if m.isfile() and m.name.startswith(prefix):
                    blob = tf.extractfile(m)
                    archived[m.name[len(prefix):]] = hashlib.sha256(
                        blob.read() if blob else b"").hexdigest()

        out = subprocess.run(
            ["git", "archive", "--format=tar", tag],
            cwd=ROOT, capture_output=True, check=False)
        if out.returncode != 0:
            print(f"SKIP  tag {tag} not present locally; tree not compared", file=sys.stderr)
            return 2

        import io
        expected: dict[str, str] = {}
        with tarfile.open(fileobj=io.BytesIO(out.stdout)) as tf:
            for m in tf.getmembers():
                if m.isfile():
                    blob = tf.extractfile(m)
                    expected[m.name] = hashlib.sha256(
                        blob.read() if blob else b"").hexdigest()

        missing = sorted(set(expected) - set(archived))
        extra = sorted(set(archived) - set(expected))
        changed = sorted(
            p for p in set(expected) & set(archived | expected)
            if p in archived and expected[p] != archived[p])

        if not missing and not extra and not changed:
            ok(f"archive tree matches tag {tag} exactly ({len(expected)} files, content included)")
        else:
            for m in missing[:5]:
                bad(f"tracked at {tag} but absent from the archive: {m}")
            for e in extra[:5]:
                bad(f"in the archive but not tracked at {tag}: {e}")
            for c in changed[:5]:
                bad(f"content differs between the archive and tag {tag}: {c}")

    print()
    if fails:
        print(f"verify_deposit: {len(fails)} failure(s) of {checks}")
        print("A moved tag is the usual cause. Publish a new version rather than "
              "editing the notes that a published archive already froze.")
        return 1
    print(f"verify_deposit: {checks} checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
