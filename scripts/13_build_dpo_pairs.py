import argparse, csv, json
from pathlib import Path

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels_csv", type=str, default="data/scored/labels.csv")
    ap.add_argument("--cif_dir", type=str, default="data/raw_cifs")
    ap.add_argument("--out_jsonl", type=str, default="data/dpo_pairs/pairs.jsonl")
    ap.add_argument("--prompt", type=str, default="Generate a stable NaCl crystal structure in CIF format.")
    args = ap.parse_args()

    labels_csv = Path(args.labels_csv)
    cif_dir = Path(args.cif_dir)
    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    winners = []
    losers = []

    with open(labels_csv, "r", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            file = row["file"]
            valid = row["valid"] == "True"
            hit = row["hit_target"] == "True"
            if valid and hit:
                winners.append(file)
            else:
                losers.append(file)

    if not winners or not losers:
        raise SystemExit(f"Need both winners and losers. winners={len(winners)} losers={len(losers)}")

    # Pair each winner with a loser (simple round-robin)
    pairs = []
    for i, w in enumerate(winners):
        l = losers[i % len(losers)]
        pairs.append((w, l))

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for (w, l) in pairs:
            rec = {
                "prompt": args.prompt,
                "chosen": read_text(cif_dir / w),
                "rejected": read_text(cif_dir / l),
                "chosen_file": w,
                "rejected_file": l,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"Wrote {len(pairs)} pairs to {out_jsonl}")
    print(f"winners={len(winners)} losers={len(losers)}")

if __name__ == "__main__":
    main()
