#!/usr/bin/env python3
"""
Pipeline utility functions for SFT+RL experiments.

This module extracts commonly used inline Python functions from the pipeline
shell script into a proper Python module for better maintainability and testing.
"""

import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


# =============================================================================
# Logging utilities
# =============================================================================

def debug_log(log_dir: str, run_id: str, hypothesis_id: str, location: str,
              message: str, data: Dict[str, Any], session_id: str = "25e703"):
    """Write structured debug log entry to JSONL file.

    Args:
        log_dir: Directory to write log files
        run_id: Run identifier
        hypothesis_id: Hypothesis identifier
        location: Code location string (file:line)
        message: Human-readable message
        data: Dictionary of structured data
        session_id: Session identifier for log file naming
    """
    log_path = Path(log_dir) / f"debug-{session_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    entry = {
        "sessionId": session_id,
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# =============================================================================
# CSV and data counting utilities
# =============================================================================

def count_csv_rows(csv_path: str) -> int:
    """Count rows in a CSV file (excluding header).

    Args:
        csv_path: Path to CSV file

    Returns:
        Number of data rows (excluding header)
    """
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            return sum(1 for _ in csv.DictReader(f))
    except Exception:
        return 0


def count_scored_rows(scores_csv: str) -> int:
    """Count non-empty MatGL score rows (excluding header/failed rows).

    Args:
        scores_csv: Path to ehull_scores.csv file

    Returns:
        Number of rows with valid score_e_per_atom values
    """
    try:
        with open(scores_csv, "r", encoding="utf-8") as f:
            return sum(
                1 for row in csv.DictReader(f)
                if (row.get("score_e_per_atom") or "").strip()
            )
    except Exception:
        return 0


def count_cif_files(cif_dir: str) -> int:
    """Count CIF files under a directory.

    Args:
        cif_dir: Directory path to search

    Returns:
        Number of .cif files
    """
    try:
        return sum(1 for _ in Path(cif_dir).glob("*.cif"))
    except Exception:
        return 0


# =============================================================================
# Score validation utilities
# =============================================================================

def check_score_fail_rate(
    scored_dir: str,
    label: str,
    mode: str = "warn",
    threshold: float = 0.05,
    verbose: bool = True
) -> Tuple[bool, float, int, int]:
    """Check failed-score rate using scores_failed.csv and ehull_scores.csv.

    Args:
        scored_dir: Directory containing scored CSV files
        label: Label for logging (e.g., "baseline/LiFePO4")
        mode: One of "off", "warn", "fail" - determines action on threshold breach
        threshold: Failure rate threshold (0.05 = 5%)
        verbose: Whether to print status messages

    Returns:
        Tuple of (passed, rate, failed_count, total_count)
        - passed: True if check passed (rate <= threshold or mode != "fail")
        - rate: Calculated failure rate
        - failed_count: Number of failed scores
        - total_count: Total number of scores

    Raises:
        SystemExit: If mode="fail" and rate > threshold
    """
    scores_path = Path(scored_dir) / "ehull_scores.csv"
    failed_path = Path(scored_dir) / "scores_failed.csv"

    total = 0
    failed = 0

    try:
        with open(scores_path, "r", encoding="utf-8") as f:
            total = sum(1 for _ in csv.DictReader(f))
    except Exception as e:
        if verbose:
            print(f"  WARNING [{label}]: Could not read ehull_scores.csv for fail-rate check: {e}")
        return True, 0.0, 0, 0

    if failed_path.exists():
        try:
            with open(failed_path, "r", encoding="utf-8") as f:
                failed = sum(1 for _ in csv.DictReader(f))
        except Exception as e:
            if verbose:
                print(f"  WARNING [{label}]: Could not read scores_failed.csv: {e}")

    rate = (failed / total) if total > 0 else 0.0

    if verbose:
        print(f"  Score fail-rate [{label}]: {failed}/{total} ({rate:.2%}), mode={mode}, threshold={threshold:.2%}")

    passed = True
    if rate > threshold:
        if mode == "fail":
            print(f"ERROR [{label}]: Score fail-rate {rate:.2%} exceeds threshold {threshold:.2%}")
            passed = False
        elif mode == "warn":
            print(f"  WARNING [{label}]: Score fail-rate {rate:.2%} exceeds threshold {threshold:.2%}")

    return passed, rate, failed, total


def check_reward_spread(
    scored_dir: str,
    label: str,
    min_std: float = 0.05,
    verbose: bool = True
) -> Tuple[bool, float, float, float]:
    """Check reward spread after composite reward scoring.

    Args:
        scored_dir: Directory containing composite_reward_summary.json
        label: Label for logging
        min_std: Minimum acceptable standard deviation
        verbose: Whether to print status messages

    Returns:
        Tuple of (ok, std, r_geom_mean, gate_fail_rate)
    """
    summary_path = Path(scored_dir) / "composite_reward_summary.json"

    try:
        with open(summary_path, "r") as f:
            d = json.load(f)

        std = d["r_total"]["std"]
        r_geom = d.get("r_geom", {}).get("mean", 0)
        gate_fail_rate = d.get("gate_failure_rate", 0)

        ok = std >= min_std

        if verbose:
            if not ok:
                print(f"  WARNING [{label}]: R_total std={std:.4f} < {min_std} - reward has almost no spread!")
            else:
                print(f"  Reward OK [{label}]: R_total std={std:.4f} r_geom={r_geom:.3f} gate_fail={gate_fail_rate:.3f}")

        return ok, std, r_geom, gate_fail_rate

    except Exception as e:
        if verbose:
            print(f"  WARNING [{label}]: Could not read reward summary: {e}")
        return False, 0.0, 0.0, 0.0


# =============================================================================
# CSV merging utilities
# =============================================================================

def merge_eval_csv(scored_dir: str, conda_env: Optional[str] = None) -> bool:
    """Merge labels.csv + ehull_scores.csv -> eval.csv.

    Args:
        scored_dir: Directory containing scored outputs
        conda_env: Optional conda environment name to run in (not used in Python version)

    Returns:
        True if successful, False otherwise
    """
    scored_path = Path(scored_dir)
    labels_path = scored_path / "labels.csv"
    scores_path = scored_path / "ehull_scores.csv"
    out_path = scored_path / "eval.csv"

    try:
        # Load labels
        labels = {}
        with open(labels_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                labels[row["file"]] = row

        # Load scores
        scores = {}
        with open(scores_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                v = row.get("score_e_per_atom", "").strip()
                if v:
                    scores[row["file"]] = v

        # Write merged output
        fieldnames = ["file", "valid", "formula", "target", "hit_target",
                      "score_e_per_atom", "error"]

        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for file, lbl in labels.items():
                row = lbl.copy()
                row["score_e_per_atom"] = scores.get(file, "")
                writer.writerow(row)

        print(f"  eval.csv: {len(labels)} labels, {len(scores)} scores merged")
        return True

    except Exception as e:
        print(f"WARNING: Failed to merge eval.csv in {scored_dir}: {e}")
        return False


# =============================================================================
# Visualization utilities
# =============================================================================

def warn_if_no_visualizations(viz_dir: str) -> bool:
    """Warn if Phase 6 produced no rendered images.

    Args:
        viz_dir: Visualization output directory

    Returns:
        True if images found, False if no images
    """
    viz_path = Path(viz_dir)

    if not viz_path.exists():
        print(f"WARNING: Visualization output dir missing: {viz_dir}")
        return False

    exts = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    n = sum(1 for p in viz_path.rglob("*") if p.suffix.lower() in exts)

    if n == 0:
        print(f"WARNING: Phase 6 rendered 0 images under {viz_dir}. Check input ranking files or rendering backend.")
        return False
    else:
        print(f"Phase 6 rendered images: {n}")
        return True


# =============================================================================
# Conda utilities
# =============================================================================

def get_conda_base() -> Optional[str]:
    """Get conda base directory.

    Returns:
        Path to conda base directory, or None if not found
    """
    # Try common locations
    home = Path.home()
    candidates = [
        home / "miniconda3",
        home / "anaconda3",
        home / "conda",
    ]

    for cand in candidates:
        if cand.exists():
            return str(cand)

    # Try conda info command
    try:
        import subprocess
        result = subprocess.run(
            ["conda", "info", "--base"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def get_conda_sh_path() -> Optional[str]:
    """Get path to conda.sh for shell initialization.

    Returns:
        Path to conda.sh if found, None otherwise
    """
    base = get_conda_base()
    if base:
        conda_sh = Path(base) / "etc" / "profile.d" / "conda.sh"
        if conda_sh.exists():
            return str(conda_sh)
    return None


# =============================================================================
# Main entry points for command-line usage
# =============================================================================

def main():
    """Main entry point for command-line usage."""
    import argparse

    ap = argparse.ArgumentParser(description="Pipeline utilities")
    subparsers = ap.add_subparsers(dest="command", help="Command to run")

    # Count rows command
    count_parser = subparsers.add_parser("count_csv", help="Count CSV rows")
    count_parser.add_argument("--csv", required=True, help="Path to CSV file")
    count_parser.add_argument("--type", choices=["rows", "scored", "cifs"],
                             default="rows", help="Type of count")

    # Check score fail rate command
    failrate_parser = subparsers.add_parser("check_fail_rate", help="Check score fail rate")
    failrate_parser.add_argument("--scored_dir", required=True)
    failrate_parser.add_argument("--label", required=True)
    failrate_parser.add_argument("--mode", default="warn")
    failrate_parser.add_argument("--threshold", type=float, default=0.05)

    # Check reward spread command
    spread_parser = subparsers.add_parser("check_reward_spread", help="Check reward spread")
    spread_parser.add_argument("--scored_dir", required=True)
    spread_parser.add_argument("--label", required=True)

    # Merge eval CSV command
    merge_parser = subparsers.add_parser("merge_eval", help="Merge eval CSV")
    merge_parser.add_argument("--scored_dir", required=True)

    # Check visualizations command
    viz_parser = subparsers.add_parser("check_viz", help="Check visualizations")
    viz_parser.add_argument("--viz_dir", required=True)

    # Debug log command
    log_parser = subparsers.add_parser("debug_log", help="Write debug log")
    log_parser.add_argument("--log_dir", required=True)
    log_parser.add_argument("--run_id", required=True)
    log_parser.add_argument("--hypothesis_id", required=True)
    log_parser.add_argument("--location", required=True)
    log_parser.add_argument("--message", required=True)
    log_parser.add_argument("--data", default="{}")

    args = ap.parse_args()

    if args.command == "count_csv":
        if args.type == "rows":
            print(count_csv_rows(args.csv))
        elif args.type == "scored":
            print(count_scored_rows(args.csv))
        elif args.type == "cifs":
            print(count_cif_files(args.csv))

    elif args.command == "check_fail_rate":
        passed, rate, failed, total = check_score_fail_rate(
            args.scored_dir, args.label, args.mode, args.threshold
        )
        sys.exit(0 if passed else 1)

    elif args.command == "check_reward_spread":
        ok, std, r_geom, gate_fail = check_reward_spread(args.scored_dir, args.label)
        sys.exit(0 if ok else 1)

    elif args.command == "merge_eval":
        success = merge_eval_csv(args.scored_dir)
        sys.exit(0 if success else 1)

    elif args.command == "check_viz":
        ok = warn_if_no_visualizations(args.viz_dir)
        sys.exit(0 if ok else 1)

    elif args.command == "debug_log":
        data = json.loads(args.data)
        debug_log(args.log_dir, args.run_id, args.hypothesis_id,
                  args.location, args.message, data)


if __name__ == "__main__":
    main()
