import argparse, csv, json
from pathlib import Path

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels_csv", default="data/scored/labels.csv")
    ap.add_argument("--scores_csv", default="data/scored/ehull_scores.csv")
    ap.add_argument("--cif_dir", default="data/raw_cifs")
    ap.add_argument("--out_jsonl", default="data/dpo_pairs/pairs_phase3.jsonl")
    ap.add_argument("--gap", type=float, default=0.05)
    args = ap.parse_args()

    # labels: valid/invalid + formula + hit_target
    labels = {}
    with open(args.labels_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["file"]] = row

    # scores: proxy stability score (lower = better)
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

    cif_dir = Path(args.cif_dir)
    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    pairs = []

    # Scenario B (proposal): valid beats invalid
    valids = [fn for fn, r in labels.items() if r.get("valid") == "True" and r.get("hit_target") == "True"]
    invalids = [fn for fn, r in labels.items() if r.get("valid") != "True"]
    for i, v in enumerate(valids):
        if not invalids:
            break
        b = invalids[i % len(invalids)]
        prompt = labels[v].get("formula") or "unknown"
        pairs.append((prompt, v, b, "scenario_B_valid_vs_invalid"))

    # Scenario A (proposal): same composition, stability gap
    by_formula = {}
    for fn, r in labels.items():
        if r.get("valid") != "True":
            continue
        if fn not in scores:
            continue
        formula = r.get("formula") or "unknown"
        by_formula.setdefault(formula, []).append((scores[fn], fn))

    for formula, items in by_formula.items():
        items.sort(key=lambda x: x[0])  # lower score = more stable
        if len(items) < 2:
            continue
        best_s, best_f = items[0]
        worst_s, worst_f = items[-1]
        if (worst_s - best_s) >= args.gap:
            pairs.append((formula, best_f, worst_f, "scenario_A_stability_gap"))

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for prompt, chosen_file, rejected_file, tag in pairs:
            rec = {
                "prompt": prompt,   # proposal: prompt = composition/formula
                "chosen": read_text(cif_dir / chosen_file),
                "rejected": read_text(cif_dir / rejected_file),
                "chosen_file": chosen_file,
                "rejected_file": rejected_file,
                "tag": tag,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("Wrote:", out_jsonl)
    print("Pairs:", len(pairs))
    print("ScenarioA:", sum(1 for p in pairs if p[3].startswith("scenario_A")))
    print("ScenarioB:", sum(1 for p in pairs if p[3].startswith("scenario_B")))

if __name__ == "__main__":
    main()
