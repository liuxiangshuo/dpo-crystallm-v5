import argparse
from pathlib import Path

def has_any(lines, key_prefix: str) -> bool:
    return any(ln.strip().startswith(key_prefix) for ln in lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_cif", required=True)
    ap.add_argument("--out_cif", required=True)
    ap.add_argument("--data_name", default="generated")
    ap.add_argument("--a", type=float, default=10.0)
    ap.add_argument("--b", type=float, default=10.0)
    ap.add_argument("--c", type=float, default=10.0)
    ap.add_argument("--alpha", type=float, default=90.0)
    ap.add_argument("--beta", type=float, default=90.0)
    ap.add_argument("--gamma", type=float, default=90.0)
    args = ap.parse_args()

    txt = Path(args.in_cif).read_text(encoding="utf-8", errors="replace").splitlines()
    # remove CrystaLLM warning comment lines
    lines = [ln for ln in txt if not ln.strip().startswith("# WARNING:") and ln.strip() != ""]

    # ensure data_ header
    if not lines or not lines[0].lower().startswith("data_"):
        lines = [f"data_{args.data_name}"] + lines

    insert = []

    # symmetry fallbacks
    if not any("_symmetry_space_group_name_H-M" in ln for ln in lines):
        insert.append("_symmetry_space_group_name_H-M   'P 1'")
    if not any("_symmetry_Int_Tables_number" in ln for ln in lines):
        insert.append("_symmetry_Int_Tables_number 1")

    # cell fallbacks (required for building a structure)
    if not has_any(lines, "_cell_length_a"):
        insert.append(f"_cell_length_a   {args.a}")
    if not has_any(lines, "_cell_length_b"):
        insert.append(f"_cell_length_b   {args.b}")
    if not has_any(lines, "_cell_length_c"):
        insert.append(f"_cell_length_c   {args.c}")
    if not has_any(lines, "_cell_angle_alpha"):
        insert.append(f"_cell_angle_alpha {args.alpha}")
    if not has_any(lines, "_cell_angle_beta"):
        insert.append(f"_cell_angle_beta  {args.beta}")
    if not has_any(lines, "_cell_angle_gamma"):
        insert.append(f"_cell_angle_gamma {args.gamma}")

    if insert:
        lines = [lines[0]] + insert + lines[1:]

    Path(args.out_cif).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote:", args.out_cif)

if __name__ == "__main__":
    main()
