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
        return load_model(str(local_dir))
    return load_model("M3GNet-MP-2021.2.8-PES")

def build_ase_calculator(potential):
    import matgl.ext.ase as ase_mod
    candidates = ["PESCalculator", "M3GNetPESCalculator", "M3GNetCalculator", "MatGLCalculator", "Calculator"]
    for cname in candidates:
        cls = getattr(ase_mod, cname, None)
        if cls is None:
            continue
        # try common constructor signatures
        for kwargs in ({"potential": potential}, {"model": potential}):
            try:
                return cls(**kwargs)
            except TypeError:
                pass
        try:
            return cls(potential)
        except TypeError:
            pass
    avail = [n for n,o in vars(ase_mod).items() if inspect.isclass(o)]
    raise RuntimeError(f"No usable ASE calculator in matgl.ext.ase. Available: {avail}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_csv", required=True)
    args = ap.parse_args()

    backend = pick_backend()
    if backend is None:
        raise RuntimeError("Need dgl or torch_geometric for MatGL backend.")
    os.environ["MATGL_BACKEND"] = backend

    pot = load_model_local_first()
    calc = build_ase_calculator(pot)
    adaptor = AseAtomsAdaptor()

    in_dir = Path(args.in_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in sorted(in_dir.glob("*.cif")):
        formula = ""
        score = math.nan
        err = ""
        try:
            s = Structure.from_file(str(p))
            formula = s.composition.reduced_formula
            atoms = adaptor.get_atoms(s)
            atoms.calc = calc
            e = atoms.get_potential_energy()
            score = float(e) / float(len(atoms))
        except Exception as e:
            err = repr(e)
        rows.append({"file": p.name, "formula": formula, "score_e_per_atom": "" if math.isnan(score) else f"{score:.8f}", "error": err})

    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file","formula","score_e_per_atom","error"])
        w.writeheader()
        w.writerows(rows)

    ok = sum(1 for r in rows if r["score_e_per_atom"] and not r["error"])
    print("Wrote:", out_csv, "rows:", len(rows), "ok:", ok)

if __name__ == "__main__":
    main()
