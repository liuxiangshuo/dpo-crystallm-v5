#!/usr/bin/env python3
"""
Phase 2.3: Best-of-N Sampling and Rejection Sampling Baselines

Computes baseline comparison metrics without any DPO training:
  - Best-of-N: Select top-K samples by energy from N candidates
  - Rejection Sampling: Filter samples by energy threshold

These are critical baselines for the paper — DPO must outperform
these simple post-hoc selection methods to demonstrate value.

Usage:
    python scripts/44_baselines_bon_rejection.py \
        --scores_csv outputs/exp_final_50k/baseline/scored/ehull_scores.csv \
        --ehull_csv outputs/exp_final_50k/baseline/scored/ehull_estimates.csv \
        --labels_csv outputs/exp_final_50k/baseline/scored/labels.csv \
        --target LiFePO4 \
        --out_dir reports/baselines_comparison

    # Compare with DPO results:
    python scripts/44_baselines_bon_rejection.py \
        --scores_csv outputs/exp_final_50k/baseline/scored/ehull_scores.csv \
        --ehull_csv outputs/exp_final_50k/baseline/scored/ehull_estimates.csv \
        --labels_csv outputs/exp_final_50k/baseline/scored/labels.csv \
        --dpo_scores_csv outputs/exp_ablation_dpo/dpo/scored/ehull_scores.csv \
        --dpo_ehull_csv outputs/exp_ablation_dpo/dpo/scored/ehull_estimates.csv \
        --dpo_labels_csv outputs/exp_ablation_dpo/dpo/scored/labels.csv \
        --target LiFePO4 \
        --out_dir reports/baselines_comparison
"""

import argparse
import csv
import json
from pathlib import Path

import numpy as np


def load_scored_data(scores_csv, ehull_csv, labels_csv, target=None):
    """Load and merge scored data from multiple CSVs."""
    # Load scores
    scores = {}
    with open(scores_csv) as f:
        for row in csv.DictReader(f):
            fname = row["file"]
            v = row.get("score_e_per_atom", "").strip()
            if v:
                try:
                    scores[fname] = float(v)
                except ValueError:
                    pass

    # Load ehull
    ehull = {}
    if Path(ehull_csv).exists():
        with open(ehull_csv) as f:
            for row in csv.DictReader(f):
                fname = row["file"]
                v = row.get("ehull_proxy", "").strip()
                if v:
                    try:
                        ehull[fname] = float(v)
                    except ValueError:
                        pass

    # Load labels (for hit_target filtering)
    hit_target = set()
    all_files = set()
    if labels_csv and Path(labels_csv).exists():
        with open(labels_csv) as f:
            for row in csv.DictReader(f):
                fname = row["file"]
                all_files.add(fname)
                if row.get("hit_target", "").lower() in ("true", "1", "yes"):
                    hit_target.add(fname)

    # Merge
    data = []
    for fname in scores:
        entry = {
            "file": fname,
            "energy": scores[fname],
            "ehull": ehull.get(fname, None),
            "hit_target": fname in hit_target,
            "stable": ehull.get(fname, 999) < 0.05,
        }
        data.append(entry)

    return data, len(all_files)


def best_of_n_analysis(data, n_values=None):
    """
    Best-of-N analysis: from N total samples, if you pick top-K by energy,
    what stability rate do you achieve?

    Returns dict mapping N -> {stability_rate, mean_energy, median_energy, ...}
    """
    if n_values is None:
        n_values = [100, 500, 1000, 2000, 5000, 10000, 20000, 50000]

    # Sort by energy (ascending = lower is better)
    sorted_data = sorted(data, key=lambda x: x["energy"])
    total = len(sorted_data)

    results = {}
    for n in n_values:
        if n > total:
            continue
        subset = sorted_data[:n]
        energies = [d["energy"] for d in subset]
        stable_count = sum(1 for d in subset if d["stable"])
        hit_count = sum(1 for d in subset if d["hit_target"])

        results[n] = {
            "n_selected": n,
            "n_total": total,
            "selection_ratio": round(n / total * 100, 2),
            "stability_rate": round(stable_count / n * 100, 4),
            "stable_count": stable_count,
            "hit_rate": round(hit_count / n * 100, 4),
            "mean_energy": round(float(np.mean(energies)), 6),
            "median_energy": round(float(np.median(energies)), 6),
            "p10_energy": round(float(np.percentile(energies, 10)), 6),
            "p90_energy": round(float(np.percentile(energies, 90)), 6),
            "best_energy": round(float(min(energies)), 6),
            "worst_energy": round(float(max(energies)), 6),
            # Efficiency: GPU-seconds per stable structure
            # Assume 1.58s per sample generation
            "gpu_seconds_per_stable": round(total * 1.58 / max(stable_count, 1), 2),
        }

    return results


def rejection_sampling_analysis(data, thresholds=None):
    """
    Rejection Sampling: keep only samples with energy below threshold.

    Returns dict mapping threshold -> {stability_rate, n_remaining, ...}
    """
    if thresholds is None:
        thresholds = [-6.0, -5.5, -5.0, -4.5, -4.0, -3.5, -3.0]

    total = len(data)

    results = {}
    for thresh in thresholds:
        subset = [d for d in data if d["energy"] <= thresh]
        n = len(subset)
        if n == 0:
            results[thresh] = {
                "threshold": thresh,
                "n_remaining": 0,
                "survival_rate": 0,
                "stability_rate": 0,
                "stable_count": 0,
            }
            continue

        energies = [d["energy"] for d in subset]
        stable_count = sum(1 for d in subset if d["stable"])
        hit_count = sum(1 for d in subset if d["hit_target"])

        results[thresh] = {
            "threshold": thresh,
            "n_remaining": n,
            "survival_rate": round(n / total * 100, 2),
            "stability_rate": round(stable_count / n * 100, 4),
            "stable_count": stable_count,
            "hit_rate": round(hit_count / n * 100, 4),
            "mean_energy": round(float(np.mean(energies)), 6),
            "median_energy": round(float(np.median(energies)), 6),
            "gpu_seconds_per_stable": round(total * 1.58 / max(stable_count, 1), 2),
        }

    return results


def generate_report(bon_results, rejection_results, out_dir, baseline_stats=None,
                    dpo_stats=None, target=""):
    """Generate comprehensive baseline comparison report."""
    md_path = out_dir / "baselines_report.md"

    with open(md_path, "w") as f:
        f.write("# Baseline Comparison Report: Best-of-N & Rejection Sampling\n\n")
        f.write(f"**Target**: {target}\n\n")

        # Best-of-N table
        f.write("## 1. Best-of-N Sampling\n\n")
        f.write("Select top-K samples by MatGL energy from the full baseline pool.\n\n")
        f.write("| K (selected) | Selection % | Stability Rate | Mean Energy | Median Energy | Stable Count | GPU-s/stable |\n")
        f.write("|-------------|------------|----------------|-------------|---------------|-------------|-------------|\n")
        for n, r in sorted(bon_results.items()):
            f.write(f"| {n:,} | {r['selection_ratio']}% | {r['stability_rate']}% | "
                    f"{r['mean_energy']:.4f} | {r['median_energy']:.4f} | "
                    f"{r['stable_count']:,} | {r['gpu_seconds_per_stable']:.1f}s |\n")

        # Rejection sampling table
        f.write("\n## 2. Rejection Sampling\n\n")
        f.write("Keep only samples below an energy threshold.\n\n")
        f.write("| Threshold (eV/atom) | Remaining | Survival % | Stability Rate | Stable Count | Mean Energy |\n")
        f.write("|--------------------|-----------|-----------:|----------------|-------------|------------|\n")
        for thresh, r in sorted(rejection_results.items()):
            f.write(f"| {thresh:.1f} | {r['n_remaining']:,} | {r['survival_rate']}% | "
                    f"{r['stability_rate']}% | {r['stable_count']:,} | "
                    f"{r.get('mean_energy', 'N/A')} |\n")

        # Comparison with DPO (if available)
        if dpo_stats:
            f.write("\n## 3. Comparison: DPO vs Baselines\n\n")
            f.write("| Method | Stability Rate | Mean Energy | Median Energy | Notes |\n")
            f.write("|--------|---------------|-------------|---------------|-------|\n")

            if baseline_stats:
                f.write(f"| Raw Baseline | {baseline_stats['stability_rate']}% | "
                        f"{baseline_stats['mean_energy']:.4f} | {baseline_stats['median_energy']:.4f} | "
                        f"No filtering |\n")

            f.write(f"| DPO Model | {dpo_stats['stability_rate']}% | "
                    f"{dpo_stats['mean_energy']:.4f} | {dpo_stats['median_energy']:.4f} | "
                    f"After DPO alignment |\n")

            # Find BoN that matches DPO stability rate
            dpo_sr = dpo_stats["stability_rate"]
            matching_bon = None
            for n, r in sorted(bon_results.items()):
                if r["stability_rate"] >= dpo_sr:
                    matching_bon = (n, r)
                    break
            if matching_bon:
                n, r = matching_bon
                f.write(f"| Best-of-{n:,} | {r['stability_rate']}% | "
                        f"{r['mean_energy']:.4f} | {r['median_energy']:.4f} | "
                        f"Matches DPO stability |\n")

            f.write("\n### Key Finding\n\n")
            if matching_bon:
                n, r = matching_bon
                ratio = n / dpo_stats.get("total", 50000) * 100
                f.write(f"To match DPO's stability rate of {dpo_sr}%, "
                        f"Best-of-N requires selecting the top {n:,} samples "
                        f"({ratio:.1f}% of the pool).\n")
                if dpo_sr > r["stability_rate"]:
                    f.write(f"\n**DPO outperforms Best-of-N** at equivalent sample size.\n")
                else:
                    f.write(f"\n**Best-of-N matches/exceeds DPO** with simple post-hoc selection.\n")

        f.write("\n## Plots\n\n")
        f.write("- `plots/bon_stability_curve.png` — Best-of-N stability vs K\n")
        f.write("- `plots/rejection_stability_curve.png` — Rejection sampling stability vs threshold\n")
        f.write("- `plots/method_comparison.png` — Combined comparison\n")

    print(f"Report: {md_path}")


def generate_plots(bon_results, rejection_results, out_dir,
                   baseline_stability=None, dpo_stability=None):
    """Generate comparison plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not available, skipping plots")
        return

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # 1. Best-of-N curve
    if bon_results:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        ns = sorted(bon_results.keys())
        stabilities = [bon_results[n]["stability_rate"] for n in ns]
        medians = [bon_results[n]["median_energy"] for n in ns]

        ax1.plot(ns, stabilities, "o-", color="#2196F3", linewidth=2, markersize=6)
        if baseline_stability is not None:
            ax1.axhline(y=baseline_stability, color="gray", linestyle="--",
                        alpha=0.5, label=f"Full Baseline ({baseline_stability}%)")
        if dpo_stability is not None:
            ax1.axhline(y=dpo_stability, color="red", linestyle="--",
                        alpha=0.7, label=f"DPO ({dpo_stability}%)")
        ax1.set_xlabel("K (samples selected)", fontsize=12)
        ax1.set_ylabel("Stability Rate (%)", fontsize=12)
        ax1.set_title("Best-of-N: Stability vs Selection Size", fontsize=14)
        ax1.set_xscale("log")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.plot(ns, medians, "s-", color="#4CAF50", linewidth=2, markersize=6)
        ax2.set_xlabel("K (samples selected)", fontsize=12)
        ax2.set_ylabel("Median Energy (eV/atom)", fontsize=12)
        ax2.set_title("Best-of-N: Median Energy vs Selection Size", fontsize=14)
        ax2.set_xscale("log")
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(plots_dir / "bon_stability_curve.png", dpi=150, bbox_inches="tight")
        plt.close()

    # 2. Rejection sampling curve
    if rejection_results:
        fig, ax = plt.subplots(figsize=(10, 6))
        thresholds = sorted(rejection_results.keys())
        stabilities = [rejection_results[t]["stability_rate"] for t in thresholds]
        survivals = [rejection_results[t]["survival_rate"] for t in thresholds]

        ax.plot(thresholds, stabilities, "o-", color="#2196F3", linewidth=2,
                markersize=6, label="Stability Rate")
        ax2 = ax.twinx()
        ax2.plot(thresholds, survivals, "s--", color="#FF9800", linewidth=2,
                 markersize=6, label="Survival Rate")

        ax.set_xlabel("Energy Threshold (eV/atom)", fontsize=12)
        ax.set_ylabel("Stability Rate (%)", fontsize=12, color="#2196F3")
        ax2.set_ylabel("Survival Rate (%)", fontsize=12, color="#FF9800")
        ax.set_title("Rejection Sampling: Stability vs Threshold", fontsize=14)
        ax.legend(loc="upper left")
        ax2.legend(loc="upper right")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(plots_dir / "rejection_stability_curve.png", dpi=150, bbox_inches="tight")
        plt.close()


def compute_stats(data):
    """Compute summary stats for a dataset."""
    energies = [d["energy"] for d in data]
    stable_count = sum(1 for d in data if d["stable"])
    hit_count = sum(1 for d in data if d["hit_target"])
    total = len(data)

    return {
        "total": total,
        "stability_rate": round(stable_count / max(total, 1) * 100, 4),
        "stable_count": stable_count,
        "hit_rate": round(hit_count / max(total, 1) * 100, 4),
        "mean_energy": round(float(np.mean(energies)), 6) if energies else 0,
        "median_energy": round(float(np.median(energies)), 6) if energies else 0,
    }


def main():
    ap = argparse.ArgumentParser(description="Best-of-N and Rejection Sampling baselines")
    ap.add_argument("--scores_csv", required=True, help="Baseline MatGL scores CSV")
    ap.add_argument("--ehull_csv", required=True, help="Baseline Ehull estimates CSV")
    ap.add_argument("--labels_csv", default=None, help="Baseline labels CSV")
    ap.add_argument("--target", default="LiFePO4", help="Target composition")
    ap.add_argument("--out_dir", required=True, help="Output directory")
    # DPO comparison (optional)
    ap.add_argument("--dpo_scores_csv", default=None, help="DPO scores CSV for comparison")
    ap.add_argument("--dpo_ehull_csv", default=None, help="DPO Ehull CSV for comparison")
    ap.add_argument("--dpo_labels_csv", default=None, help="DPO labels CSV for comparison")
    # Best-of-N config
    ap.add_argument("--bon_values", default="100,500,1000,2000,5000,10000,20000,50000",
                    help="Comma-separated N values for Best-of-N")
    # Rejection config
    ap.add_argument("--rejection_thresholds", default="-6.0,-5.5,-5.0,-4.5,-4.0,-3.5,-3.0",
                    help="Comma-separated energy thresholds for rejection sampling")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Parse config
    bon_values = [int(x) for x in args.bon_values.split(",")]
    rejection_thresholds = [float(x) for x in args.rejection_thresholds.split(",")]

    # Load baseline data
    print("Loading baseline data...")
    baseline_data, total_files = load_scored_data(
        args.scores_csv, args.ehull_csv, args.labels_csv, args.target
    )
    print(f"  Loaded {len(baseline_data)} scored samples (total files: {total_files})")
    baseline_stats = compute_stats(baseline_data)
    print(f"  Baseline stability: {baseline_stats['stability_rate']}%")

    # Best-of-N analysis
    print("\nRunning Best-of-N analysis...")
    bon_results = best_of_n_analysis(baseline_data, bon_values)
    for n, r in sorted(bon_results.items()):
        print(f"  Top-{n:>6,}: stability={r['stability_rate']:>7.3f}%, "
              f"median_e={r['median_energy']:.4f}")

    # Rejection sampling analysis
    print("\nRunning Rejection Sampling analysis...")
    rejection_results = rejection_sampling_analysis(baseline_data, rejection_thresholds)
    for t, r in sorted(rejection_results.items()):
        print(f"  Threshold {t:>5.1f}: n={r['n_remaining']:>6,}, "
              f"stability={r['stability_rate']:>7.3f}%, survive={r['survival_rate']:>5.1f}%")

    # Load DPO data if available
    dpo_stats = None
    if args.dpo_scores_csv and Path(args.dpo_scores_csv).exists():
        print("\nLoading DPO data for comparison...")
        dpo_data, _ = load_scored_data(
            args.dpo_scores_csv,
            args.dpo_ehull_csv or "",
            args.dpo_labels_csv,
            args.target
        )
        dpo_stats = compute_stats(dpo_data)
        print(f"  DPO stability: {dpo_stats['stability_rate']}%")

    # Save raw results
    with open(out_dir / "bon_results.json", "w") as f:
        json.dump({str(k): v for k, v in bon_results.items()}, f, indent=2)
    with open(out_dir / "rejection_results.json", "w") as f:
        json.dump({str(k): v for k, v in rejection_results.items()}, f, indent=2)
    if dpo_stats:
        with open(out_dir / "dpo_comparison.json", "w") as f:
            json.dump(dpo_stats, f, indent=2)

    # Generate plots
    print("\nGenerating plots...")
    generate_plots(
        bon_results, rejection_results, out_dir,
        baseline_stability=baseline_stats["stability_rate"],
        dpo_stability=dpo_stats["stability_rate"] if dpo_stats else None,
    )

    # Generate report
    print("Generating report...")
    generate_report(
        bon_results, rejection_results, out_dir,
        baseline_stats=baseline_stats, dpo_stats=dpo_stats,
        target=args.target,
    )

    print("\nDone!")


if __name__ == "__main__":
    main()
