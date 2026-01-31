import argparse
from pathlib import Path
from src.utils import make_run_dir, save_json

DUMMY_CIF = """data_dummy
_symmetry_space_group_name_H-M   'P 1'
_cell_length_a   5
_cell_length_b   5
_cell_length_c   5
_cell_angle_alpha 90
_cell_angle_beta  90
_cell_angle_gamma 90
_symmetry_Int_Tables_number 1
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na1 Na 0 0 0
Cl1 Cl 0.5 0.5 0.5
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--out_dir", type=str, default="data/raw_cifs")
    args = ap.parse_args()

    run_dir = make_run_dir(outputs_dir="outputs", tag="gen_stub")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta = {
        "n": args.n,
        "out_dir": str(out_dir),
        "note": "stub generator (writes dummy CIFs). Replace with CrystaLLM later."
    }
    save_json(meta, run_dir / "meta.json")

    written = []
    for i in range(args.n):
        p = out_dir / f"sample_{i:04d}.cif"
        p.write_text(DUMMY_CIF, encoding="utf-8")
        written.append(str(p))

    save_json({"written": written}, run_dir / "written.json")
    print("Wrote", len(written), "CIFs to", out_dir)
    print("Run log:", run_dir)

if __name__ == "__main__":
    main()
