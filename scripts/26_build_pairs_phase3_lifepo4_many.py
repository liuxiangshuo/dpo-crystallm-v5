import argparse, csv, json, random
from pathlib import Path

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels_csv", default="data/scored/labels.csv")
    ap.add_argument("--scores_csv", default="data/scored/ehull_scores.csv")
    ap.add_argument("--cif_dir", default="data/raw_cifs")
    ap.add_argument("--out_jsonl", default="data/dpo_pairs/pairs_phase3_LiFePO4_many.jsonl")
    ap.add_argument("--target", default="LiFePO4")
    ap.add_argument("--gap", type=float, default=0.05)
    ap.add_argument("--q", type=float, default=0.2)          # top/bottom quantile
    ap.add_argument("--num_pairs", type=int, default=1000)   # how many pairs to write
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    # load labels
    labels = {}
    with open(args.labels_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["file"]] = row

    # load scores
    scores = {}
    with open(args.scores_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = (row.get("score_e_per_atom") or "").strip()
            if not v:
                continue
            try:
                scores[row["file"]] = float(v)
            except:
                pass

    # winners = valid + hit_target + has score
    winners = [fn for fn, r in labels.items()
               if r.get("valid")=="True" and r.get("hit_target")=="True" and fn in scores]

    if len(winners) < 10:
        raise SystemExit(f"Too few winners with scores: {len(winners)}")

    # sort by stability score (lower is better)
    winners_sorted = sorted(winners, key=lambda fn: scores[fn])
    n = len(winners_sorted)
    k = max(1, int(n * args.q))

    top = winners_sorted[:k]      # most stable
    bot = winners_sorted[-k:]     # least stable

    cif_dir = Path(args.cif_dir)
    out = Path(args.out_jsonl)
    out.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with out.open("w", encoding="utf-8") as f:
        tries = 0
        while written < args.num_pairs and tries < args.num_pairs * 50:
            tries += 1
            c = rng.choice(top)
            r = rng.choice(bot)
            if (scores[r] - scores[c]) < args.gap:
                continue
            rec = {
                "prompt": args.target,
                "chosen": read_text(cif_dir / c),
                "rejected": read_text(cif_dir / r),
                "chosen_file": c,
                "rejected_file": r,
                "tag": "scenario_A_quantile_gap",
                "chosen_score": scores[c],
                "rejected_score": scores[r],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

    print("Wrote:", out)
    print("Pairs:", written)
    print("Winners:", n, "TopQ:", k, "BottomQ:", k, "Gap:", args.gap)

if __name__ == "__main__":
    main()
