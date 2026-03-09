#!/usr/bin/env python3
"""
Pair merging utilities for Phase 4 of the SFT+RL pipeline.

This module handles the dynamic allocation of pairs from multiple targets
for DPO training, ensuring exact pair count requirements are met.
"""

import json
import random
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any


def agent_log(log_path: Path, run_id: str, hypothesis_id: str, location: str,
              message: str, data: Dict[str, Any], session_id: str = "25e703"):
    """Write agent debug log entry.

    Args:
        log_path: Path to log file
        run_id: Run identifier
        hypothesis_id: Hypothesis identifier
        location: Code location
        message: Log message
        data: Structured data dictionary
        session_id: Session identifier
    """
    entry = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_pairs_from_targets(
    exp_dir: Path,
    targets: List[str],
    branch: str,
    pairs_filename: str = "pairs.jsonl"
) -> Dict[str, List[Dict]]:
    """Load pair data from multiple targets.

    Args:
        exp_dir: Experiment directory root
        targets: List of target names
        branch: Branch name (e.g., "lora64")
        pairs_filename: Name of pairs file

    Returns:
        Dictionary mapping target names to lists of pair records
    """
    per_target = {}

    for target in targets:
        pairs_file = exp_dir / target / f"sft_{branch}" / "pairs" / pairs_filename
        rows = []

        if pairs_file.exists():
            with open(pairs_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        if rows:
            per_target[target] = rows

    return per_target


def compute_allocation(
    per_target: Dict[str, List[Dict]],
    target_total: int,
    seed: int = 42
) -> Tuple[Dict[str, int], Dict[str, int], int]:
    """Compute dynamic per-target pair allocation.

    Distributes target_total pairs proportionally across available targets,
    with capacity correction to ensure exact total.

    Args:
        per_target: Dictionary of target -> pairs
        target_total: Total number of pairs required
        seed: Random seed for reproducibility

    Returns:
        Tuple of (counts, allocation, total_available)
        - counts: Available pairs per target
        - allocation: Final allocation per target
        - total_available: Total pairs available
    """
    rng = random.Random(seed)

    # Count available pairs per target
    counts = {t: len(v) for t, v in per_target.items()}
    total_available = sum(counts.values())

    if total_available < target_total:
        return counts, {}, total_available

    if not per_target:
        return {}, {}, 0

    # Dynamic split proportional to availability
    raw = {t: target_total * counts[t] / total_available for t in per_target}
    alloc = {t: int(raw[t]) for t in per_target}

    # Handle remainder
    remainder = target_total - sum(alloc.values())
    order = sorted(per_target.keys(), key=lambda t: (raw[t] - alloc[t]), reverse=True)

    for i in range(remainder):
        alloc[order[i % len(order)]] += 1

    # Capacity correction - ensure we don't exceed available pairs
    deficit = 0
    for target in list(alloc.keys()):
        if alloc[target] > counts[target]:
            deficit += alloc[target] - counts[target]
            alloc[target] = counts[target]

    # Redistribute deficit to targets with capacity
    if deficit > 0:
        grow = [t for t in alloc if alloc[t] < counts[t]]
        idx = 0
        while deficit > 0 and grow:
            target = grow[idx % len(grow)]
            if alloc[target] < counts[target]:
                alloc[target] += 1
                deficit -= 1
            idx += 1

    return counts, alloc, total_available


def merge_pairs(
    exp_dir: str,
    targets_csv: str,
    branch: str,
    target_total: int,
    seed: int,
    out_path: str,
    val_split: float = 0.1,
    log_path: Optional[str] = None,
    run_id: str = "pre-fix-1",
    session_id: str = "25e703"
) -> Dict[str, Any]:
    """Merge pairs from multiple targets for DPO training.

    This is the main entry point for Phase 4 pair merging.

    Args:
        exp_dir: Experiment directory path
        targets_csv: Comma-separated list of target names
        branch: Branch name
        target_total: Required total number of pairs
        seed: Random seed
        out_path: Output path for merged pairs JSONL
        val_split: Fraction of merged pairs to hold out for validation (0 to disable)
        log_path: Optional path for agent log
        run_id: Run identifier for logging
        session_id: Session identifier for logging

    Returns:
        Summary dictionary with merge statistics

    Raises:
        SystemExit: If insufficient pairs or allocation mismatch
    """
    exp_path = Path(exp_dir)
    targets = [t.strip() for t in targets_csv.split(",") if t.strip()]
    out_file = Path(out_path)

    # Setup logging
    if log_path:
        log_file = Path(log_path)
    else:
        log_file = Path.home() / ".cursor" / f"debug-{session_id}.log"

    def log(hid, location, message, data):
        agent_log(log_file, run_id, hid, location, message, data, session_id)

    # Load pairs from all targets
    per_target = load_pairs_from_targets(exp_path, targets, branch)

    if not per_target:
        log("H1", "pair_merge.py:merge_pairs", "No per-target pairs available for merge",
            {"branch": branch, "targets": targets})
        print("ERROR: no available pair files", file=sys.stderr)
        sys.exit(1)

    # Compute allocation
    counts, alloc, total_available = compute_allocation(per_target, target_total, seed)

    log("H1", "pair_merge.py:compute_allocation",
        "Pre-merge availability snapshot",
        {"branch": branch, "counts": counts, "total_available": total_available,
         "target_total": target_total})

    print(f"Available pairs by target: {counts} (total={total_available})")

    if total_available < target_total:
        log("H1", "pair_merge.py:compute_allocation",
            "Insufficient total_available before allocation",
            {"branch": branch, "counts": counts, "total_available": total_available,
             "target_total": target_total})
        print(f"ERROR: available pairs {total_available} < requested {target_total}", file=sys.stderr)
        sys.exit(2)

    if sum(alloc.values()) != target_total:
        log("H3", "pair_merge.py:compute_allocation",
            "Allocation sum mismatch after correction",
            {"branch": branch, "alloc": alloc, "sum_alloc": sum(alloc.values()),
             "target_total": target_total, "counts": counts})
        print("ERROR: failed to allocate exactly requested pairs", file=sys.stderr)
        sys.exit(3)

    log("H3", "pair_merge.py:compute_allocation",
        "Allocation computed successfully",
        {"branch": branch, "alloc": alloc, "target_total": target_total, "counts": counts})

    # Merge and shuffle
    rng = random.Random(seed)
    merged = []

    for target, n in alloc.items():
        rows = per_target[target]
        rng.shuffle(rows)
        chosen = rows[:n]

        # Add source target metadata
        for rec in chosen:
            rec["source_target"] = target

        merged.extend(chosen)

    # Final shuffle across all targets
    rng.shuffle(merged)

    # Split train/val before writing
    val_count = int(len(merged) * val_split) if val_split > 0 else 0
    val_pairs = merged[:val_count]
    train_pairs = merged[val_count:]

    # Write training output
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        for rec in train_pairs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Write validation output
    val_file = out_file.parent / "val_pairs.jsonl"
    if val_pairs:
        with open(val_file, "w", encoding="utf-8") as f:
            for rec in val_pairs:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"Validation pairs: {len(val_pairs)} -> {val_file}")

    # Write summary
    summary = {
        "requested_total_pairs": target_total,
        "available_pairs_by_target": counts,
        "allocated_pairs_by_target": alloc,
        "merged_pairs": len(merged),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "val_split": val_split,
    }

    summary_path = out_file.parent / "merge_pairs_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Allocated pairs by target: {alloc}")
    print(f"Wrote merged pairs: {len(train_pairs)} train + {len(val_pairs)} val -> {out_file}")

    return summary


def main():
    """Command-line entry point."""
    import argparse

    ap = argparse.ArgumentParser(description="Merge pairs from multiple targets")
    ap.add_argument("--exp_dir", required=True, help="Experiment directory")
    ap.add_argument("--targets", required=True, help="Comma-separated target names")
    ap.add_argument("--branch", required=True, help="Branch name")
    ap.add_argument("--target_total", type=int, required=True, help="Total pairs required")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    ap.add_argument("--out", required=True, help="Output path for merged pairs")
    ap.add_argument("--val_split", type=float, default=0.1,
                    help="Fraction of pairs to hold out for DPO validation (0 to disable)")
    ap.add_argument("--log_path", default=None, help="Path for agent log")
    ap.add_argument("--run_id", default="pre-fix-1", help="Run ID for logging")

    args = ap.parse_args()

    summary = merge_pairs(
        exp_dir=args.exp_dir,
        targets_csv=args.targets,
        branch=args.branch,
        target_total=args.target_total,
        seed=args.seed,
        out_path=args.out,
        val_split=args.val_split,
        log_path=args.log_path,
        run_id=args.run_id
    )

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
