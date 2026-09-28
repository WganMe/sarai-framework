#!/usr/bin/env python3
"""
assert_published_values.py -- fail if the reproduction scripts stop agreeing
with the numbers printed in the manuscript.

WHY THIS EXISTS
---------------
The manuscript states that "the statistics, sensitivity, and cost analyses are
computed by tracked scripts ... that read the raw per-question run data
directly, so every reported number is regenerated rather than transcribed."
That claim is only meaningful if something CHECKS it. Running the scripts and
eyeballing the output proves nothing to a reader and nothing to a referee; it
also silently stops being true the first time a script is edited.

So this script runs the three analysis scripts, captures what they print, and
asserts the published figures are present. It is the CI step that turns the
sentence above from an assertion into a machine-checked fact.

WHAT IT ASSERTS (each value quoted from the manuscript, with its location)
  deployment_cost.py
    23.71 s/query      "the measured 23.71 s/query generation time"      (Sec. 7.3)
    USD 11,635/yr      "at 1,000 queries/day it costs USD 11,635/yr"     (Sec. 7.3)
    USD 436/yr         "Cloud pricing at the same volumes is USD 436/yr" (Sec. 7.3)
    USD 9,600 ops      "operations are USD 9,600"                        (Sec. 7.3)
    USD 35 elec        "electricity is only USD 35"                      (Sec. 7.3)
    2.9%               "even at 10,000 queries/day electricity is 2.9%"  (Sec. 7.3)
    28,907 -> 2.9e4    "the break-even at roughly 2.9x10^4 queries/day"  (Sec. 7.3)
    16,946 / 52,831    "halving it lowers ... to 1.7e4 / doubling ... 5.3e4"
  sovereignty_sensitivity.py
    the graded ladder endpoints (on-premise 1.00, public API 0.00) and the
    auditable-API range 0.75, which are the Section 3.3 / Table 4 claims.
  revision_stats.py
    the four model latencies (14.10 / 23.71 / 3.66 / 149.91 s generation).

WHAT IT DELIBERATELY DOES NOT DO
  It does not re-run the benchmark. Those numbers need the federated
  deployment (PostgreSQL + MariaDB + Trino + Ollama/Superset), which is not
  part of this repository. This checks the ANALYSIS, not the RUN -- the same
  boundary the manuscript draws.

Exit code 0 if every assertion holds, 1 otherwise, with each failure named.
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))


def run(script):
    """Run a framework/ script and return its stdout+stderr as text."""
    path = os.path.join(ROOT, "framework", script)
    if not os.path.exists(path):
        print(f"  MISSING SCRIPT: framework/{script}")
        return None
    r = subprocess.run([sys.executable, path], capture_output=True, text=True,
                       cwd=ROOT)
    if r.returncode != 0:
        print(f"  SCRIPT FAILED ({r.returncode}): framework/{script}")
        print((r.stderr or "")[-600:])
        return None
    return (r.stdout or "") + (r.stderr or "")


# Each entry: (label, substring that must appear, source location in the paper)
#
# Substrings are matched against the scripts' own printed output. Keep them
# specific enough to be meaningful and loose enough not to break on formatting:
# no thousands separators, since the scripts print "11635" and the manuscript
# writes "11{,}635".
CHECKS = {
    "deployment_cost.py": [
        ("measured generation time", "gen_time=23.71", "Sec 7.3, 23.71 s/query"),
        ("self-host at 1k/day", "11635", "Sec 7.3, USD 11,635/yr"),
        ("cloud at 1k/day", "436", "Sec 7.3, USD 436/yr"),
        ("operations cost", "9600", "Sec 7.3, USD 9,600 ops"),
        ("electricity at 1k/day", "35", "Sec 7.3, USD 35 electricity"),
        ("electricity share at 10k", "2.9%", "Sec 7.3, electricity 2.9%"),
        ("break-even", "28907", "Sec 7.3, ~2.9e4 queries/day"),
        ("break-even, ops halved", "16946", "Sec 7.3, ~1.7e4/day"),
        ("break-even, ops doubled", "52831", "Sec 7.3, ~5.3e4/day"),
    ],
    "sovereignty_sensitivity.py": [
        ("on-premise reaches full capability", "On-premise:[1.00,1.00]",
         "Sec 3.3 / Table 4, rho_max = 1.00"),
        ("public API reaches none", "Public API:[0.00,0.00]",
         "Sec 3.3 / Table 4, rho_max = 0.00"),
        ("auditable API retains 0.75", "Auditable API:[0.75,1.00]",
         "Sec 3.3, auditable API rho_max = 0.75"),
    ],
    "revision_stats.py": [
        ("Llama 3.1 8B generation latency", "gen=23.71", "Table 10, 23.71 s"),
        ("Llama 3.2 3B generation latency", "gen=14.10", "Table 10, 14.10 s"),
        ("Gemma-3 27B generation latency", "gen=3.66", "Table 10, 3.66 s"),
        ("DeepSeek R1 generation latency", "gen=149.91", "Table 10, 149.91 s"),
    ],
}


def main():
    print("Asserting the scripts still print the manuscript's published values.")
    print("(These are the ANALYSIS numbers; the benchmark RUN is out of scope.)\n")

    failures = []
    for script, checks in CHECKS.items():
        print(f"=== framework/{script} ===")
        out = run(script)
        if out is None:
            failures.append(f"{script} did not run")
            print()
            continue
        # normalise whitespace so a line-wrap cannot break a match
        flat = re.sub(r"\s+", " ", out)
        for label, needle, where in checks:
            ok = needle in flat
            print(f"  [{'OK ' if ok else 'FAIL'}] {label:34} {needle!r:22} <- {where}")
            if not ok:
                failures.append(f"{script}: {label} ({needle!r}) not found")
        print()

    print("=" * 66)
    if failures:
        print(f"  {len(failures)} ASSERTION(S) FAILED")
        for f in failures:
            print(f"    - {f}")
        print()
        print("  A published number no longer reproduces. Either the script or the")
        print("  manuscript changed and they have drifted apart.")
        return 1
    n = sum(len(v) for v in CHECKS.values())
    print(f"  {n} published values reproduce from the committed run data.")
    print("  The manuscript's reproducibility claim holds for the analysis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
