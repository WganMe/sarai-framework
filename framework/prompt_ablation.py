#!/usr/bin/env python3
"""
Prompt ablation experiment addressing reviewer request: "compare zero-shot
prompting, schema-only prompting, ... prompts containing different numbers of
examples." Reuses the real benchmark harness (question list, gold validators,
SQL executor) from benchmark_50q_realinfra.py; only the prompt construction
differs across conditions. Run against Llama 3.1 8B (the flagship local model)
on the real infrastructure already validated in this session.
"""
import json, time, os
from datetime import datetime

import benchmark_50q_realinfra as base

MODEL = "llama3.1:8b"

# ---- Condition 1: Zero-shot (no schema, no examples) ----
ZERO_SHOT_PROMPT = """You are a SQL expert for federated SQL. Output ONLY a single SQL query, no explanation.
Fact tables (PostgreSQL) use prefix postgresql.public.<table>; dimension tables (MariaDB) use prefix mysql.<schema>.<table>.
"""

# ---- Condition 2: Schema-only (full DDL + rules, no worked examples) ----
_examples_marker = "=== EXAMPLES ==="
_idx = base.SYSTEM_PROMPT.index(_examples_marker)
SCHEMA_ONLY_PROMPT = base.SYSTEM_PROMPT[:_idx].rstrip() + "\n"

# ---- Condition 3: Few-shot (the real baseline already tested: 74% accuracy) ----
FEW_SHOT_PROMPT = base.SYSTEM_PROMPT

CONDITIONS = {
    "zero_shot": ZERO_SHOT_PROMPT,
    "schema_only": SCHEMA_ONLY_PROMPT,
}


def run_condition(name, system_prompt):
    print(f"\n{'='*80}\nCONDITION: {name}  (prompt length ~{len(system_prompt)} chars)\n{'='*80}")
    result = {
        "condition": name, "model": MODEL,
        "tier_scores": {"1": [], "2": [], "3": [], "4": [], "5": []},
        "total_correct": 0, "total_questions": len(base.BENCHMARK),
        "timings": [], "details": []
    }
    for q in base.BENCHMARK:
        qid, nl, tier = q["id"], q["nl"], str(q["tier"])
        prompt = f"{system_prompt}\n\nQ: {nl}\nA:"
        gen_sql, gen_time, raw = base.call_local_llm_prompt(MODEL, prompt)
        valid, msg, exec_time, used_sql = base.validate_generated_sql(gen_sql, q["validator"], qid)
        result["tier_scores"][tier].append(1 if valid else 0)
        if valid:
            result["total_correct"] += 1
        result["timings"].append(gen_time)
        result["details"].append({
            "id": qid, "tier": tier, "domain": q["domain"], "question": nl,
            "generated_sql": gen_sql, "valid": valid, "message": msg,
            "gen_time": gen_time, "exec_time": exec_time
        })
        status = "OK" if valid else "FAIL"
        print(f"  {qid:8s} {status:5s} [{gen_time:5.1f}s] {msg}")
    pct = 100 * result["total_correct"] / result["total_questions"]
    print(f"\n  SUMMARY [{name}]: {result['total_correct']}/{result['total_questions']} ({pct:.1f}%)")
    return result


if __name__ == "__main__":
    all_results = {}
    for name, prompt in CONDITIONS.items():
        all_results[name] = run_condition(name, prompt)

    print(f"\n{'='*80}\nABLATION SUMMARY (Llama 3.1 8B, real infrastructure)\n{'='*80}")
    print(f"{'Condition':<15s} {'Accuracy':<12s}")
    print("-" * 30)
    for name, r in all_results.items():
        pct = 100 * r["total_correct"] / r["total_questions"]
        print(f"{name:<15s} {r['total_correct']}/{r['total_questions']} ({pct:.1f}%)")
    print(f"{'few_shot (baseline, already measured)':<15s} 37/50 (74.0%)")

    outdir = os.environ.get(
        "RUNS_DIR",
        os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "..", "datasets", "real_infra_runs")))
    os.makedirs(outdir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(outdir, f"ablation_results_{ts}.json")
    with open(outfile, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nSaved to {outfile}")
