#!/usr/bin/env python3
"""
Phase 1.3: Preference Pair Quality Analysis

Analyzes the quality and characteristics of constructed preference pairs:
  - Energy gap distribution histogram
  - Token length vs. energy quality correlation
  - Trimmed vs. untrimmed strategy comparison
  - Prompt coverage statistics
  - Pair diversity metrics

Usage:
    python scripts/43_analyze_pair_quality.py \
        --pairs_jsonl outputs/exp_final_50k/pairs/pairs.jsonl \
        --scores_csv outputs/exp_final_50k/baseline/scored/ehull_scores.csv \
        --out_dir reports/pair_quality_analysis

    # Compare two pair strategies:
    python scripts/43_analyze_pair_quality.py \
        --pairs_jsonl outputs/exp1/pairs/pairs.jsonl \
        --pairs_jsonl_compare outputs/exp2/pairs/pairs.jsonl \
        --labels "trimmed" "untrimmed" \
        --out_dir reports/pair_quality_comparison
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


def load_pairs(jsonl_path: str):
    """Load preference pairs from JSONL file."""
    pairs = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def compute_pair_stats(pairs: list) -> dict:
    """Compute detailed statistics about preference pairs."""
    gaps = []
    chosen_energies = []
    rejected_energies = []
    chosen_lengths = []
    rejected_lengths = []
    prompts = Counter()
    scenarios = Counter()

    for p in pairs:
        # Energy gap (support both field naming conventions)
        ce_key = "chosen_energy" if "chosen_energy" in p else "chosen_score"
        re_key = "rejected_energy" if "rejected_energy" in p else "rejected_score"
        if ce_key in p and re_key in p:
            try:
                ce = float(p[ce_key])
                re_ = float(p[re_key])
                gap = re_ - ce  # positive = chosen is lower energy (better)
                gaps.append(gap)
                chosen_energies.append(ce)
                rejected_energies.append(re_)
            except (ValueError, TypeError):
                pass

        # Token lengths
        if "chosen_tokens" in p:
            chosen_lengths.append(int(p["chosen_tokens"]))
        elif "chosen" in p:
            chosen_lengths.append(len(p["chosen"].split()))  # rough estimate

        if "rejected_tokens" in p:
            rejected_lengths.append(int(p["rejected_tokens"]))
        elif "rejected" in p:
            rejected_lengths.append(len(p["rejected"].split()))

        # Prompt tracking
        prompt = p.get("prompt", "unknown")
        prompts[prompt] += 1

        # Scenario tracking
        scenario = p.get("scenario", "A")
        scenarios[str(scenario)] += 1

    gaps = np.array(gaps) if gaps else np.array([])
    chosen_e = np.array(chosen_energies) if chosen_energies else np.array([])
    rejected_e = np.array(rejected_energies) if rejected_energies else np.array([])
    chosen_len = np.array(chosen_lengths) if chosen_lengths else np.array([])
    rejected_len = np.array(rejected_lengths) if rejected_lengths else np.array([])

    stats = {
        "total_pairs": len(pairs),
        "unique_prompts": len(prompts),
        "scenario_distribution": dict(scenarios),
        "pairs_per_prompt": {
            "mean": float(np.mean(list(prompts.values()))) if prompts else 0,
            "min": min(prompts.values()) if prompts else 0,
            "max": max(prompts.values()) if prompts else 0,
            "std": float(np.std(list(prompts.values()))) if prompts else 0,
        },
    }

    if len(gaps) > 0:
        stats["energy_gap"] = {
            "mean": float(gaps.mean()),
            "median": float(np.median(gaps)),
            "std": float(gaps.std()),
            "min": float(gaps.min()),
            "max": float(gaps.max()),
            "p10": float(np.percentile(gaps, 10)),
            "p25": float(np.percentile(gaps, 25)),
            "p75": float(np.percentile(gaps, 75)),
            "p90": float(np.percentile(gaps, 90)),
        }
        stats["chosen_energy"] = {
            "mean": float(chosen_e.mean()),
            "median": float(np.median(chosen_e)),
            "std": float(chosen_e.std()),
        }
        stats["rejected_energy"] = {
            "mean": float(rejected_e.mean()),
            "median": float(np.median(rejected_e)),
            "std": float(rejected_e.std()),
        }

    if len(chosen_len) > 0:
        stats["chosen_token_length"] = {
            "mean": float(chosen_len.mean()),
            "median": float(np.median(chosen_len)),
            "std": float(chosen_len.std()),
            "min": int(chosen_len.min()),
            "max": int(chosen_len.max()),
        }
    if len(rejected_len) > 0:
        stats["rejected_token_length"] = {
            "mean": float(rejected_len.mean()),
            "median": float(np.median(rejected_len)),
            "std": float(rejected_len.std()),
            "min": int(rejected_len.min()),
            "max": int(rejected_len.max()),
        }

    return stats, gaps, chosen_e, rejected_e, chosen_len, rejected_len


def generate_plots(stats, gaps, chosen_e, rejected_e, chosen_len, rejected_len,
                   out_dir: Path, label: str = ""):
    """Generate analysis plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not available, skipping plots")
        return

    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{label}" if label else ""

    # 1. Energy gap distribution
    if len(gaps) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(gaps, bins=100, alpha=0.7, color="#2196F3", edgecolor="white")
        ax.axvline(x=np.median(gaps), color="red", linestyle="--",
                   label=f"Median: {np.median(gaps):.3f} eV/atom")
        ax.axvline(x=np.mean(gaps), color="orange", linestyle="--",
                   label=f"Mean: {np.mean(gaps):.3f} eV/atom")
        ax.set_xlabel("Energy Gap (rejected - chosen, eV/atom)", fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.set_title(f"Preference Pair Energy Gap Distribution{f' ({label})' if label else ''}", fontsize=14)
        ax.legend(fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(plots_dir / f"gap_distribution{suffix}.png", dpi=150, bbox_inches="tight")
        plt.close()

    # 2. Chosen vs Rejected energy scatter
    if len(chosen_e) > 0 and len(rejected_e) > 0:
        fig, ax = plt.subplots(figsize=(8, 8))
        # Random subsample for large datasets
        n = min(5000, len(chosen_e))
        idx = np.random.choice(len(chosen_e), n, replace=False)
        ax.scatter(chosen_e[idx], rejected_e[idx], alpha=0.1, s=5, color="#4CAF50")
        lims = [min(chosen_e.min(), rejected_e.min()), max(chosen_e.max(), rejected_e.max())]
        # Clip extreme values for better visualization
        lims = [max(lims[0], -8), min(lims[1], 10)]
        ax.plot(lims, lims, "r--", alpha=0.5, label="y = x (no preference)")
        ax.set_xlabel("Chosen Energy (eV/atom)", fontsize=12)
        ax.set_ylabel("Rejected Energy (eV/atom)", fontsize=12)
        ax.set_title("Chosen vs Rejected Energy", fontsize=14)
        ax.set_xlim(lims)
        ax.set_ylim(lims)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(plots_dir / f"chosen_vs_rejected{suffix}.png", dpi=150, bbox_inches="tight")
        plt.close()

    # 3. Token length distributions
    if len(chosen_len) > 0:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(chosen_len, bins=50, alpha=0.6, label="Chosen", color="#2196F3")
        if len(rejected_len) > 0:
            ax.hist(rejected_len, bins=50, alpha=0.6, label="Rejected", color="#FF5722")
        ax.set_xlabel("Token Length", fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.set_title("Token Length Distribution", fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(plots_dir / f"token_length_dist{suffix}.png", dpi=150, bbox_inches="tight")
        plt.close()

    # 4. Token length vs energy (correlation)
    if len(chosen_len) > 0 and len(chosen_e) > 0 and len(chosen_len) == len(chosen_e):
        fig, ax = plt.subplots(figsize=(10, 6))
        n = min(5000, len(chosen_len))
        idx = np.random.choice(len(chosen_len), n, replace=False)
        ax.scatter(chosen_len[idx], chosen_e[idx], alpha=0.1, s=5, color="#2196F3", label="Chosen")
        if len(rejected_len) > 0 and len(rejected_e) > 0 and len(rejected_len) == len(rejected_e):
            idx2 = np.random.choice(len(rejected_len), min(n, len(rejected_len)), replace=False)
            ax.scatter(rejected_len[idx2], rejected_e[idx2], alpha=0.1, s=5, color="#FF5722", label="Rejected")
        ax.set_xlabel("Token Length", fontsize=12)
        ax.set_ylabel("Energy (eV/atom)", fontsize=12)
        ax.set_title("Token Length vs Energy Correlation", fontsize=14)
        ax.legend()
        ax.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(plots_dir / f"token_vs_energy{suffix}.png", dpi=150, bbox_inches="tight")
        plt.close()


def generate_report(stats: dict, out_dir: Path, label: str = "",
                    compare_stats: dict = None, compare_label: str = ""):
    """Generate markdown analysis report."""
    md_path = out_dir / "pair_quality_report.md"
    with open(md_path, "w") as f:
        f.write("# Preference Pair Quality Analysis Report\n\n")

        if label:
            f.write(f"**Dataset**: {label}\n\n")

        f.write("## Overview\n\n")
        f.write(f"| Metric | Value |\n")
        f.write(f"|--------|-------|\n")
        f.write(f"| Total pairs | {stats['total_pairs']:,} |\n")
        f.write(f"| Unique prompts | {stats['unique_prompts']} |\n")
        f.write(f"| Mean pairs/prompt | {stats['pairs_per_prompt']['mean']:.1f} |\n")
        f.write(f"| Scenario distribution | {stats['scenario_distribution']} |\n")
        f.write("\n")

        if "energy_gap" in stats:
            eg = stats["energy_gap"]
            f.write("## Energy Gap Statistics\n\n")
            f.write("| Statistic | Value (eV/atom) |\n")
            f.write("|-----------|----------------|\n")
            for k in ["mean", "median", "std", "min", "max", "p10", "p25", "p75", "p90"]:
                f.write(f"| {k.upper()} | {eg[k]:.6f} |\n")
            f.write("\n")

            f.write("## Energy Statistics\n\n")
            f.write("| | Chosen | Rejected |\n")
            f.write("|--|--------|----------|\n")
            ce = stats["chosen_energy"]
            re_ = stats["rejected_energy"]
            for k in ["mean", "median", "std"]:
                f.write(f"| {k.capitalize()} | {ce[k]:.4f} | {re_[k]:.4f} |\n")
            f.write("\n")

        if "chosen_token_length" in stats:
            f.write("## Token Length Statistics\n\n")
            f.write("| | Chosen | Rejected |\n")
            f.write("|--|--------|----------|\n")
            ct = stats["chosen_token_length"]
            rt = stats.get("rejected_token_length", {})
            for k in ["mean", "median", "std", "min", "max"]:
                cv = ct.get(k, "N/A")
                rv = rt.get(k, "N/A")
                cv_str = f"{cv:.1f}" if isinstance(cv, float) else str(cv)
                rv_str = f"{rv:.1f}" if isinstance(rv, float) else str(rv)
                f.write(f"| {k.capitalize()} | {cv_str} | {rv_str} |\n")
            f.write("\n")

        # Comparison section
        if compare_stats:
            f.write(f"## Strategy Comparison: {label} vs {compare_label}\n\n")
            f.write("| Metric | {label} | {compare_label} |\n")
            f.write("|--------|---------|----------------|\n")
            f.write(f"| Total pairs | {stats['total_pairs']:,} | {compare_stats['total_pairs']:,} |\n")
            if "energy_gap" in stats and "energy_gap" in compare_stats:
                eg1 = stats["energy_gap"]
                eg2 = compare_stats["energy_gap"]
                f.write(f"| Mean gap | {eg1['mean']:.4f} | {eg2['mean']:.4f} |\n")
                f.write(f"| Median gap | {eg1['median']:.4f} | {eg2['median']:.4f} |\n")
                f.write(f"| Std gap | {eg1['std']:.4f} | {eg2['std']:.4f} |\n")
            f.write("\n")

        f.write("## Plots\n\n")
        f.write("- `plots/gap_distribution.png` — Energy gap histogram\n")
        f.write("- `plots/chosen_vs_rejected.png` — Chosen vs rejected scatter\n")
        f.write("- `plots/token_length_dist.png` — Token length distribution\n")
        f.write("- `plots/token_vs_energy.png` — Token length vs energy correlation\n")

    print(f"Report: {md_path}")


def main():
    ap = argparse.ArgumentParser(description="Preference Pair Quality Analysis")
    ap.add_argument("--pairs_jsonl", required=True, help="Primary JSONL pairs file")
    ap.add_argument("--pairs_jsonl_compare", default=None,
                    help="Optional second JSONL for comparison")
    ap.add_argument("--labels", nargs=2, default=["primary", "comparison"],
                    help="Labels for the two datasets")
    ap.add_argument("--scores_csv", default=None,
                    help="Optional scores CSV for additional context")
    ap.add_argument("--out_dir", required=True, help="Output directory for report and plots")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    np.random.seed(args.seed)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading pairs from {args.pairs_jsonl}...")
    pairs = load_pairs(args.pairs_jsonl)
    print(f"  Loaded {len(pairs)} pairs")

    print("Computing statistics...")
    stats, gaps, chosen_e, rejected_e, chosen_len, rejected_len = compute_pair_stats(pairs)

    # Save raw stats
    with open(out_dir / "pair_stats_detailed.json", "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Stats saved to {out_dir}/pair_stats_detailed.json")

    # Generate plots
    print("Generating plots...")
    generate_plots(stats, gaps, chosen_e, rejected_e, chosen_len, rejected_len,
                   out_dir, label=args.labels[0])

    # Comparison
    compare_stats = None
    if args.pairs_jsonl_compare:
        print(f"\nLoading comparison pairs from {args.pairs_jsonl_compare}...")
        pairs2 = load_pairs(args.pairs_jsonl_compare)
        print(f"  Loaded {len(pairs2)} pairs")
        compare_stats, gaps2, ce2, re2, cl2, rl2 = compute_pair_stats(pairs2)
        generate_plots(compare_stats, gaps2, ce2, re2, cl2, rl2,
                       out_dir, label=args.labels[1])
        with open(out_dir / f"pair_stats_{args.labels[1]}.json", "w") as f:
            json.dump(compare_stats, f, indent=2)

    # Generate report
    print("Generating report...")
    generate_report(stats, out_dir, label=args.labels[0],
                    compare_stats=compare_stats, compare_label=args.labels[1])

    print("\nDone!")


if __name__ == "__main__":
    main()
