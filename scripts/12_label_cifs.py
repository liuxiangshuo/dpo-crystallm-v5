import argparse
from pathlib import Path
import csv
from pymatgen.core import Structure

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", type=str, default="data/raw_cifs")
    ap.add_argument("--out_csv", type=str, default="data/scored/labels.csv")
    ap.add_argument("--target", type=str, default="NaCl")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in sorted(in_dir.glob("*.cif")):
        valid = False
        formula = ""
        err = ""
        try:
            s = Structure.from_file(str(p))
            valid = True
            formula = s.composition.reduced_formula
        except Exception as e:
            err = repr(e)

        hit = (formula == args.target) if valid else False

        rows.append({
            "file": p.name,
            "valid": str(valid),
            "formula": formula,
            "target": args.target,
            "hit_target": str(hit),
            "error": err,
        })

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file","valid","formula","target","hit_target","error"])
        w.writeheader()
        w.writerows(rows)

    n = len(rows)
    n_valid = sum(1 for r in rows if r["valid"] == "True")
    n_hit = sum(1 for r in rows if r["hit_target"] == "True")
    print(f"Total={n}  Valid={n_valid}  HitTarget={n_hit}")
    print("Wrote:", out_csv)

if __name__ == "__main__":
    main()
