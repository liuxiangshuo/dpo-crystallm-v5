import argparse, csv, math, os, importlib.util, inspect
from pathlib import Path

from pymatgen.core import Structure
from pymatgen.io.ase import AseAtomsAdaptor

def pick_backend():
    has_dgl = importlib.util.find_spec("dgl") is not None
    has_pyg = importlib.util.find_spec("torch_geometric") is not None
    if has_dgl:
        return "DGL"
    if has_pyg:
        return "PYG"
    return None

def load_model_local_first():
    import matgl
    load_model = getattr(matgl, "load_model", None)
    if load_model is None:
        from matgl import load_model  # type: ignore

    local_dir = Path("matgl_models/M3GNet-MP-2021.2.8-PES")
    need = ["model.pt", "state.pt", "model.json"]
    if local_dir.exists() and all((local_dir / f).exists() for f in need):
        print("Loading local MatGL model from:", local_dir)
        return load_model(str(local_dir))

    name = "M3GNet-MP-2021.2.8-PES"
    print("Local model not found, trying online model name:", name)
    return load_model(name)

def build_ase_calculator(potential):
    # MatGL versions differ; find a usable ASE calculator class dynamically.
    import matgl.ext.ase as ase_mod

    # Candidate class names seen across versions
    candidates = [
        "PESCalculator",
        "M3GNetPESCalculator",
        "M3GNetCalculator",
        "MatGLCalculator",
        "Calculator",
    ]

    for cname in candidates:
        cls = getattr(ase_mod, cname, None)
        if cls is None:
            continue
        # Try common constructor signatures
        try:
            return cls(potential=potential)
        except TypeError:
            try:
                return cls(model=potential)
            except TypeError:
                try:
                    return cls(potential)
                except TypeError:
                    pass

    # If nothing matched, print available classes to help debugging
    avail = [n for n, o in vars(ase_mod).items() if inspect.isclass(o)]
    raise RuntimeError(f"Could not find a usable ASE calculator in matgl.ext.ase. Available classes: {avail}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", default="data/scored/valid_cifs")
    ap.add_argument("--out_csv", default="data/scored/ehull_scores.csv")
    args = ap.parse_args()

    backend = pick_backend()
    if backend is None:
        raise RuntimeError("Neither dgl nor torch_geometric found. Install one backend for MatGL.")
    os.environ["MATGL_BACKEND"] = backend
    print("Using MATGL_BACKEND =", backend)

    potential = load_model_local_first()
    calc = build_ase_calculator(potential)

    in_dir = Path(args.in_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    adaptor = AseAtomsAdaptor()
    rows = []

    for cif in sorted(in_dir.glob("*.cif")):
        formula = ""
        score = math.nan
        err = ""
        try:
            s = Structure.from_file(str(cif))
            formula = s.composition.reduced_formula
            atoms = adaptor.get_atoms(s)
            atoms.calc = calc
            e = atoms.get_potential_energy()      # eV
            score = float(e) / float(len(atoms))  # eV/atom (proxy)
        except Exception as e:
            err = repr(e)

        rows.append({
            "file": cif.name,
            "formula": formula,
            "score_e_per_atom": "" if math.isnan(score) else f"{score:.8f}",
            "error": err,
        })

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file","formula","score_e_per_atom","error"])
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["score_e_per_atom"] and not r["error"])
    print("Wrote:", out_csv)
    print("Rows:", len(rows), "Scored OK:", ok)

if __name__ == "__main__":
    main()
