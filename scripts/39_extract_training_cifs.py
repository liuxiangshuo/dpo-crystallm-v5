#!/usr/bin/env python3
"""
Extract CIF files from CrystaLLM benchmark CSV for novelty comparison.

CrystaLLM benchmark datasets (mp_20, mpts_52, etc.) store CIF content in CSV.
This script extracts them as individual .cif files for use with 37_compute_novelty.py.

Usage:
    python scripts/39_extract_training_cifs.py \
        --csv_dir ~/projects/crystallm-repro/external/CrystaLLM/resources/benchmarks/mp_20 \
        --out_dir data/training_cifs_mp20 \
        --splits train,val

    # Extract from multiple benchmarks:
    python scripts/39_extract_training_cifs.py \
        --csv_dir ~/projects/crystallm-repro/external/CrystaLLM/resources/benchmarks \
        --out_dir data/training_cifs_all \
        --recursive
"""

import argparse
import csv
import os
from pathlib import Path


def extract_cifs_from_csv(csv_path: Path, out_dir: Path, max_files: int = None):
    """Extract CIF content from a benchmark CSV file."""
    count = 0
    skipped = 0

    # Increase CSV field size limit
    csv.field_size_limit(10 * 1024 * 1024)  # 10 MB

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cif_content = row.get("cif", "").strip()
            mat_id = row.get("material_id", f"struct_{count}")

            if not cif_content:
                skipped += 1
                continue

            out_file = out_dir / f"{mat_id}.cif"
            with open(out_file, "w", encoding="utf-8") as out:
                out.write(cif_content)

            count += 1
            if max_files and count >= max_files:
                break

    return count, skipped


def main():
    ap = argparse.ArgumentParser(description="Extract CIF files from CrystaLLM benchmark CSV")
    ap.add_argument("--csv_dir", required=True,
                    help="Directory containing train.csv, val.csv, test.csv")
    ap.add_argument("--out_dir", required=True, help="Output directory for CIF files")
    ap.add_argument("--splits", default="train,val",
                    help="Comma-separated splits to extract (default: train,val)")
    ap.add_argument("--recursive", action="store_true",
                    help="Recursively search subdirectories for CSV files")
    ap.add_argument("--max_files", type=int, default=None,
                    help="Maximum files to extract per CSV")
    args = ap.parse_args()

    csv_dir = Path(args.csv_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = [s.strip() for s in args.splits.split(",")]
    total_extracted = 0
    total_skipped = 0

    if args.recursive:
        # Find all CSV files in subdirectories
        csv_files = []
        for split in splits:
            csv_files.extend(csv_dir.rglob(f"{split}.csv"))
    else:
        csv_files = [csv_dir / f"{split}.csv" for split in splits]

    for csv_path in csv_files:
        if not csv_path.exists():
            print(f"Skipping (not found): {csv_path}")
            continue

        print(f"Extracting from: {csv_path}")
        count, skipped = extract_cifs_from_csv(csv_path, out_dir, args.max_files)
        total_extracted += count
        total_skipped += skipped
        print(f"  Extracted: {count}, Skipped: {skipped}")

    print(f"\nTotal extracted: {total_extracted} CIF files -> {out_dir}")
    print(f"Total skipped: {total_skipped}")


if __name__ == "__main__":
    main()
