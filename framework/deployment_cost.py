#!/usr/bin/env python3
"""
SARAI Paper -- parametric deployment-cost model (self-host vs. cloud API).

Backs the "Deployment Cost" subsection of the manuscript. The model is
deliberately parametric: the three quantities it cannot know for a given
organization (hardware life, electricity price, operator effort, cloud token
price) are named inputs, so a reader can substitute their own. Only the query
rate and the measured generation time are taken from this study's run.

Prints:
  * annual cost at a spread of daily query volumes, split into hardware,
    electricity, and operations;
  * the break-even query volume above which the flat-cost self-hosted
    deployment is cheaper than per-query cloud pricing;
  * how the break-even moves when the operator-effort assumption is halved or
    doubled.

Usage:  python3 deployment_cost.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BENCH = os.path.normpath(os.path.join(HERE, "..", "datasets",
                                      "benchmark_results_20260219_054729.json"))

# --- MEASURED inputs (from this study's benchmark run) ----------------------
def measured_inputs():
    data = json.load(open(BENCH))
    by = {m["model"]: m for m in data}
    m = by["Llama 3.1 8B"]                       # the sovereign deployment of record
    gen = [d["gen_time"] for d in m["details"] if d.get("gen_time")]
    t_gen = sum(gen) / len(gen)                  # s/query
    out_chars = [len(d.get("generated_sql") or "") for d in m["details"]]
    n_out = sum(out_chars) / len(out_chars) / 4  # ~tokens
    return t_gen, n_out


# --- ASSUMED inputs (organization-specific; substitute your own) ------------
N_PROMPT = 3900      # tokens: full schema + four few-shot examples (fixed prompt)
C_HW = 6000.0        # USD commodity server, 3-year life
P_KW = 0.12          # kW average while serving
P_KWH = 0.12         # USD/kWh
C_OPS = 9600.0       # USD/yr operations (0.16 FTE)
P_TOKEN = 0.30       # USD per 1M tokens, blended cloud price


def self_host(W, t_gen):
    hw = C_HW / 3
    elec = W * 365 * (t_gen / 3600) * P_KW * P_KWH
    return hw + elec + C_OPS, hw, elec


def cloud(W, n_out):
    return W * 365 * (N_PROMPT + n_out) / 1e6 * P_TOKEN


def crossover(t_gen, n_out, ops=C_OPS):
    hw = C_HW / 3
    a = 365 * (t_gen / 3600) * P_KW * P_KWH       # USD/query self-host
    b = 365 * (N_PROMPT + n_out) / 1e6 * P_TOKEN  # USD/query cloud
    return (hw + ops) / (b - a), a, b


if __name__ == "__main__":
    t_gen, n_out = measured_inputs()
    print(f"measured: gen_time={t_gen:.2f} s/query, output~{n_out:.0f} tokens\n")
    print(f"{'W/day':>8} {'self-host':>11} {'hw':>7} {'elec':>7} {'ops':>7} {'cloud':>10}")
    for W in (100, 500, 1000, 5000, 10000):
        s, hw, el = self_host(W, t_gen)
        print(f"{W:8d} {s:11.0f} {hw:7.0f} {el:7.0f} {C_OPS:7.0f} {cloud(W, n_out):10.0f}")
    Wc, a, b = crossover(t_gen, n_out)
    print(f"\nper-query: self-host elec=USD{a:.6f}  cloud=USD{b:.6f}")
    print(f"break-even W* = {Wc:.0f} queries/day")
    print(f"electricity share of self-host at 10k/day: "
          f"{self_host(10000, t_gen)[2] / self_host(10000, t_gen)[0] * 100:.1f}%")
    print(f"break-even if ops doubled: {crossover(t_gen, n_out, 2 * C_OPS)[0]:.0f}/day; "
          f"if ops halved: {crossover(t_gen, n_out, 0.5 * C_OPS)[0]:.0f}/day")
