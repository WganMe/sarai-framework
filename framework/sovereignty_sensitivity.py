#!/usr/bin/env python3
"""
SARAI Paper -- sovereignty sensitivity analysis and graded-sovereignty ladder.

Generates the artefacts cited in Section "Sovereignty Sensitivity and the Graded
Model" of the manuscript:

  * fig_sensitivity.pdf -- a two-panel figure: (a) the graded sovereignty ladder
    with the capability step function rho_max(sigma_I), and (b) a threshold
    tornado showing how rho_max moves as each capability's inference-sovereignty
    threshold tau_i^I is perturbed by +/-0.25.
  * all numbers printed to stdout, so the prose can be checked against the code.

Everything is computed from the capability weights and thresholds declared in
Table `tab:risk_capabilities` of the manuscript. No number is typed by hand:
change the table and re-run, and the figure and the printed values move together.

Usage:
    python3 sovereignty_sensitivity.py            # writes ../Elsevier-IPM/fig_sensitivity.pdf
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Computer Modern Roman", "CMU Serif", "DejaVu Serif", "Times New Roman"],
    "mathtext.fontset": "cm",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
    "axes.linewidth": 0.6,
    "lines.linewidth": 1.0,
    "axes.grid": False,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "text.usetex": False,
})

# Capability weights (v_i) and inference-sovereignty thresholds (tau_i^I) from
# Table `tab:risk_capabilities`. tau_i^D values are all <= the graded ladder's
# data-sovereignty levels and are not varied here.
CAPS = {
    "anomaly":    {"v": 0.30, "tauI": 0.50},
    "drift":      {"v": 0.25, "tauI": 0.25},
    "confidence": {"v": 0.25, "tauI": 0.75},
    "feedback":   {"v": 0.20, "tauI": 0.50},
}

# Deployment archetypes on the graded scale (sigma_D fixed at 1.0 for the ladder).
ARCHETYPES = {
    "On-premise":   1.000,
    "Private VPC":  0.875,
    "Auditable API": 0.625,
    "Public API":   0.000,
}


def rho_max(sigma_i, weights=None, thresholds=None):
    """Risk Assessment Capability Index under the step-function bound."""
    weights = weights or {k: c["v"] for k, c in CAPS.items()}
    thresholds = thresholds or {k: c["tauI"] for k, c in CAPS.items()}
    return round(sum(weights[k] for k in CAPS if sigma_i >= thresholds[k] - 1e-12), 4)


def available(sigma_i, thresholds=None):
    thresholds = thresholds or {k: c["tauI"] for k, c in CAPS.items()}
    return [k for k in CAPS if sigma_i >= thresholds[k] - 1e-12]


def report():
    print("=== Graded sovereignty ladder (sigma_D = 1.0) ===")
    for name, si in ARCHETYPES.items():
        print(f"  {name:14s} sigma_I={si:.3f}  rho_max={rho_max(si):.2f}  "
              f"capabilities={available(si)}")

    print("\n=== Step-function breakpoints ===")
    prev = None
    for i in range(101):
        si = i / 100
        r = rho_max(si)
        if r != prev:
            print(f"  sigma_I >= {si:.2f} -> rho_max = {r:.2f}")
            prev = r

    print("\n=== Weight sensitivity (300k Dirichlet-style samples, v_i in [0.10,0.40]) ===")
    rng = np.random.default_rng(1)
    n = 0
    res = {a: [1.0, 0.0] for a in ARCHETYPES}
    while n < 300_000:
        w = rng.uniform(0.10, 0.40, size=4)
        s = w.sum()
        if not 0.9 <= s <= 1.1:
            continue
        w = w / s
        if not np.all((w >= 0.10 - 1e-9) & (w <= 0.40 + 1e-9)):
            continue
        n += 1
        wd = dict(zip(CAPS, w))
        for a, si in ARCHETYPES.items():
            r = rho_max(si, weights=wd)
            res[a][0] = min(res[a][0], r)
            res[a][1] = max(res[a][1], r)
    for a in ARCHETYPES:
        print(f"  {a:14s} rho_max in [{res[a][0]:.2f}, {res[a][1]:.2f}]")

    print("\n=== Threshold sensitivity (tau_i^I +/-0.25, range printed) ===")
    for k in CAPS:
        rng_lo, rng_hi = {a: [1.0, 0.0] for a in ARCHETYPES}, {a: [1.0, 0.0] for a in ARCHETYPES}
        for d in np.arange(-0.25, 0.2501, 0.01):
            thr = {kk: CAPS[kk]["tauI"] for kk in CAPS}
            thr[k] = min(1.0, max(0.0, CAPS[k]["tauI"] + d))
            for a, si in ARCHETYPES.items():
                r = rho_max(si, thresholds=thr)
                rng_lo[a][0] = min(rng_lo[a][0], r)
                rng_hi[a][1] = max(rng_hi[a][1], r)
        print(f"  tau_I[{k:10s}] -> " +
              "  ".join(f"{a}:[{rng_lo[a][0]:.2f},{rng_hi[a][1]:.2f}]" for a in ARCHETYPES))
    return res


def figure(out_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 2.9))

    # Panel (a): graded ladder + step function
    xs = np.linspace(0, 1, 501)
    ys = [rho_max(x) for x in xs]
    ax1.step(xs, ys, where="post", color="#1f3b73", linewidth=1.2, zorder=3)
    ax1.fill_between(xs, ys, step="post", color="#1f3b73", alpha=0.06, zorder=1)
    # Stagger labels vertically so the two full-capability archetypes do not collide.
    label_offsets = {"Private VPC": (6, -13), "On-premise": (-6, 6),
                     "Auditable API": (6, -11), "Public API": (6, 4)}
    for name, si in ARCHETYPES.items():
        ax1.plot([si], [rho_max(si)], marker="o", markersize=4.5,
                 color="#b3202a" if si < 0.75 else "#2e7d32", zorder=4)
        dx, dy = label_offsets[name]
        ax1.annotate(name, (si, rho_max(si)), textcoords="offset points",
                     xytext=(dx, dy), fontsize=7,
                     ha="right" if dx < 0 else "left")
    for t in (0.25, 0.50, 0.75):
        ax1.axvline(t, color="gray", linestyle="--", linewidth=0.5, alpha=0.6, zorder=0)
    ax1.set_xlabel(r"Inference sovereignty score $\sigma_I$")
    ax1.set_ylabel(r"Risk capability $\rho_{\max}$")
    ax1.set_xlim(0, 1.02)
    ax1.set_ylim(0, 1.08)
    ax1.set_xticks([0, 0.25, 0.5, 0.625, 0.75, 0.875, 1.0])
    ax1.set_yticks([0, 0.25, 0.75, 1.0])
    ax1.set_title("(a) Graded sovereignty ladder", fontsize=8.5)

    # Panel (b): threshold tornado as a horizontal grouped bar
    labels = list(CAPS)
    base = [rho_max(ARCHETYPES["Auditable API"])] * len(labels)
    lo, hi = [], []
    for k in labels:
        best, worst = 0.0, 1.0
        for d in np.arange(-0.25, 0.2501, 0.01):
            thr = {kk: CAPS[kk]["tauI"] for kk in CAPS}
            thr[k] = min(1.0, max(0.0, CAPS[k]["tauI"] + d))
            r = rho_max(ARCHETYPES["Auditable API"], thresholds=thr)
            worst = min(worst, r)
            best = max(best, r)
        lo.append(worst)
        hi.append(best)
    ypos = np.arange(len(labels))
    base_v = base[0]
    ax2.barh(ypos, [h - base_v for h in hi], left=base_v, color="#2e7d32",
             alpha=0.75, height=0.55, label=r"$\tau_i^I$ lowered")
    ax2.barh(ypos, [base_v - l for l in lo], left=lo, color="#b3202a",
             alpha=0.75, height=0.55, label=r"$\tau_i^I$ raised")
    ax2.axvline(base_v, color="black", linewidth=0.8, zorder=3)
    ax2.set_yticks(ypos)
    ax2.set_yticklabels([r"$\tau$ " + k for k in labels])
    ax2.set_xlabel(r"$\rho_{\max}$ (Auditable API, $\sigma_I{=}0.625$)")
    ax2.set_xlim(0.35, 1.02)
    ax2.set_title(r"(b) Threshold tornado ($\tau_i^I\pm0.25$)", fontsize=8.5)
    ax2.legend(frameon=False, loc="lower right")

    fig.tight_layout()
    fig.savefig(out_path)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    report()
    # Write BESIDE THIS SCRIPT, or wherever --out says. The previous version
    # aimed at a path THREE LEVELS UP through a nested checkout
    # ("../../../../papers/Paper1/Elsevier-IPM/fig_sensitivity.pdf") and fell
    # back to the current directory when that layout was absent. So the same
    # command produced the figure in different places on different machines:
    # here it landed in the manuscript directory, on a clean clone in cwd. A
    # reproducibility script must not do that -- its output location has to be
    # a property of the script, not of the surrounding directory tree.
    #
    # Usage:
    #   python3 sovereignty_sensitivity.py            # writes ./fig_sensitivity.pdf
    #   python3 sovereignty_sensitivity.py --out DIR  # writes DIR/fig_sensitivity.pdf
    out_dir = os.path.dirname(os.path.abspath(__file__))
    argv = sys.argv[1:]
    if "--out" in argv:
        i = argv.index("--out")
        if i + 1 >= len(argv):
            sys.exit("--out needs a directory argument")
        out_dir = argv[i + 1]
        os.makedirs(out_dir, exist_ok=True)
    figure(os.path.join(out_dir, "fig_sensitivity.pdf"))
