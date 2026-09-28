#!/usr/bin/env python3
"""
Independent validation of the SQL Anomaly Scorer against REAL model-generated
errors from the benchmark run (not the author-designed adversarial test set
used to build/tune the detection rules). Addresses the reviewer's concern that
the anomaly rules and test samples may have been developed from the same
underlying categories, potentially inflating the reported F1 score.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sarai_risk_mechanisms import SQLAnomalyScorer

# Resolve the run data relative to this file so the script works from any checkout.
RESULTS_FILE = os.path.normpath(
    os.path.join(HERE, "..", "datasets", "benchmark_results_20260219_054729.json"))


def main():
    data = json.load(open(RESULTS_FILE))
    total_real_errors = 0
    flagged = 0
    per_model_rows = []
    examples = []

    for m in data:
        name = m["model"]
        real_errors = [d for d in m["details"] if not d["valid"] and d.get("generated_sql")]
        n = len(real_errors)
        if n == 0:
            per_model_rows.append((name, 0, 0))
            continue
        model_flagged = 0
        for d in real_errors:
            sql = d["generated_sql"]
            score, findings, is_blocked = SQLAnomalyScorer.score(sql)
            total_real_errors += 1
            if is_blocked:
                flagged += 1
                model_flagged += 1
            if len(examples) < 8:
                examples.append({
                    "model": name, "id": d["id"], "sql": sql[:120],
                    "score": score, "blocked": is_blocked,
                    "findings": [f["msg"] for f in findings][:2],
                    "exec_message": d.get("message"),
                })
        per_model_rows.append((name, n, model_flagged))

    print("=== Per-model real (non-adversarial) model errors tested ===")
    for name, n, fl in per_model_rows:
        print(f"{name}: {n} real wrong-but-generated queries, {fl} flagged by anomaly scorer")

    print(f"\n=== Overall ===")
    print(f"Total real model errors tested: {total_real_errors}")
    print(f"Flagged (blocked) by anomaly scorer: {flagged} ({100*flagged/total_real_errors:.1f}%)")
    print(f"NOT flagged (scorer sees them as structurally normal SQL): {total_real_errors - flagged} "
          f"({100*(total_real_errors-flagged)/total_real_errors:.1f}%)")

    print("\n=== Example cases ===")
    for e in examples:
        print(f"- [{e['model']} / {e['id']}] blocked={e['blocked']} score={e['score']:.2f} "
              f"exec_msg={e['exec_message']!r}")
        print(f"  SQL: {e['sql']}")
        if e["findings"]:
            print(f"  findings: {e['findings']}")


if __name__ == "__main__":
    main()
