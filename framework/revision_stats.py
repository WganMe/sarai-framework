#!/usr/bin/env python3
"""
SARAI Paper — Revision statistics for reviewer request:
McNemar's test (paired binary) + Holm correction, Cochran's Q, paired-difference
CIs, and real end-to-end latency, computed from the actual per-question raw data
in benchmark_results_20260219_054729.json (the run cited in the manuscript).
No scipy/statsmodels dependency, consistent with the project's existing
from-scratch statistics style in process_results.py.
"""
import json, math
import os
from itertools import combinations

# Resolve the run data RELATIVE TO THIS FILE rather than by absolute path. The
# absolute form ("/home/bcdr/...") only worked on the machine that wrote it, so
# neither a co-author nor CI could run this script at all.
HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_FILE = os.path.normpath(
    os.path.join(HERE, "..", "datasets",
                 "benchmark_results_20260219_054729.json"))

EVALUATED_MODELS = ["Llama 3.2 3B", "Llama 3.1 8B", "Gemma-3 27B", "DeepSeek R1"]  # Llama 3.3 70B excluded: API failure


def load_paired_binary():
    data = json.load(open(RESULTS_FILE))
    by_model = {m["model"]: m for m in data}
    per_model_by_id = {}
    for name in EVALUATED_MODELS:
        m = by_model[name]
        per_model_by_id[name] = {d["id"]: bool(d["valid"]) for d in m["details"]}
    ids = sorted(per_model_by_id[EVALUATED_MODELS[0]].keys())
    # sanity: all models must share the same 50 question ids
    for name in EVALUATED_MODELS:
        assert set(per_model_by_id[name].keys()) == set(ids), f"ID mismatch for {name}"
    return ids, per_model_by_id


def mcnemar_exact(b, c):
    """Exact two-sided McNemar test via binomial distribution on discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)

    def binom_pmf(x, n, p=0.5):
        return math.comb(n, x) * (p ** x) * ((1 - p) ** (n - x))

    p = sum(binom_pmf(x, n) for x in range(0, k + 1))
    p = min(1.0, 2 * p)
    return p


def holm_correction(pvals):
    """Holm-Bonferroni step-down correction. Returns adjusted p-values in original order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    adjusted = [0.0] * m
    running_max = 0.0
    for rank, idx in enumerate(order):
        adj = (m - rank) * pvals[idx]
        running_max = max(running_max, adj)
        adjusted[idx] = min(1.0, running_max)
    return adjusted


def cochrans_q(matrix):
    """
    Cochran's Q test for k paired binary outcomes across n subjects (questions).
    matrix: list of n rows, each a list of k binary values (0/1) in fixed model order.
    """
    n = len(matrix)
    k = len(matrix[0])
    col_sums = [sum(row[j] for row in matrix) for j in range(k)]
    row_sums = [sum(row) for row in matrix]
    T = sum(col_sums)
    numerator = (k - 1) * (k * sum(cs ** 2 for cs in col_sums) - T ** 2)
    denominator = k * T - sum(rs ** 2 for rs in row_sums)
    if denominator == 0:
        return 0.0, k - 1, 1.0
    Q = numerator / denominator
    df = k - 1
    p = chi2_sf(Q, df)
    return Q, df, p


def chi2_sf(x, df):
    """Survival function (1 - CDF) of chi-square via regularized upper incomplete gamma."""
    return upper_incomplete_gamma_reg(df / 2.0, x / 2.0)


def upper_incomplete_gamma_reg(a, x, iters=200):
    """Regularized upper incomplete gamma Q(a,x) via continued fraction (Numerical Recipes)."""
    if x < 0 or a <= 0:
        return 1.0
    if x == 0:
        return 1.0
    gln = math.lgamma(a)
    if x < a + 1.0:
        # series representation for P(a,x), then Q = 1 - P
        ap = a
        summ = 1.0 / a
        delta = summ
        for _ in range(iters):
            ap += 1
            delta *= x / ap
            summ += delta
            if abs(delta) < abs(summ) * 1e-12:
                break
        p = summ * math.exp(-x + a * math.log(x) - gln)
        return 1.0 - p
    else:
        # continued fraction for Q(a,x)
        b = x + 1.0 - a
        c = 1.0 / 1e-30
        d = 1.0 / b
        h = d
        for i in range(1, iters):
            an = -i * (i - a)
            b += 2.0
            d = an * d + b
            if abs(d) < 1e-30:
                d = 1e-30
            c = b + an / c
            if abs(c) < 1e-30:
                c = 1e-30
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < 1e-12:
                break
        q = math.exp(-x + a * math.log(x) - gln) * h
        return q


def paired_diff_ci(b, c, n, z=1.96):
    """
    Confidence interval for the paired difference in proportions (accuracy_A - accuracy_B)
    using the standard asymptotic SE for paired binary data based on discordant pairs.
    """
    diff = (b - c) / n
    se = math.sqrt((b + c) - (b - c) ** 2 / n) / n if n > 0 else 0.0
    return diff, diff - z * se, diff + z * se


def main():
    ids, per_model = load_paired_binary()
    n = len(ids)
    print(f"Loaded {n} matched questions across {len(EVALUATED_MODELS)} evaluated models.\n")

    # ---- Pairwise McNemar + Holm correction ----
    pairs = list(combinations(EVALUATED_MODELS, 2))
    raw_pvals = []
    pair_stats = []
    for a, b_ in pairs:
        va = per_model[a]
        vb = per_model[b_]
        b_disc = sum(1 for i in ids if va[i] and not vb[i])   # A correct, B wrong
        c_disc = sum(1 for i in ids if not va[i] and vb[i])   # A wrong, B correct
        p = mcnemar_exact(b_disc, c_disc)
        diff, lo, hi = paired_diff_ci(b_disc, c_disc, n)
        raw_pvals.append(p)
        pair_stats.append((a, b_, b_disc, c_disc, p, diff, lo, hi))

    adj_pvals = holm_correction(raw_pvals)

    print("=== Pairwise McNemar's exact test (Holm-corrected) ===")
    for (a, b_, b_disc, c_disc, p, diff, lo, hi), p_adj in zip(pair_stats, adj_pvals):
        acc_a = sum(per_model[a].values()) / n * 100
        acc_b = sum(per_model[b_].values()) / n * 100
        sig = "significant" if p_adj < 0.05 else "not significant"
        print(f"{a} ({acc_a:.0f}%) vs {b_} ({acc_b:.0f}%): "
              f"discordant b={b_disc}, c={c_disc}, p_raw={p:.4g}, p_holm={p_adj:.4g} [{sig}], "
              f"paired diff={diff*100:.1f} pp, 95% CI=[{lo*100:.1f}, {hi*100:.1f}] pp")

    # ---- Cochran's Q across all 4 models ----
    matrix = [[int(per_model[m][i]) for m in EVALUATED_MODELS] for i in ids]
    Q, df, p_q = cochrans_q(matrix)
    print(f"\n=== Cochran's Q test (omnibus, k={len(EVALUATED_MODELS)} models) ===")
    print(f"Q = {Q:.4f}, df = {df}, p = {p_q:.4g}")

    # ---- Real end-to-end latency ----
    print("\n=== Real end-to-end latency (gen_time + exec_time), seconds ===")
    data = json.load(open(RESULTS_FILE))
    by_model = {m["model"]: m for m in data}
    for name in EVALUATED_MODELS:
        details = by_model[name]["details"]
        totals = sorted((d["gen_time"] or 0.0) + (d["exec_time"] or 0.0) for d in details)
        n_d = len(totals)
        mean = sum(totals) / n_d
        median = totals[n_d // 2]
        p95 = totals[int(0.95 * (n_d - 1))]
        gen_only = sum(d["gen_time"] or 0.0 for d in details) / n_d
        exec_only = sum(d["exec_time"] or 0.0 for d in details) / n_d
        print(f"{name}: mean={mean:.2f}s, median={median:.2f}s, p95={p95:.2f}s "
              f"(gen={gen_only:.2f}s, exec={exec_only:.3f}s)")


if __name__ == "__main__":
    main()
