#!/usr/bin/env python3
"""
Verify every gold query in the benchmark actually executes through the
federation engine, and that its own validator accepts the result.

This is the data half of the reproducibility claim: it needs the federated
stack (PostgreSQL + MariaDB + PrestoDB) from docker-compose.yml, but it does NOT
need a language model. The result is deterministic, which is why it is the
strongest check that can run in CI.

It imports the framework's own BENCHMARK list and its own run_presto() and
validators, so it verifies the shipped code rather than a reimplementation.

Usage:
    python3 tools/verify_gold_queries.py
    FEDERATION_URL=http://host:8080 python3 tools/verify_gold_queries.py
"""
import importlib.util
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE = ROOT / "framework" / "benchmark_50q_realinfra.py"


def load_framework():
    spec = importlib.util.spec_from_file_location("sarai_benchmark", MODULE)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod


def main():
    mod = load_framework()
    bench = getattr(mod, "BENCHMARK", None)
    if not bench:
        sys.exit(f"no BENCHMARK list in {MODULE}")

    engine = os.environ.get("FEDERATION_URL", "http://127.0.0.1:8080")

    # Fail early and legibly if the engine is not answering JSON. Otherwise the
    # raw decoder error ("Expecting value: line 1 column 1") appears once per
    # question and says nothing about the actual problem, which is almost always
    # that the engine is still starting up.
    try:
        with urllib.request.urlopen(f"{engine}/v1/info", timeout=10) as r:
            info = json.loads(r.read().decode())
    except Exception as exc:
        sys.exit(f"the engine at {engine} is not answering /v1/info as JSON: "
                 f"{type(exc).__name__}: {exc}\n"
                 "  wait for it with:  python3 tools/wait_for_engine.py\n"
                 "  or start the stack: docker compose up -d")
    if info.get("starting", True):
        sys.exit(f"the engine at {engine} is up but still starting "
                 f"(uptime {info.get('uptime', '?')}); queries cannot run yet.\n"
                 "  wait for it with:  python3 tools/wait_for_engine.py")

    print(f"verifying {len(bench)} gold queries against {engine}"
          f" (engine {info.get('nodeVersion', {}).get('version', '?')})\n")

    passed, failures = 0, []
    t0 = time.time()
    for q in bench:
        qid = q["id"]
        cols, rows, _elapsed, err = mod.run_presto(q["gold_sql"], timeout=60)
        if err:
            failures.append((qid, f"execution error: {str(err)[:100]}"))
            continue
        try:
            ok = bool(q["validator"](rows))
        except Exception as exc:                       # validator raised
            failures.append((qid, f"validator raised {type(exc).__name__}: {exc}"))
            continue
        if ok:
            passed += 1
        else:
            failures.append((qid, f"validator rejected result ({len(rows or [])} rows)"))

    elapsed = time.time() - t0
    total = len(bench)
    federated = sum(1 for q in bench
                    if "mysql." in q["gold_sql"] and "postgresql." in q["gold_sql"])

    by_tier = {}
    for q in bench:
        tier = q["tier"]
        cross = "mysql." in q["gold_sql"] and "postgresql." in q["gold_sql"]
        t, f = by_tier.get(tier, (0, 0))
        by_tier[tier] = (t + 1, f + (1 if cross else 0))

    print(f"  gold queries passed : {passed}/{total}   in {elapsed:.1f}s")
    print(f"  cross-engine joins  : {federated}/{total}")
    for tier in sorted(by_tier):
        t, f = by_tier[tier]
        print(f"    tier {tier}: {t} queries, {f} federated")

    if failures:
        print(f"\n  {len(failures)} FAILURE(S):")
        for qid, why in failures[:20]:
            print(f"    {qid}: {why}")
        sys.exit(1)

    print("\n  every gold query executed and satisfied its own validator.")
    print(json.dumps({"gold_queries": total, "passed": passed,
                      "federated": federated, "seconds": round(elapsed, 1)}))


if __name__ == "__main__":
    main()
