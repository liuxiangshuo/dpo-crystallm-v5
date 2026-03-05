#!/usr/bin/env python3
"""
Phase 5: Paper Figure and Table Generation

Generates all figures and tables needed for the DPO-CrystaLLM paper:
  - Fig.1: Method pipeline diagram (schematic, requires manual finishing)
  - Fig.2: Beta sensitivity curve
  - Fig.3: Energy distribution comparison (histogram + CDF)
  - Fig.4: Ablation heatmap
  - Fig.5: Multi-material comparison (grouped bar chart)
  - Fig.6: DFT vs proxy correlation scatter
  - Tab.1: Main results table
  - Tab.2: Multi-material results
  - Tab.3: DFT validation results

Usage:
    python scripts/46_generate_paper_figures.py \
        --results_dir reports/ \
        --out_dir reports/paper_figures

    # Generate specific figure:
    python scripts/46_generate_paper_figures.py \
        --results_dir reports/ \
        --out_dir reports/paper_figures \
        --figures fig2,fig3
"""

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import rcParams
    # Paper-quality settings
    rcParams["font.family"] = "serif"
    rcParams["font.size"] = 11
    rcParams["axes.labelsize"] = 13
    rcParams["axes.titlesize"] = 14
    rcParams["legend.fontsize"] = 10
    rcParams["xtick.labelsize"] = 10
    rcParams["ytick.labelsize"] = 10
    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    print("WARNING: matplotlib not available. Install with: pip install matplotlib")


def load_json(path):
    """Load JSON file, return None if not found."""
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return None


def load_csv_rows(path):
    """Load CSV into list of dicts."""
    p = Path(path)
    if not p.exists():
        return []
    with open(p) as f:
        return list(csv.DictReader(f))


def fig2_beta_sensitivity(results_dir, out_dir):
    """Fig.2: Beta sensitivity curve."""
    data_path = Path(results_dir) / "beta_sweep" / "beta_sweep_plot_data.json"
    csv_path = Path(results_dir) / "beta_sweep" / "beta_sweep_results.csv"

    # Try JSON first
    data = load_json(data_path)
    if data is None:
        # Fall back to CSV
        rows = load_csv_rows(csv_path)
        if not rows:
            print("  [fig2] No beta sweep data found, skipping")
            return
        data = {
            "betas": [float(r["beta"]) for r in rows],
            "stability_rates": [float(r["stability_rate"]) for r in rows],
            "median_energies": [float(r["median_energy"]) for r in rows],
        }

    betas = data["betas"]
    stability = data["stability_rates"]
    medians = data["median_energies"]

    fig, ax1 = plt.subplots(figsize=(7, 5))

    color1 = "#1565C0"
    color2 = "#C62828"
    ax1.set_xlabel(r"DPO $\beta$")
    ax1.set_ylabel("Stability Rate (%)", color=color1)
    line1, = ax1.plot(betas, stability, "o-", color=color1, linewidth=2,
                      markersize=7, label="Stability Rate", zorder=3)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.set_xscale("log")
    ax1.axhline(y=12.12, color="gray", linestyle=":", alpha=0.5)
    ax1.text(betas[0], 12.5, "Baseline", color="gray", fontsize=9, alpha=0.7)
    ax1.grid(True, alpha=0.15)

    ax2 = ax1.twinx()
    ax2.set_ylabel("Median Energy (eV/atom)", color=color2)
    line2, = ax2.plot(betas, medians, "s--", color=color2, linewidth=2,
                      markersize=7, label="Median Energy", zorder=2)
    ax2.tick_params(axis="y", labelcolor=color2)

    lines = [line1, line2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left")

    fig.tight_layout()
    fig.savefig(out_dir / "fig2_beta_sensitivity.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "fig2_beta_sensitivity.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("  [fig2] Beta sensitivity curve saved")


def fig3_energy_distribution(results_dir, out_dir):
    """Fig.3: Energy distribution comparison (histogram + CDF)."""
    # Try to load from multiple possible locations
    for exp_name in ["exp_ablation_dpo", "exp_final_50k"]:
        base_csv = Path(f"outputs/{exp_name}/baseline/scored/ehull_scores.csv")
        dpo_csv = Path(f"outputs/{exp_name}/dpo/scored/ehull_scores.csv")
        if base_csv.exists() and dpo_csv.exists():
            break
    else:
        print("  [fig3] No scored data found, skipping")
        return

    def load_energies(csv_path):
        energies = []
        with open(csv_path) as f:
            for row in csv.DictReader(f):
                v = row.get("score_e_per_atom", "").strip()
                if v:
                    try:
                        energies.append(float(v))
                    except ValueError:
                        pass
        return np.array(energies)

    base_e = load_energies(base_csv)
    dpo_e = load_energies(dpo_csv)

    # Clip for visualization
    clip_min, clip_max = -8, 5
    base_clip = base_e[(base_e >= clip_min) & (base_e <= clip_max)]
    dpo_clip = dpo_e[(dpo_e >= clip_min) & (dpo_e <= clip_max)]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Histogram
    bins = np.linspace(clip_min, clip_max, 100)
    ax1.hist(base_clip, bins=bins, alpha=0.6, density=True, label="Baseline",
             color="#1565C0", edgecolor="white", linewidth=0.3)
    ax1.hist(dpo_clip, bins=bins, alpha=0.6, density=True, label="DPO",
             color="#C62828", edgecolor="white", linewidth=0.3)
    ax1.set_xlabel("Energy per Atom (eV)")
    ax1.set_ylabel("Density")
    ax1.set_title("(a) Energy Distribution")
    ax1.legend()
    ax1.grid(True, alpha=0.15)

    # CDF
    for arr, label, color in [(base_e, "Baseline", "#1565C0"), (dpo_e, "DPO", "#C62828")]:
        sorted_e = np.sort(arr)
        cdf = np.arange(1, len(sorted_e) + 1) / len(sorted_e)
        # Downsample for plotting
        step = max(1, len(sorted_e) // 2000)
        ax2.plot(sorted_e[::step], cdf[::step], label=label, color=color, linewidth=1.5)

    ax2.set_xlabel("Energy per Atom (eV)")
    ax2.set_ylabel("Cumulative Fraction")
    ax2.set_title("(b) Cumulative Distribution")
    ax2.set_xlim(clip_min, clip_max)
    ax2.legend()
    ax2.grid(True, alpha=0.15)

    fig.tight_layout()
    fig.savefig(out_dir / "fig3_energy_distribution.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "fig3_energy_distribution.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("  [fig3] Energy distribution saved")


def fig4_ablation_heatmap(results_dir, out_dir):
    """Fig.4: Factor ablation heatmap."""
    csv_path = Path(results_dir) / "factor_ablation" / "factor_ablation_results.csv"
    rows = load_csv_rows(csv_path)
    if not rows:
        print("  [fig4] No ablation data found, skipping")
        return

    # Group by factor
    factors = {}
    for r in rows:
        tag = r["experiment"]
        factor = tag.split("_")[0]
        if factor not in factors:
            factors[factor] = []
        factors[factor].append(r)

    # Create heatmap data
    factor_names = sorted(factors.keys())
    metrics = ["stability_rate", "mean_energy", "median_energy", "hit_rate"]

    fig, axes = plt.subplots(1, len(factor_names), figsize=(4 * len(factor_names), 5),
                             squeeze=False)

    for fi, factor in enumerate(factor_names):
        ax = axes[0][fi]
        exps = factors[factor]
        exp_labels = [e["experiment"].replace(f"{factor}_", "") for e in exps]
        data = np.array([[float(e.get(m, 0)) for m in metrics] for e in exps])

        # Normalize each column for coloring
        im = ax.imshow(data, aspect="auto", cmap="RdYlGn")
        ax.set_xticks(range(len(metrics)))
        ax.set_xticklabels(["Stab%", "Mean E", "Med E", "Hit%"], fontsize=8, rotation=45)
        ax.set_yticks(range(len(exp_labels)))
        ax.set_yticklabels(exp_labels, fontsize=8)
        ax.set_title(factor, fontsize=11)

        # Add text annotations
        for i in range(len(exp_labels)):
            for j in range(len(metrics)):
                val = data[i, j]
                fmt = f"{val:.2f}" if abs(val) < 100 else f"{val:.1f}"
                ax.text(j, i, fmt, ha="center", va="center", fontsize=7)

    fig.tight_layout()
    fig.savefig(out_dir / "fig4_ablation_heatmap.pdf", dpi=300, bbox_inches="tight")
    fig.savefig(out_dir / "fig4_ablation_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close()
    print("  [fig4] Ablation heatmap saved")


def fig5_multi_material(results_dir, out_dir):
    """Fig.5: Multi-material comparison (grouped bar chart)."""
    # Look for multi-target results
    multi_dirs = list(Path(results_dir).glob("multi_*"))
    if not multi_dirs:
        # Try individual exp reports
        pass

    # Collect results from any available experiments
    materials = {}
    for exp_dir in Path("outputs").iterdir():
        config_sh = Path(f"experiments/{exp_dir.name}/config.sh")
        results_json = exp_dir / "dpo" / "scored" / "ehull_estimates.csv"

    # Placeholder - will be populated after multi-material experiments
    print("  [fig5] Multi-material data not yet available, creating template")

    # Create template figure
    fig, ax = plt.subplots(figsize=(10, 6))
    materials_list = ["LiFePO4", "NaCl", "TiO2", "BaTiO3"]
    x = np.arange(len(materials_list))
    width = 0.35
    baseline = [12.12, 0, 0, 0]  # placeholder
    dpo = [12.27, 0, 0, 0]  # placeholder

    ax.bar(x - width/2, baseline, width, label="Baseline", color="#1565C0", alpha=0.8)
    ax.bar(x + width/2, dpo, width, label="DPO (best)", color="#C62828", alpha=0.8)
    ax.set_xlabel("Target Material")
    ax.set_ylabel("Stability Rate (%)")
    ax.set_title("Multi-Material DPO Alignment Results")
    ax.set_xticks(x)
    ax.set_xticklabels(materials_list)
    ax.legend()
    ax.grid(True, alpha=0.15, axis="y")

    fig.tight_layout()
    fig.savefig(out_dir / "fig5_multi_material_TEMPLATE.png", dpi=150, bbox_inches="tight")
    plt.close()


def tab1_main_results(results_dir, out_dir):
    """Tab.1: Main experiment results table (LaTeX)."""
    # Collect from various sources
    rows = []

    # Baseline from exp_final_50k
    summary_csv = Path(results_dir) / "exp_final_50k" / "summary.csv"
    if summary_csv.exists():
        for r in load_csv_rows(summary_csv):
            rows.append(r)

    # Ablation results
    for exp in ["exp_ablation_dpo", "exp_ablation_cdpo", "exp_ablation_simpo"]:
        summary = Path(results_dir) / exp / "summary.csv"
        if summary.exists():
            for r in load_csv_rows(summary):
                if r.get("model", "").lower() == "dpo":
                    r["experiment"] = exp
                    rows.append(r)

    if not rows:
        print("  [tab1] No results available yet, creating template")
        # Write template
        with open(out_dir / "tab1_main_results.tex", "w") as f:
            f.write("% Table 1: Main Results (to be filled after experiments)\n")
            f.write("\\begin{table}[h]\n\\centering\n")
            f.write("\\caption{Main experimental results on LiFePO4 generation.}\n")
            f.write("\\begin{tabular}{lcccccc}\n\\toprule\n")
            f.write("Method & Validity & Stability & Hit Rate & Mean E & Median E & Eff. \\\\\n")
            f.write("\\midrule\n")
            f.write("Baseline & & & & & & \\\\\n")
            f.write("DPO ($\\beta$=0.1) & & & & & & \\\\\n")
            f.write("DPO ($\\beta$=2.5) & & & & & & \\\\\n")
            f.write("cDPO & & & & & & \\\\\n")
            f.write("SimPO & & & & & & \\\\\n")
            f.write("Best-of-N & & & & & & \\\\\n")
            f.write("\\bottomrule\n\\end{tabular}\n")
            f.write("\\label{tab:main_results}\n\\end{table}\n")
        return

    # Generate LaTeX table
    with open(out_dir / "tab1_main_results.tex", "w") as f:
        f.write("\\begin{table}[h]\n\\centering\n")
        f.write("\\caption{Main experimental results on LiFePO4 generation.}\n")
        f.write("\\begin{tabular}{lcccccc}\n\\toprule\n")
        f.write("Method & Validity (\\%) & Stability (\\%) & Hit Rate (\\%) & "
                "Mean E & Median E & Eff. (s/stable) \\\\\n")
        f.write("\\midrule\n")
        for r in rows:
            model = r.get("model", r.get("experiment", ""))
            vr = r.get("valid_rate", "")
            sr = r.get("stability_rate", "")
            hr = r.get("hit_rate", "")
            me = r.get("score_mean", "")
            med = r.get("score_median", "")
            eff = r.get("efficiency", "")
            f.write(f"{model} & {vr} & {sr} & {hr} & {me} & {med} & {eff} \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n")
        f.write("\\label{tab:main_results}\n\\end{table}\n")

    print("  [tab1] Main results table saved")


def main():
    ap = argparse.ArgumentParser(description="Generate paper figures and tables")
    ap.add_argument("--results_dir", default="reports", help="Base reports directory")
    ap.add_argument("--out_dir", default="reports/paper_figures", help="Output directory")
    ap.add_argument("--figures", default="all",
                    help="Comma-separated figure IDs (fig2,fig3,fig4,fig5,tab1) or 'all'")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not HAS_MPL:
        print("ERROR: matplotlib is required. Install with: pip install matplotlib")
        print("Generating tables only...")

    figs = args.figures.split(",") if args.figures != "all" else [
        "fig2", "fig3", "fig4", "fig5", "tab1"
    ]

    print(f"Generating figures: {figs}")
    print(f"Output: {out_dir}")
    print()

    if "fig2" in figs and HAS_MPL:
        fig2_beta_sensitivity(args.results_dir, out_dir)
    if "fig3" in figs and HAS_MPL:
        fig3_energy_distribution(args.results_dir, out_dir)
    if "fig4" in figs and HAS_MPL:
        fig4_ablation_heatmap(args.results_dir, out_dir)
    if "fig5" in figs and HAS_MPL:
        fig5_multi_material(args.results_dir, out_dir)
    if "tab1" in figs:
        tab1_main_results(args.results_dir, out_dir)

    print(f"\nAll requested figures generated in {out_dir}/")


if __name__ == "__main__":
    main()
