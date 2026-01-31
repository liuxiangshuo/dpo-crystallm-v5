import argparse
from pathlib import Path
import csv
import shutil
from pymatgen.core import Structure

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", type=str, default="data/raw_cifs")
    ap.add_argument("--out_dir", type=str, default="data/scored")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_dir = Path(args.out_dir)
    valid_dir = out_dir / "valid_cifs"
    invalid_dir = out_dir / "invalid_cifs"
    valid_dir.mkdir(parents=True, exist_ok=True)
    invalid_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    cif_paths = sorted(in_dir.glob("*.cif"))

    for p in cif_paths:
        ok = False
        nsites = ""
        formula = ""
        err = ""
        try:
            s = Structure.from_file(str(p))
            ok = True
            nsites = str(len(s))
            formula = s.composition.reduced_formula
        except Exception as e:
            err = repr(e)

        rows.append({
            "file": p.name,
            "valid": str(ok),
            "nsites": nsites,
            "formula": formula,
            "error": err,
        })

        target = (valid_dir if ok else invalid_dir) / p.name
        shutil.copy2(p, target)

    csv_path = out_dir / "parse_summary.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "valid", "nsites", "formula", "error"])
        w.writeheader()
        w.writerows(rows)

    n_valid = sum(1 for r in rows if r["valid"] == "True")
    print(f"Total: {len(rows)}  Valid: {n_valid}  Invalid: {len(rows)-n_valid}")
    print("Wrote:", csv_path)

if __name__ == "__main__":
    main()
