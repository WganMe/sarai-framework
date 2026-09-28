#!/usr/bin/env python3
"""
SARAI Paper — Publication-Quality Figures (v3 — 3 models only)
Llama 3.3 70B and DeepSeek R1 removed. TCO figure removed.
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os

plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Computer Modern Roman', 'CMU Serif', 'DejaVu Serif', 'Times New Roman'],
    'mathtext.fontset': 'cm',
    'font.size': 9,
    'axes.titlesize': 10,
    'axes.labelsize': 9,
    'xtick.labelsize': 8,
    'ytick.labelsize': 8,
    'legend.fontsize': 8,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.05,
    'axes.linewidth': 0.6,
    'xtick.major.width': 0.5,
    'ytick.major.width': 0.5,
    'xtick.minor.width': 0.3,
    'ytick.minor.width': 0.3,
    'lines.linewidth': 1.0,
    'axes.grid': False,
    'axes.spines.top': False,
    'axes.spines.right': False,
    'figure.figsize': (5.5, 3.8),
    'text.usetex': False,
})

OUTDIR = os.environ.get('FIG_OUTDIR', os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'figures')))
os.makedirs(OUTDIR, exist_ok=True)

# ── Color palette ───────────────────────────────────────────────────────
C_LOCAL  = '#2c2c2c'
C_CLOUD  = '#888888'
C_ACCENT = '#4472C4'
C_LIGHT  = '#B4C7E7'
C_GRID   = '#DDDDDD'

H_LOCAL = '//'
H_CLOUD = '..'

# ═════════════════════════════════════════════════════════════════════════
# DATA — 4 models (matching ipm-manuscript.tex bench macros, Table tab:accuracy)
# ═════════════════════════════════════════════════════════════════════════
MODELS = ['Llama 3.2\n3B', 'Llama 3.1\n8B', 'Gemma-3\n27B', 'DeepSeek\nR1']
MODELS_SHORT = ['3B', '8B', '27B', 'DeepSeek']
SOURCE = ['Local', 'Local', 'Cloud', 'Cloud']
TIERS = ['T1', 'T2', 'T3', 'T4', 'T5']

# Per-model, per-tier accuracy (%) from actual paper macros
ACC = np.array([
    [90, 20, 50, 40, 30],  # Llama 3.2 3B  → overall 46%
    [80, 50, 80, 50, 40],  # Llama 3.1 8B  → overall 60%
    [100, 80, 90, 90, 90], # Gemma-3 27B   → overall 90%
    [80, 100, 90, 70, 50], # DeepSeek R1   → overall 78%
], dtype=float)

OVERALL = np.array([46.0, 60.0, 90.0, 78.0])
SIGMA_I = [1.0, 1.0, 0.0, 0.0]
RHO_MAX = [1.0, 1.0, 0.0, 0.0]

# 95% CI half-widths (Wald normal approximation, matching the paper's values)
CI_HALF = np.array([
    (59.8 - 32.2) / 2,   # 3B: ±13.8
    (73.6 - 46.4) / 2,   # 8B: ±13.6
    (98.3 - 81.7) / 2,   # 27B: ±8.3
    (89.5 - 66.5) / 2,   # DeepSeek R1: ±11.5
])


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Accuracy heatmap (3 models × 5 tiers + overall column)
# ═══════════════════════════════════════════════════════════════════════════
def fig_heatmap():
    # Build extended data matrix: 5 tiers + 1 overall column
    ext = np.column_stack([ACC, OVERALL])           # shape (3, 6)
    n_rows, n_cols = ext.shape

    fig, ax = plt.subplots(figsize=(5.8, 2.6))

    # ── Main heatmap (sequential blue-grey) ──────────────────────────────
    from matplotlib.colors import LinearSegmentedColormap
    cmap_custom = LinearSegmentedColormap.from_list(
        'sarai', ['#F2F2F2', '#B4C7E7', '#4472C4', '#1F3864'], N=256)
    im = ax.imshow(ext, cmap=cmap_custom, vmin=0, vmax=100, aspect='auto')

    # ── Cell annotations ─────────────────────────────────────────────────
    for i in range(n_rows):
        for j in range(n_cols):
            val = ext[i, j]
            color = 'white' if val > 60 else '#1a1a1a'
            weight = 'bold'
            fs = 10 if j < 5 else 11          # overall col slightly larger
            ax.text(j, i, f'{val:.0f}%', ha='center', va='center',
                    fontsize=fs, color=color, fontweight=weight)

    # ── Vertical separator before "Overall" column ───────────────────────
    ax.axvline(x=4.5, color='white', linewidth=2.5)
    ax.axvline(x=4.5, color='black', linewidth=0.8)

    # ── Horizontal separator: local vs cloud ─────────────────────────────
    ax.axhline(y=1.5, color='white', linewidth=2.5)
    ax.axhline(y=1.5, color='black', linewidth=1.0)

    # ── Deployment-source brackets (left side) ───────────────────────────
    ax.annotate('', xy=(-0.9, -0.40), xytext=(-0.9, 1.40),
                arrowprops=dict(arrowstyle='-[, widthB=3.0, lengthB=0.3',
                                lw=0.8, color='#333'),
                annotation_clip=False)
    ax.text(-1.35, 0.5, 'Local', ha='center', va='center', fontsize=8,
            fontweight='bold', rotation=90, style='italic',
            transform=ax.get_yaxis_transform(), clip_on=False)

    ax.annotate('', xy=(-0.9, 1.60), xytext=(-0.9, 3.40),
                arrowprops=dict(arrowstyle='-[, widthB=2.4, lengthB=0.3',
                                lw=0.8, color='#333'),
                annotation_clip=False)
    ax.text(-1.35, 2.5, 'Cloud', ha='center', va='center', fontsize=8,
            fontweight='bold', rotation=90, style='italic',
            transform=ax.get_yaxis_transform(), clip_on=False)

    # ── X-axis: tier labels ──────────────────────────────────────────────
    tier_labels = ['Tier 1\nSingle table', 'Tier 2\nSingle join',
                   'Tier 3\nCross engine', 'Tier 4\nMulti join',
                   'Tier 5\nCross domain', 'Overall']
    ax.set_xticks(range(n_cols))
    ax.set_xticklabels(tier_labels, fontsize=8)
    # Bold the "Overall" tick label
    labels = ax.get_xticklabels()
    labels[-1].set_fontweight('bold')

    # ── Y-axis: model names ──────────────────────────────────────────────
    model_labels = ['Llama 3.2 3B', 'Llama 3.1 8B', 'Gemma-3 27B', 'DeepSeek R1']
    ax.set_yticks(range(n_rows))
    ax.set_yticklabels(model_labels, fontsize=9, fontweight='bold')

    # ── Colour bar ───────────────────────────────────────────────────────
    cbar = fig.colorbar(im, ax=ax, shrink=0.85, pad=0.03, aspect=15)
    cbar.set_label('Accuracy (%)', fontsize=8.5)
    cbar.set_ticks([0, 25, 50, 75, 100])
    cbar.ax.tick_params(labelsize=7.5)

    # ── Clean up spines ──────────────────────────────────────────────────
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False, top=False, right=False)

    plt.tight_layout()
    plt.subplots_adjust(left=0.20)
    plt.savefig(f'{OUTDIR}/fig_heatmap.pdf')
    plt.close()
    print(f'  fig_heatmap.pdf — {os.path.getsize(f"{OUTDIR}/fig_heatmap.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Accuracy bar chart (3 models, with error bars)
# ═══════════════════════════════════════════════════════════════════════════
def fig_accuracy_bar():
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    
    x = np.arange(5)
    width = 0.18
    offsets = [-1.5, -0.5, 0.5, 1.5]
    
    colors = [C_LOCAL, '#555555', C_LIGHT, '#775DA6']
    hatches = ['', '', H_CLOUD, H_CLOUD]
    
    for i, (model, tier_accs) in enumerate(zip(MODELS_SHORT, ACC)):
        ax.bar(x + offsets[i] * width, tier_accs, width * 0.88,
               label=f'{model} ({SOURCE[i]})',
               color=colors[i],
               edgecolor='#333333',
               hatch=hatches[i],
               linewidth=0.5)
    
    ax.set_xlabel('Query Complexity Tier')
    ax.set_ylabel('Accuracy (%)')
    ax.set_xticks(x)
    ax.set_xticklabels(['Tier 1', 'Tier 2', 'Tier 3', 'Tier 4', 'Tier 5'])
    ax.set_ylim(0, 115)
    ax.yaxis.grid(True, linestyle=':', alpha=0.4, color=C_GRID)
    ax.set_axisbelow(True)
    
    local_patch = mpatches.Patch(facecolor=C_LOCAL, edgecolor='#333', label='Local models')
    cloud_patch = mpatches.Patch(facecolor=C_LIGHT, edgecolor='#333', hatch='..', label='Cloud model')
    ax.legend(handles=[local_patch, cloud_patch], loc='upper right', framealpha=0.9,
              edgecolor='#999')
    
    plt.tight_layout()
    plt.savefig(f'{OUTDIR}/fig_accuracy_bar.pdf')
    plt.close()
    print(f'  fig_accuracy_bar.pdf — {os.path.getsize(f"{OUTDIR}/fig_accuracy_bar.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Tier difficulty gradient (line chart)
# ═══════════════════════════════════════════════════════════════════════════
def fig_tier_gradient():
    fig, ax = plt.subplots(figsize=(4.8, 3.0))
    
    markers = ['o', 's', '^', 'D']
    styles = ['-', '-', '--', ':']
    colors_line = [C_LOCAL, '#555555', C_ACCENT, '#775DA6']
    
    for i, (model, tier_accs) in enumerate(zip(MODELS_SHORT, ACC)):
        ax.plot(range(5), tier_accs, marker=markers[i], linestyle=styles[i],
                color=colors_line[i], markersize=6, label=f'{model} ({SOURCE[i]})',
                markeredgecolor='black', markeredgewidth=0.4)
    
    ax.set_xlabel('Query Complexity Tier')
    ax.set_ylabel('Accuracy (%)')
    ax.set_xticks(range(5))
    ax.set_xticklabels(['T1\n(Single)', 'T2\n(Join)', 'T3\n(Cross)', 'T4\n(Multi)', 'T5\n(Feder.)'],
                        fontsize=7.5)
    ax.set_ylim(-5, 115)
    ax.yaxis.grid(True, linestyle=':', alpha=0.3, color=C_GRID)
    ax.set_axisbelow(True)
    
    ax.legend(loc='upper right', framealpha=0.9, edgecolor='#999',
              handletextpad=0.4)
    
    plt.tight_layout()
    plt.savefig(f'{OUTDIR}/fig_tier_gradient.pdf')
    plt.close()
    print(f'  fig_tier_gradient.pdf — {os.path.getsize(f"{OUTDIR}/fig_tier_gradient.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Sovereignty–Capability Pareto frontier (3 models)
# ═══════════════════════════════════════════════════════════════════════════
def fig_pareto():
    fig, ax = plt.subplots(figsize=(4.5, 3.5))
    
    for i in range(4):
        marker = 'o' if SOURCE[i] == 'Local' else 's'
        color = C_LOCAL if SOURCE[i] == 'Local' else C_CLOUD
        facecolor = color if SOURCE[i] == 'Local' else 'white'
        
        # Error bars (Wilson CIs)
        ax.errorbar(SIGMA_I[i], OVERALL[i], yerr=CI_HALF[i],
                     fmt='none', ecolor='#999999', elinewidth=0.7, capsize=3, capthick=0.7,
                     zorder=4)
        ax.scatter(SIGMA_I[i], OVERALL[i], marker=marker, s=90,
                   c=facecolor, edgecolors=color, linewidths=1.2,
                   zorder=5)
        
        offx = 0.04 if SOURCE[i] == 'Local' else -0.04
        ha = 'left' if SOURCE[i] == 'Local' else 'right'
        ax.annotate(MODELS_SHORT[i], (SIGMA_I[i], OVERALL[i]),
                    xytext=(offx, 3), textcoords='offset points',
                    fontsize=7.5, ha=ha, va='bottom')
    
    # Pareto frontier
    ax.plot([0.0, 1.0], [90.0, 60.0], 'k--', linewidth=0.8, alpha=0.5, label='Pareto frontier')
    
    # Sovereignty zone
    ax.axvspan(0.5, 1.15, alpha=0.06, color='black', label='Sovereignty zone')
    ax.axhline(y=50, color='#AAAAAA', linewidth=0.4, linestyle=':')
    
    ax.set_xlabel(r'Infrastructure Sovereignty Index ($\sigma_I$)')
    ax.set_ylabel('Text-to-SQL Accuracy (%)')
    ax.set_xlim(-0.15, 1.15)
    ax.set_ylim(0, 108)
    ax.set_xticks([0.0, 0.5, 1.0])
    ax.set_xticklabels(['0.0\n(Cloud)', '0.5', '1.0\n(Local)'])
    
    ax.annotate(r'$\rho_{\max}=0$' + '\n(no risk assessment)', 
                xy=(0.0, 5), fontsize=6.5, color='#666', ha='center', style='italic')
    ax.annotate(r'$\rho_{\max}=1$' + '\n(full capability)',
                xy=(1.0, 5), fontsize=6.5, color='#333', ha='center', style='italic')
    
    local_h = plt.Line2D([], [], marker='o', color='w', markerfacecolor=C_LOCAL,
                          markeredgecolor=C_LOCAL, markersize=7, label='Local')
    cloud_h = plt.Line2D([], [], marker='s', color='w', markerfacecolor='white',
                          markeredgecolor=C_CLOUD, markersize=7, label='Cloud')
    ax.legend(handles=[local_h, cloud_h], loc='center left', framealpha=0.9,
              edgecolor='#999')
    
    plt.tight_layout()
    plt.savefig(f'{OUTDIR}/fig_pareto.pdf')
    plt.close()
    print(f'  fig_pareto.pdf — {os.path.getsize(f"{OUTDIR}/fig_pareto.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Observability bound (unchanged — no model-specific data)
# ═══════════════════════════════════════════════════════════════════════════
def fig_observability():
    fig, ax = plt.subplots(figsize=(4.2, 3.5))
    
    sd = np.linspace(0, 1, 100)
    si = np.linspace(0, 1, 100)
    SD, SI = np.meshgrid(sd, si)
    RHO = SD * SI
    
    levels = [0.0, 0.1, 0.25, 0.5, 0.75, 1.0]
    cs = ax.contour(SD, SI, RHO, levels=levels, colors='black', linewidths=0.6)
    ax.clabel(cs, levels, fmt=r'$\rho$=%.2f', fontsize=6.5, inline=True)
    
    ax.fill_between([0, 0.5], [0, 0], [1, 1], alpha=0.08, color='black')
    ax.fill_betweenx([0, 0.5], [0, 0], [1, 1], alpha=0.08, color='black')
    
    ax.plot(1.0, 1.0, 'ko', markersize=8, zorder=10)
    ax.annotate('Local\nmodels', (1.0, 1.0), xytext=(-12, -16), textcoords='offset points',
                fontsize=7, ha='center', fontweight='bold')
    
    ax.plot(1.0, 0.0, 'ks', markersize=8, fillstyle='none', linewidth=1.5, zorder=10)
    ax.annotate('Cloud\nmodels', (1.0, 0.0), xytext=(-12, 8), textcoords='offset points',
                fontsize=7, ha='center')
    
    ax.axhline(y=0.5, color='#999', linewidth=0.4, linestyle='--')
    ax.axvline(x=0.5, color='#999', linewidth=0.4, linestyle='--')
    
    ax.set_xlabel(r'Data Sovereignty ($\sigma_D$)')
    ax.set_ylabel(r'Infrastructure Sovereignty ($\sigma_I$)')
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_aspect('equal')
    
    ax.text(0.25, 0.25, 'Insufficient\nsovereignty', fontsize=6.5, ha='center', va='center',
            style='italic', color='#888')
    ax.text(0.78, 0.78, 'Full\ncapability', fontsize=6.5, ha='center', va='center',
            fontweight='bold', color='#333')
    
    plt.tight_layout()
    plt.savefig(f'{OUTDIR}/fig_observability.pdf')
    plt.close()
    print(f'  fig_observability.pdf — {os.path.getsize(f"{OUTDIR}/fig_observability.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
# Fig: Risk assessment capability matrix
# ═══════════════════════════════════════════════════════════════════════════
def fig_risk_capability():
    fig, ax = plt.subplots(figsize=(5.0, 2.8))
    ax.axis('off')
    
    capabilities = ['SQL Anomaly\nDetection', 'Schema-Drift\nMonitoring', 
                     'Confidence\nGating', 'Feedback\nLoop']
    requirements = [r'$\sigma_I \geq 0.50$', r'$\sigma_D \geq 0.75$', 
                     r'$\sigma_I \geq 0.75$', r'$\sigma_D \geq 0.50$']
    local_status = ['Yes', 'Yes', 'Yes', 'Yes']
    cloud_status = ['No', 'No', 'No', 'No']
    
    col_x = [0.02, 0.28, 0.52, 0.70, 0.88]
    col_widths = [0.26, 0.24, 0.18, 0.18]
    headers = ['Capability', 'Requirement', 'Local\n(\u03c3=1.0)', 'Cloud\n(\u03c3=0.0)']
    
    y_start = 0.88
    row_h = 0.15
    
    for j, (x, w, h) in enumerate(zip(col_x, col_widths, headers)):
        rect = mpatches.FancyBboxPatch((x, y_start), w - 0.01, row_h,
                                        boxstyle="square,pad=0", 
                                        facecolor='#E0E0E0', edgecolor='black', linewidth=0.5)
        ax.add_patch(rect)
        ax.text(x + w/2 - 0.005, y_start + row_h/2, h, ha='center', va='center',
                fontsize=7.5, fontweight='bold')
    
    for i in range(4):
        y = y_start - (i + 1) * row_h
        bg = 'white' if i % 2 == 0 else '#F8F8F8'
        
        row_data = [capabilities[i], requirements[i], local_status[i], cloud_status[i]]
        for j, (x, w, val) in enumerate(zip(col_x, col_widths, row_data)):
            rect = mpatches.FancyBboxPatch((x, y), w - 0.01, row_h,
                                            boxstyle="square,pad=0",
                                            facecolor=bg, edgecolor='#999', linewidth=0.3)
            ax.add_patch(rect)
            
            if val == 'Yes':
                ax.text(x + w/2 - 0.005, y + row_h/2, 'Yes', ha='center', va='center',
                        fontsize=7.5, color='#2d6a2e', fontweight='bold')
            elif val == 'No':
                ax.text(x + w/2 - 0.005, y + row_h/2, 'No', ha='center', va='center',
                        fontsize=7.5, color='#a02020', fontweight='bold')
            else:
                ax.text(x + w/2 - 0.005, y + row_h/2, val, ha='center', va='center',
                        fontsize=7)
    
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(0.15, 1.05)
    
    plt.tight_layout()
    plt.savefig(f'{OUTDIR}/fig_risk_capability.pdf')
    plt.close()
    print(f'  fig_risk_capability.pdf — {os.path.getsize(f"{OUTDIR}/fig_risk_capability.pdf")/1024:.1f} KB')


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('Generating figures (v3 — 3 models, no TCO)...\n')
    
    fig_heatmap()
    fig_accuracy_bar()
    fig_tier_gradient()
    fig_pareto()
    fig_observability()
    fig_risk_capability()
    
    print(f'\nAll figures saved to {OUTDIR}/')
