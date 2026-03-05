#!/usr/bin/env python3
"""
Compute Novelty rate: fraction of stable generated structures that are NOT
found in the CrystaLLM training set.

Uses pymatgen StructureMatcher for approximate structure comparison.

Usage:
  python 37_compute_novelty.py \
    --gen_cif_dir outputs/exp/baseline/raw_cifs \
    --ehull_csv outputs/exp/baseline/scored/ehull_estimates.csv \
    --train_cif_dir /path/to/crystallm_training_cifs \
    --out_json outputs/exp/baseline/scored/novelty.json \
    --ehull_threshold 0.05

If --train_cif_dir is not provided or does not exist, novelty is reported as N/A.
"""
import argparse
import csv
import json
import os
from pathlib import Path

def main():
    ap = argparse.ArgumentParser(description="Compute novelty rate of generated structures")
    ap.add_argument("--gen_cif_dir", required=True, help="Directory of generated CIF files")
    ap.add_argument("--ehull_csv", required=True, help="Ehull estimates CSV (from 36_estimate_ehull.py)")
    ap.add_argument("--train_cif_dir", default=None,
                    help="Directory of CrystaLLM training CIF files (for novelty comparison)")
    ap.add_argument("--out_json", required=True, help="Output JSON with novelty stats")
    ap.add_argument("--ehull_threshold", type=float, default=0.05,
                    help="Ehull threshold for 'stable' classification")
    ap.add_argument("--ltol", type=float, default=0.2, help="StructureMatcher length tolerance")
    ap.add_argument("--stol", type=float, default=0.3, help="StructureMatcher site tolerance")
    ap.add_argument("--angle_tol", type=float, default=5.0, help="StructureMatcher angle tolerance")
    args = ap.parse_args()

    # 1. Identify stable generated structures
    stable_files = set()
    with open(args.ehull_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ehull_str = (row.get("ehull_proxy") or "").strip()
            if ehull_str:
                try:
                    if float(ehull_str) < args.ehull_threshold:
                        stable_files.add(row["file"])
                except ValueError:
                    pass

    print(f"Stable generated structures (Ehull < {args.ehull_threshold}): {len(stable_files)}")

    if not stable_files:
        result = {
            "stable_count": 0,
            "novel_count": 0,
            "novelty_rate": None,
            "note": "No stable structures found",
        }
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"No stable structures. Wrote: {out_path}")
        return

    # 2. Check training data availability
    if not args.train_cif_dir or not Path(args.train_cif_dir).exists():
        result = {
            "stable_count": len(stable_files),
            "novel_count": None,
            "novelty_rate": None,
            "note": "Training CIF directory not provided or not found. Novelty = N/A.",
            "train_cif_dir": args.train_cif_dir,
        }
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Training data not available. Novelty = N/A. Wrote: {out_path}")
        return

    # 3. Load training structures
    from pymatgen.core import Structure
    from pymatgen.analysis.structure_matcher import StructureMatcher

    matcher = StructureMatcher(ltol=args.ltol, stol=args.stol, angle_tol=args.angle_tol)

    train_dir = Path(args.train_cif_dir)
    train_cifs = sorted(train_dir.glob("*.cif"))
    print(f"Loading {len(train_cifs)} training structures...")

    train_structures = []
    for p in train_cifs:
        try:
            s = Structure.from_file(str(p))
            train_structures.append(s)
        except Exception:
            pass

    print(f"Loaded {len(train_structures)} valid training structures.")

    # 4. Compare each stable generated structure against training set
    gen_dir = Path(args.gen_cif_dir)
    novel_count = 0
    matched_count = 0
    error_count = 0

    for i, fname in enumerate(sorted(stable_files)):
        gen_path = gen_dir / fname
        if not gen_path.exists():
            error_count += 1
            continue

        try:
            gen_s = Structure.from_file(str(gen_path))
        except Exception:
            error_count += 1
            continue

        is_novel = True
        for train_s in train_structures:
            try:
                if matcher.fit(gen_s, train_s):
                    is_novel = False
                    break
            except Exception:
                continue

        if is_novel:
            novel_count += 1
        else:
            matched_count += 1

        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(stable_files)} (novel={novel_count}, matched={matched_count})")

    total_checked = novel_count + matched_count
    novelty_rate = novel_count / total_checked if total_checked > 0 else None

    result = {
        "stable_count": len(stable_files),
        "checked_count": total_checked,
        "novel_count": novel_count,
        "matched_count": matched_count,
        "error_count": error_count,
        "novelty_rate": round(novelty_rate, 4) if novelty_rate is not None else None,
        "matcher_params": {"ltol": args.ltol, "stol": args.stol, "angle_tol": args.angle_tol},
        "train_structures_loaded": len(train_structures),
    }

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"\nNovelty results:")
    print(f"  Stable: {len(stable_files)}, Checked: {total_checked}")
    print(f"  Novel: {novel_count}, Matched: {matched_count}")
    print(f"  Novelty rate: {novelty_rate:.2%}" if novelty_rate is not None else "  Novelty rate: N/A")
    print(f"  Wrote: {out_path}")


if __name__ == "__main__":
    main()
