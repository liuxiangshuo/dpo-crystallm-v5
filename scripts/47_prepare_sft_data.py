#!/usr/bin/env python3
"""
Prepare SFT training data by selecting stable CIF structures from baseline
generation and converting them to a JSONL training file.

Usage:
  python 47_prepare_sft_data.py \
    --ehull_csv outputs/exp_final_50k/baseline/scored/ehull_estimates.csv \
    --cif_dir outputs/exp_final_50k/baseline/raw_cifs \
    --pkg_dir ~/projects/crystallm-repro/external/CrystaLLM/crystallm \
    --out_jsonl outputs/exp_sft_stable/sft_data.jsonl \
    --ehull_threshold 0.05 \
    --max_tokens 1024
"""
import argparse
import csv
import json
import os
import re
import sys
import types
import importlib.util
import statistics
from pathlib import Path
from collections import Counter


def load_module(path: Path, name: str):
    """Dynamically load a Python module from file or .pyc."""
    if path.exists():
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    import marshal
    pyc_dir = path.parent / "__pycache__"
    if pyc_dir.exists():
        pyc_files = list(pyc_dir.glob(f"{path.name.split('.')[0]}*.pyc"))
        if pyc_files:
            with open(pyc_files[0], "rb") as f:
                f.read(16)
                code = marshal.load(f)
                mod = types.ModuleType(name)
                mod.__file__ = str(path)
                exec(code, mod.__dict__)
                return mod
    raise FileNotFoundError(f"Could not find {path} or .pyc fallback")


def load_tokenizer(pkg_dir: Path):
    """Load CIFTokenizer from CrystaLLM package."""
    tok_mod = load_module(pkg_dir / "_tokenizer.py", "tok")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    return tok_mod.CIFTokenizer()


def _load_stable_files(ehull_csv: str, ehull_threshold: float) -> list:
    """Load stable file list from one ehull CSV."""
    stable = []
    total = 0
    with open(ehull_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            total += 1
            ehull_str = (row.get("ehull_proxy") or "").strip()
            if ehull_str:
                try:
                    if float(ehull_str) < ehull_threshold:
                        stable.append(row["file"])
                except ValueError:
                    pass
    return stable, total


def main():
    ap = argparse.ArgumentParser(description="Prepare SFT training data from stable CIFs")
    ap.add_argument("--ehull_csv", required=True,
                    help="Ehull estimates CSV (from 36_estimate_ehull.py). "
                         "Supports comma-separated list for multi-composition merging.")
    ap.add_argument("--cif_dir", required=True,
                    help="Directory of generated CIF files. "
                         "Supports comma-separated list (one per ehull_csv, same order).")
    ap.add_argument("--pkg_dir", required=True, help="CrystaLLM package dir (for tokenizer)")
    ap.add_argument("--out_jsonl", required=True, help="Output JSONL for SFT training")
    ap.add_argument("--ehull_threshold", type=float, default=0.05,
                    help="Ehull threshold for stable classification")
    ap.add_argument("--max_tokens", type=int, default=1024,
                    help="Maximum token length (sequences longer are dropped)")
    ap.add_argument("--val_split", type=float, default=0.1,
                    help="Fraction of data to hold out for validation (0 to disable)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    out_path = Path(args.out_jsonl)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Support comma-separated multi-composition inputs
    ehull_csvs = [p.strip() for p in args.ehull_csv.split(",") if p.strip()]
    cif_dirs = [p.strip() for p in args.cif_dir.split(",") if p.strip()]

    # If only one cif_dir given for multiple ehull_csvs, repeat it
    if len(cif_dirs) == 1 and len(ehull_csvs) > 1:
        cif_dirs = cif_dirs * len(ehull_csvs)

    if len(ehull_csvs) != len(cif_dirs):
        print(f"ERROR: Number of ehull_csvs ({len(ehull_csvs)}) must match "
              f"cif_dirs ({len(cif_dirs)})")
        sys.exit(1)

    # Preflight: verify all requested inputs exist before processing.
    missing_ehull = []
    missing_cif_dirs = []
    for ehull_csv, cif_dir_str in zip(ehull_csvs, cif_dirs):
        ehull_path = Path(os.path.expanduser(ehull_csv))
        cif_dir = Path(os.path.expanduser(cif_dir_str))
        if not ehull_path.exists():
            missing_ehull.append(str(ehull_path))
        if not cif_dir.exists():
            missing_cif_dirs.append(str(cif_dir))
    if missing_ehull:
        print("ERROR: Missing ehull CSV inputs:")
        for p in missing_ehull:
            print(f"  - {p}")
        sys.exit(1)
    if missing_cif_dirs:
        print("ERROR: Missing CIF directories:")
        for p in missing_cif_dirs:
            print(f"  - {p}")
        sys.exit(1)

    # ---- Step 1: Identify stable structures from all sources ----
    # Returns list of (file, cif_dir) tuples
    stable_entries = []  # (filename, cif_dir_path)
    grand_total = 0

    for ehull_csv, cif_dir_str in zip(ehull_csvs, cif_dirs):
        cif_dir = Path(os.path.expanduser(cif_dir_str))
        print(f"Reading ehull estimates from {ehull_csv}")
        stable, total = _load_stable_files(ehull_csv, args.ehull_threshold)
        grand_total += total
        for fn in stable:
            stable_entries.append((fn, cif_dir))
        print(f"  Total scored: {total}")
        print(f"  Stable (ehull < {args.ehull_threshold}): {len(stable)}")

    stable_files_count = len(stable_entries)
    print(f"\nTotal across all sources: {grand_total} scored, "
          f"{stable_files_count} stable")

    if not stable_entries:
        print("ERROR: No stable structures found!")
        sys.exit(1)

    # ---- Step 2: Load tokenizer ----
    print(f"Loading tokenizer from {pkg_dir}")
    tokenizer = load_tokenizer(pkg_dir)

    # ---- Step 3: Read and tokenize CIF files ----
    print(f"Processing {len(stable_entries)} stable CIF files ...")
    samples = []
    skipped_missing = 0
    skipped_too_long = 0
    skipped_error = 0
    token_lengths = []
    space_groups = Counter()
    source_dirs = Counter()

    for fname, cif_dir in sorted(stable_entries, key=lambda x: x[0]):
        fpath = cif_dir / fname
        if not fpath.exists():
            skipped_missing += 1
            continue

        try:
            cif_text = fpath.read_text(encoding="utf-8", errors="replace")

            # Tokenize the full CIF (data_... header is included)
            tokenized = tokenizer.tokenize_cif(cif_text)
            token_ids = tokenizer.encode(tokenized)
            n_tokens = len(token_ids)

            if n_tokens > args.max_tokens:
                skipped_too_long += 1
                continue

            # Extract space group for statistics
            m = re.search(r'_symmetry_space_group_name_H-M\s+(.*?)\n', cif_text)
            if m:
                space_groups[m.group(1).strip()] += 1

            samples.append({
                "file": fname,
                "text": cif_text.rstrip("\n"),
                "token_ids": token_ids,
                "n_tokens": n_tokens,
            })
            token_lengths.append(n_tokens)
            source_dirs[str(cif_dir)] += 1

        except Exception as e:
            skipped_error += 1
            if skipped_error <= 5:
                print(f"  WARNING: Error processing {fname}: {e}")

    # ---- Step 4: Split train/val and write JSONL ----
    import random as _random
    split_rng = _random.Random(args.seed)
    split_rng.shuffle(samples)

    val_count = int(len(samples) * args.val_split) if args.val_split > 0 else 0
    val_samples = samples[:val_count]
    train_samples = samples[val_count:]

    print(f"\nWriting {len(train_samples)} train samples to {out_path}")
    with open(out_path, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    if val_samples:
        val_path = out_path.parent / out_path.name.replace(".jsonl", "_val.jsonl")
        print(f"Writing {len(val_samples)} val samples to {val_path}")
        with open(val_path, "w", encoding="utf-8") as f:
            for s in val_samples:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # ---- Step 5: Report statistics ----
    print(f"\n{'='*60}")
    print(f"SFT Data Preparation Summary")
    print(f"{'='*60}")
    print(f"  Input stable CIFs: {stable_files_count}")
    print(f"  Output samples: {len(samples)} (train={len(train_samples)}, val={len(val_samples)})")
    print(f"  Skipped (missing): {skipped_missing}")
    print(f"  Skipped (too long > {args.max_tokens} tokens): {skipped_too_long}")
    print(f"  Skipped (error): {skipped_error}")
    if len(source_dirs) > 1:
        print(f"\n  Samples by source directory:")
        for d, cnt in source_dirs.most_common():
            print(f"    {d}: {cnt}")

    if token_lengths:
        print(f"\n  Token length distribution:")
        print(f"    Mean: {statistics.mean(token_lengths):.1f}")
        print(f"    Median: {statistics.median(token_lengths):.1f}")
        print(f"    Min: {min(token_lengths)}, Max: {max(token_lengths)}")
        print(f"    Std: {statistics.stdev(token_lengths):.1f}")

    if space_groups:
        print(f"\n  Space group distribution:")
        total_sg = sum(space_groups.values())
        for sg, cnt in space_groups.most_common(10):
            print(f"    {sg:15s}: {cnt:5d} ({cnt/total_sg*100:.1f}%)")

    # Save stats JSON
    stats_path = out_path.parent / "sft_data_stats.json"
    stats = {
        "total_stable": stable_files_count,
        "output_samples": len(samples),
        "train_samples": len(train_samples),
        "val_samples": len(val_samples),
        "val_split": args.val_split,
        "skipped_missing": skipped_missing,
        "skipped_too_long": skipped_too_long,
        "skipped_error": skipped_error,
        "num_sources": len(ehull_csvs),
        "ehull_csvs": ehull_csvs,
        "cif_dirs": [str(d) for d in cif_dirs],
        "samples_by_source": dict(source_dirs),
        "token_length_mean": round(statistics.mean(token_lengths), 1) if token_lengths else 0,
        "token_length_median": round(statistics.median(token_lengths), 1) if token_lengths else 0,
        "token_length_min": min(token_lengths) if token_lengths else 0,
        "token_length_max": max(token_lengths) if token_lengths else 0,
        "space_group_distribution": dict(space_groups.most_common()),
        "ehull_threshold": args.ehull_threshold,
        "max_tokens": args.max_tokens,
    }
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"\n  Stats saved to: {stats_path}")
    print(f"  Data saved to: {out_path}")


if __name__ == "__main__":
    main()
