import argparse, csv, json
from pathlib import Path

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels_csv", default="data/scored/labels.csv")
    ap.add_argument("--scores_csv", default="data/scored/ehull_scores.csv")
    ap.add_argument("--cif_dir", default="data/raw_cifs")
    ap.add_argument("--out_jsonl", default="data/dpo_pairs/pairs_phase3_LiFePO4.jsonl")
    ap.add_argument("--gap", type=float, default=0.05)
    ap.add_argument("--target", default="LiFePO4")
    args = ap.parse_args()

    labels = {}
    with open(args.labels_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["file"]] = row

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

    # LiFePO4 winners = valid AND hit_target
    winners = [fn for fn,r in labels.items() if r.get("valid")=="True" and r.get("hit_target")=="True"]
    invalids = [fn for fn,r in labels.items() if r.get("valid")!="True"]

    pairs = []

    # Scenario B (proposal): valid beats invalid
    for i, w in enumerate(winners):
        if not invalids:
            break
        b = invalids[i % len(invalids)]
        pairs.append((args.target, w, b, "scenario_B_valid_vs_invalid"))

    # Scenario A (proposal): within LiFePO4, more stable beats less stable if gap >= threshold
    scored = [(scores[fn], fn) for fn in winners if fn in scores]
    scored.sort(key=lambda x: x[0])  # lower score = "more stable"
    if len(scored) >= 2:
        best_s, best_f = scored[0]
        worst_s, worst_f = scored[-1]
        if (worst_s - best_s) >= args.gap:
            pairs.append((args.target, best_f, worst_f, "scenario_A_stability_gap"))

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for prompt, chosen_file, rejected_file, tag in pairs:
            rec = {
                "prompt": prompt,  # proposal: prompt = composition
                "chosen": read_text(cif_dir / chosen_file),
                "rejected": read_text(cif_dir / rejected_file),
                "chosen_file": chosen_file,
                "rejected_file": rejected_file,
                "tag": tag,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("Wrote:", out_jsonl)
    print("Pairs:", len(pairs))
    print("Winners(hit_target):", len(winners))
    print("Invalid:", len(invalids))
    print("ScenarioA:", sum(1 for p in pairs if p[3].startswith("scenario_A")))
    print("ScenarioB:", sum(1 for p in pairs if p[3].startswith("scenario_B")))

if __name__ == "__main__":
    main()
