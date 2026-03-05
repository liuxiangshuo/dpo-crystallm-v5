#!/usr/bin/env python3
"""
Three-way comparison report: Baseline vs SFT vs SFT+DPO.

Generates a comprehensive markdown report comparing all three models across
key metrics: stability rate, energy distribution, composition hit rate,
space group distribution, and diversity.

Usage:
    python scripts/50_evaluate_three_way.py \
        --baseline_dir outputs/exp_sft_rl/LiFePO4/baseline/scored \
        --sft_dir outputs/exp_sft_rl/LiFePO4/sft/scored \
        --dpo_dir outputs/exp_sft_rl/LiFePO4/sft_dpo/scored \
        --target LiFePO4 \
        --out_dir reports/exp_sft_rl/LiFePO4

    # Multi-target (comma-separated):
    python scripts/50_evaluate_three_way.py \
        --baseline_dir outputs/exp_sft_rl/LiFePO4/baseline/scored,outputs/exp_sft_rl/NaCl/baseline/scored \
        --sft_dir outputs/exp_sft_rl/LiFePO4/sft/scored,outputs/exp_sft_rl/NaCl/sft/scored \
        --dpo_dir outputs/exp_sft_rl/LiFePO4/sft_dpo/scored,outputs/exp_sft_rl/NaCl/sft_dpo/scored \
        --target LiFePO4,NaCl \
        --out_dir reports/exp_sft_rl/comparison
"""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from collections import Counter

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    HAS_MPL = True
except ImportError:
    HAS_MPL = False


def load_json_safe(path: Path):
    if path and path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_scores(scored_dir: Path) -> dict:
    """Load evaluation data from a scored directory."""
    result = {
        "ehull_summary": {},
        "energies": [],
        "formulas": Counter(),
        "total": 0,
        "valid": 0,
        "stability_rate": 0.0,
        "stable_count": 0,
        "composition_hit_rate": 0.0,
        "energy_mean": float("nan"),
        "energy_median": float("nan"),
        "energy_std": float("nan"),
    }

    # Ehull summary
    ehull_summary = load_json_safe(scored_dir / "ehull_summary.json")
    result["ehull_summary"] = ehull_summary
    result["stability_rate"] = ehull_summary.get("stability_rate", 0.0)
    result["stable_count"] = ehull_summary.get("stable_count_ehull_005", 0)

    # Eval CSV for energies and composition
    eval_csv = scored_dir / "eval.csv"
    if eval_csv.exists():
        energies = []
        total = 0
        valid = 0
        hit_target = 0
        with open(eval_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                total += 1
                if row.get("valid") == "True":
                    valid += 1
                if row.get("hit_target") == "True":
                    hit_target += 1
                e_str = (row.get("score_e_per_atom") or "").strip()
                if e_str:
                    try:
                        energies.append(float(e_str))
                    except ValueError:
                        pass
                formula = row.get("formula", "")
                if formula:
                    result["formulas"][formula] += 1

        result["total"] = total
        result["valid"] = valid
        result["energies"] = energies
        result["composition_hit_rate"] = hit_target / total if total > 0 else 0.0

        if energies:
            result["energy_mean"] = statistics.mean(energies)
            result["energy_median"] = statistics.median(energies)
            result["energy_std"] = statistics.stdev(energies) if len(energies) > 1 else 0.0

    # Composite reward summary
    result["reward_summary"] = load_json_safe(scored_dir / "composite_reward_summary.json")

    # Novelty
    result["novelty"] = load_json_safe(scored_dir / "novelty.json")

    return result


def generate_plots(baseline, sft, dpo, out_dir: Path, target: str):
    """Generate comparison plots for three models."""
    if not HAS_MPL:
        return

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    colors = {"Baseline": "#2196F3", "SFT": "#4CAF50", "SFT+DPO": "#FF5722"}
    models = {"Baseline": baseline, "SFT": sft, "SFT+DPO": dpo}

    # 1. Energy histogram
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, data in models.items():
        if data["energies"]:
            ax.hist(data["energies"], bins=80, alpha=0.5, label=label,
                    color=colors[label], density=True)
    ax.set_xlabel("MatGL Energy (eV/atom)", fontsize=12)
    ax.set_ylabel("Density", fontsize=12)
    ax.set_title(f"Energy Distribution: {target}", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig(plots_dir / "energy_histogram.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 2. Stability rate bar chart
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = list(models.keys())
    rates = [models[l]["stability_rate"] * 100 for l in labels]
    bars = ax.bar(labels, rates, color=[colors[l] for l in labels], alpha=0.8)
    ax.set_ylabel("Stability Rate (%)", fontsize=12)
    ax.set_title(f"Stability Rate Comparison: {target}", fontsize=14)
    for bar, rate in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                f"{rate:.2f}%", ha="center", va="bottom", fontsize=11)
    ax.grid(True, alpha=0.2, axis="y")
    plt.tight_layout()
    plt.savefig(plots_dir / "stability_comparison.png", dpi=150, bbox_inches="tight")
    plt.close()

    # 3. Energy CDF
    fig, ax = plt.subplots(figsize=(10, 6))
    for label, data in models.items():
        if data["energies"]:
            sorted_e = sorted(data["energies"])
            cdf = np.arange(1, len(sorted_e) + 1) / len(sorted_e)
            ax.plot(sorted_e, cdf, label=label, color=colors[label], linewidth=2)
    ax.set_xlabel("MatGL Energy (eV/atom)", fontsize=12)
    ax.set_ylabel("Cumulative Fraction", fontsize=12)
    ax.set_title(f"Energy CDF: {target}", fontsize=14)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig(plots_dir / "energy_cdf.png", dpi=150, bbox_inches="tight")
    plt.close()


def generate_report(baseline, sft, dpo, out_dir: Path, target: str):
    """Generate markdown comparison report."""
    md_path = out_dir / "three_way_comparison.md"

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Three-Way Comparison Report: {target}\n\n")
        f.write("**Models**: Baseline vs SFT vs SFT+DPO\n\n")

        # Key metrics table
        f.write("## 1. Key Metrics\n\n")
        f.write("| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |\n")
        f.write("|--------|----------|-----|---------|-------------|----------------|\n")

        # Validity
        def safe_rate(d, key, total_key="total"):
            v = d.get(key, 0)
            t = d.get(total_key, 1)
            return v / t if t > 0 else 0

        b_valid = baseline["valid"] / baseline["total"] if baseline["total"] else 0
        s_valid = sft["valid"] / sft["total"] if sft["total"] else 0
        d_valid = dpo["valid"] / dpo["total"] if dpo["total"] else 0
        f.write(f"| Validity Rate | {b_valid:.4f} | {s_valid:.4f} | {d_valid:.4f} | "
                f"{s_valid - b_valid:+.4f} | {d_valid - b_valid:+.4f} |\n")

        # Stability
        b_stab = baseline["stability_rate"]
        s_stab = sft["stability_rate"]
        d_stab = dpo["stability_rate"]
        f.write(f"| **Stability Rate** | {b_stab:.4f} | {s_stab:.4f} | **{d_stab:.4f}** | "
                f"{s_stab - b_stab:+.4f} | {d_stab - b_stab:+.4f} |\n")

        # Stable count
        f.write(f"| Stable Count | {baseline['stable_count']} | {sft['stable_count']} | "
                f"{dpo['stable_count']} | "
                f"{sft['stable_count'] - baseline['stable_count']:+d} | "
                f"{dpo['stable_count'] - baseline['stable_count']:+d} |\n")

        # Composition hit rate
        b_hit = baseline["composition_hit_rate"]
        s_hit = sft["composition_hit_rate"]
        d_hit = dpo["composition_hit_rate"]
        f.write(f"| Composition Hit Rate | {b_hit:.4f} | {s_hit:.4f} | {d_hit:.4f} | "
                f"{s_hit - b_hit:+.4f} | {d_hit - b_hit:+.4f} |\n")

        f.write("\n")

        # Energy distribution table
        f.write("## 2. MatGL Energy Distribution (eV/atom, lower is better)\n\n")
        f.write("| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |\n")
        f.write("|--------|----------|-----|---------|-------------|----------------|\n")

        for metric_name, metric_key in [
            ("Mean", "energy_mean"),
            ("Median", "energy_median"),
            ("Std", "energy_std"),
        ]:
            bv = baseline[metric_key]
            sv = sft[metric_key]
            dv = dpo[metric_key]
            b_str = f"{bv:.4f}" if math.isfinite(bv) else "N/A"
            s_str = f"{sv:.4f}" if math.isfinite(sv) else "N/A"
            d_str = f"{dv:.4f}" if math.isfinite(dv) else "N/A"
            delta_s = f"{sv - bv:+.4f}" if (math.isfinite(bv) and math.isfinite(sv)) else "N/A"
            delta_d = f"{dv - bv:+.4f}" if (math.isfinite(bv) and math.isfinite(dv)) else "N/A"
            f.write(f"| {metric_name} | {b_str} | {s_str} | {d_str} | {delta_s} | {delta_d} |\n")

        # Percentiles
        for label, data in [("Baseline", baseline), ("SFT", sft), ("SFT+DPO", dpo)]:
            if data["energies"]:
                sorted_e = sorted(data["energies"])
                n = len(sorted_e)
                p10 = sorted_e[int(n * 0.1)] if n > 10 else sorted_e[0]
                p90 = sorted_e[int(n * 0.9)] if n > 10 else sorted_e[-1]
                f.write(f"\n**{label}**: P10={p10:.4f}, P90={p90:.4f}, "
                        f"Best={sorted_e[0]:.4f}, Worst={sorted_e[-1]:.4f}")
        f.write("\n\n")

        # Composite reward (if available)
        if baseline.get("reward_summary"):
            def reward_mean_str(data: dict, new_key: str, legacy_key: str = None) -> str:
                summary = data.get("reward_summary", {}) or {}

                # New format: nested component stats, e.g. r_proxy.mean
                component = summary.get(new_key)
                if isinstance(component, dict):
                    v = component.get("mean")
                    if isinstance(v, (int, float)) and math.isfinite(v):
                        return f"{v:.4f}"

                # Backward-compatible old flat key format
                if legacy_key:
                    v = summary.get(legacy_key)
                    if isinstance(v, (int, float)) and math.isfinite(v):
                        return f"{v:.4f}"
                return "N/A"

            f.write("## 3. Composite Reward\n\n")
            f.write("| Metric | Baseline | SFT | SFT+DPO |\n")
            f.write("|--------|----------|-----|--------|\n")

            reward_metrics = [
                ("R_proxy", "r_proxy", "r_energy_mean"),
                ("R_geom", "r_geom", "r_structure_mean"),
                ("R_comp", "r_comp", "r_composition_mean"),
                ("R_novel", "r_novel", "r_difficulty_mean"),
                ("R_total", "r_total", "r_total_mean"),
            ]
            for label, new_key, legacy_key in reward_metrics:
                bv = reward_mean_str(baseline, new_key, legacy_key)
                sv = reward_mean_str(sft, new_key, legacy_key)
                dv = reward_mean_str(dpo, new_key, legacy_key)
                f.write(f"| {label} | {bv} | {sv} | {dv} |\n")
            f.write("\n")

        # Plots
        f.write("## 4. Visualizations\n\n")
        f.write("![Energy Histogram](plots/energy_histogram.png)\n\n")
        f.write("![Stability Comparison](plots/stability_comparison.png)\n\n")
        f.write("![Energy CDF](plots/energy_cdf.png)\n\n")

        # Interpretation
        f.write("## 5. Interpretation\n\n")

        improvement = d_stab - b_stab
        if improvement > 0.02:
            f.write(f"SFT+DPO shows a meaningful improvement of **{improvement:.2%}** "
                    f"in stability rate over baseline.\n\n")
        elif improvement > 0:
            f.write(f"SFT+DPO shows a marginal improvement of **{improvement:.2%}** "
                    f"in stability rate over baseline. "
                    f"This may be within noise; larger samples are recommended.\n\n")
        else:
            f.write(f"SFT+DPO does not improve stability rate over baseline "
                    f"(delta={improvement:.2%}). "
                    f"Consider tuning hyperparameters or increasing training data.\n\n")

        sft_improvement = s_stab - b_stab
        if sft_improvement > 0:
            f.write(f"SFT alone contributes {sft_improvement:.2%} improvement, "
                    f"suggesting the space-group distribution shift is effective.\n\n")

    print(f"Report: {md_path}")
    return md_path


def main():
    ap = argparse.ArgumentParser(description="Three-way comparison: Baseline vs SFT vs SFT+DPO")
    ap.add_argument("--baseline_dir", required=True,
                    help="Baseline scored directory (or comma-separated for multi-target)")
    ap.add_argument("--sft_dir", required=True,
                    help="SFT scored directory (or comma-separated)")
    ap.add_argument("--dpo_dir", required=True,
                    help="SFT+DPO scored directory (or comma-separated)")
    ap.add_argument("--target", required=True,
                    help="Target composition(s) (comma-separated)")
    ap.add_argument("--out_dir", required=True,
                    help="Output directory for report")
    args = ap.parse_args()

    targets = [t.strip() for t in args.target.split(",")]
    baseline_dirs = [d.strip() for d in args.baseline_dir.split(",")]
    sft_dirs = [d.strip() for d in args.sft_dir.split(",")]
    dpo_dirs = [d.strip() for d in args.dpo_dir.split(",")]

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_results = []

    for i, target in enumerate(targets):
        base_dir = Path(baseline_dirs[i]) if i < len(baseline_dirs) else Path(baseline_dirs[-1])
        sft_dir = Path(sft_dirs[i]) if i < len(sft_dirs) else Path(sft_dirs[-1])
        dpo_dir = Path(dpo_dirs[i]) if i < len(dpo_dirs) else Path(dpo_dirs[-1])

        print(f"\n{'='*60}")
        print(f"Evaluating: {target}")
        print(f"{'='*60}")

        baseline = load_scores(base_dir)
        sft = load_scores(sft_dir)
        dpo = load_scores(dpo_dir)

        target_out = out_dir / target if len(targets) > 1 else out_dir
        target_out.mkdir(parents=True, exist_ok=True)

        generate_plots(baseline, sft, dpo, target_out, target)
        report = generate_report(baseline, sft, dpo, target_out, target)

        all_results.append({
            "target": target,
            "baseline_stability": baseline["stability_rate"],
            "sft_stability": sft["stability_rate"],
            "dpo_stability": dpo["stability_rate"],
            "baseline_energy_mean": baseline["energy_mean"],
            "sft_energy_mean": sft["energy_mean"],
            "dpo_energy_mean": dpo["energy_mean"],
        })

    # Cross-target summary CSV
    if len(targets) > 1:
        summary_csv = out_dir / "three_way_summary.csv"
        with open(summary_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[
                "target", "baseline_stability", "sft_stability", "dpo_stability",
                "baseline_energy_mean", "sft_energy_mean", "dpo_energy_mean",
            ])
            w.writeheader()
            for r in all_results:
                out_row = {}
                for k, v in r.items():
                    out_row[k] = f"{v:.6f}" if isinstance(v, float) and math.isfinite(v) else v
                w.writerow(out_row)
        print(f"\nCross-target summary: {summary_csv}")

    print("\nDone!")


if __name__ == "__main__":
    main()
