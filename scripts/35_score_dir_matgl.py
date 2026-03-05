import argparse, csv, json, math, os, importlib.util, inspect, time, traceback
from pathlib import Path
from pymatgen.core import Structure

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False
from pymatgen.io.ase import AseAtomsAdaptor

# B2: Force LD_LIBRARY_PATH fix before importing matgl
if os.environ.get("MATGL_FIX_LD_LIBRARY_PATH") == "1":
    conda_prefix = os.environ.get("CONDA_PREFIX", "")
    if conda_prefix:
        lib_path = f"{conda_prefix}/lib"
        current_ld = os.environ.get("LD_LIBRARY_PATH", "")
        if lib_path not in current_ld:
            os.environ["LD_LIBRARY_PATH"] = f"{lib_path}:{current_ld}" if current_ld else lib_path
            print(f"Applied LD_LIBRARY_PATH fix: {os.environ['LD_LIBRARY_PATH']}")

def pick_backend():
    has_dgl = importlib.util.find_spec("dgl") is not None
    has_pyg = importlib.util.find_spec("torch_geometric") is not None
    if has_dgl:
        return "DGL"
    if has_pyg:
        return "PYG"
    return None

def ensure_backend():
    """Set matgl backend *before* loading any model (required for matgl >= 2.0)."""
    backend = pick_backend()
    if backend:
        os.environ["MATGL_BACKEND"] = backend
        try:
            import matgl
            matgl.set_backend(backend)
        except (AttributeError, ImportError):
            pass  # older matgl without set_backend
    return backend

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

def repair_structure(s: Structure):
    """
    B1: Repair and normalize structure for MatGL compatibility.
    Returns repaired structure or None if repair fails.
    """
    try:
        # Step 1: Get reduced structure (Niggli reduction)
        try:
            s = s.get_reduced_structure(reduction_algo="niggli")
        except Exception:
            # Fallback: just copy
            s = s.copy()
        
        # Step 2: Wrap coordinates to [0,1)
        s = s.copy()
        for site in s:
            site.frac_coords = [c % 1.0 for c in site.frac_coords]
        
        # Step 3: Remove problematic properties (oxidation states, etc.)
        # Keep only essential structure data - use try/except as properties may not exist
        for prop in ["oxidation_state", "magmom", "charge"]:
            try:
                s.remove_site_property(prop)
            except (ValueError, KeyError):
                pass  # Property doesn't exist, that's fine
        
        return s
    except Exception:
        return None


def _score_one_cif(cif_path_str: str, adaptor_cls=None):
    """
    Score a single CIF file.  Designed to be called in a worker process.
    Returns a dict with keys: file, formula, score_e_per_atom, error,
    error_type, traceback_str, elapsed.
    """
    p = Path(cif_path_str)
    t0 = time.perf_counter()
    formula = ""
    try:
        s = Structure.from_file(str(p))
        formula = s.composition.reduced_formula
        s2 = repair_structure(s)
        if s2 is None:
            raise ValueError("Structure repair failed")
        adaptor = AseAtomsAdaptor()
        atoms = adaptor.get_atoms(s2)
        # calculator must already be set on atoms in the worker init
        atoms.calc = _WORKER_CALC
        e = atoms.get_potential_energy()
        score = float(e) / float(len(atoms))
        return {"file": p.name, "formula": formula,
                "score_e_per_atom": f"{score:.8f}", "error": "",
                "error_type": "", "traceback_str": "",
                "elapsed": time.perf_counter() - t0}
    except Exception as exc:
        return {"file": p.name, "formula": formula,
                "score_e_per_atom": "", "error": repr(str(exc)[:500]),
                "error_type": type(exc).__name__,
                "traceback_str": traceback.format_exc()[:1000],
                "elapsed": time.perf_counter() - t0}


# Global worker state (initialised once per worker process)
_WORKER_CALC = None

def _worker_init():
    """Initialise MatGL model + calculator in each worker process."""
    global _WORKER_CALC
    ensure_backend()
    pot = load_model_local_first()
    _WORKER_CALC = build_ase_calculator(pot)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_dir", required=True)
    ap.add_argument("--out_csv", required=True)
    ap.add_argument("--num_workers", type=int, default=1,
                    help="Number of parallel scoring workers (default 1 = sequential)")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    
    # B1: Output directory for failed scores
    failed_csv = out_csv.parent / "scores_failed.csv"

    cif_files = sorted(in_dir.glob("*.cif"))
    total_cifs = len(cif_files)
    print(f"Found {total_cifs} CIF files to score (num_workers={args.num_workers}).")

    rows = []
    failed_rows = []
    failure_reasons = {}

    # Phase 1.2: Timing infrastructure
    score_start_time = time.perf_counter()
    per_cif_times = []

    num_workers = max(1, args.num_workers)

    if num_workers > 1 and total_cifs > 1:
        # ---- Multiprocessing path ----
        from multiprocessing import Pool
        cif_paths = [str(p) for p in cif_files]

        print(f"Scoring with {num_workers} parallel workers...")
        with Pool(processes=num_workers, initializer=_worker_init) as pool:
            if HAS_TQDM:
                from functools import partial
                results = list(tqdm(
                    pool.imap(_score_one_cif, cif_paths, chunksize=max(1, total_cifs // (num_workers * 4))),
                    total=total_cifs, desc="MatGL Scoring", unit="cif"))
            else:
                results = pool.map(_score_one_cif, cif_paths,
                                   chunksize=max(1, total_cifs // (num_workers * 4)))

        for r in results:
            if r["score_e_per_atom"]:
                per_cif_times.append(r["elapsed"])
                rows.append({"file": r["file"], "formula": r["formula"],
                             "score_e_per_atom": r["score_e_per_atom"], "error": ""})
            else:
                et = r["error_type"]
                failure_reasons[et] = failure_reasons.get(et, 0) + 1
                failed_rows.append({"file": r["file"], "formula": r["formula"],
                                    "error_type": et, "error": r["error"],
                                    "traceback": r["traceback_str"]})
                rows.append({"file": r["file"], "formula": r["formula"],
                             "score_e_per_atom": "", "error": r["error"]})
    else:
        # ---- Sequential path (num_workers=1) ----
        backend = ensure_backend()
        if backend is None:
            raise RuntimeError("Need dgl or torch_geometric for MatGL backend.")
        pot = load_model_local_first()
        calc = build_ase_calculator(pot)
        adaptor = AseAtomsAdaptor()

        cif_iter = enumerate(cif_files)
        if HAS_TQDM:
            cif_iter = enumerate(tqdm(cif_files, desc="MatGL Scoring", unit="cif"))

        for idx, p in cif_iter:
            formula = ""
            score = math.nan
            err = ""
            error_type = ""
            cif_start = time.perf_counter()

            try:
                s = Structure.from_file(str(p))
                formula = s.composition.reduced_formula
                s_repaired = repair_structure(s)
                if s_repaired is None:
                    raise ValueError("Structure repair failed")
                s = s_repaired
                atoms = adaptor.get_atoms(s)
                atoms.calc = calc
                e = atoms.get_potential_energy()
                score = float(e) / float(len(atoms))

                per_cif_times.append(time.perf_counter() - cif_start)
                rows.append({"file": p.name, "formula": formula,
                             "score_e_per_atom": f"{score:.8f}", "error": ""})

            except Exception as e:
                error_type = type(e).__name__
                err_msg = str(e)[:500]
                err = repr(err_msg)
                failure_reasons[error_type] = failure_reasons.get(error_type, 0) + 1
                failed_rows.append({"file": p.name, "formula": formula,
                                    "error_type": error_type, "error": err,
                                    "traceback": traceback.format_exc()[:1000]})
                rows.append({"file": p.name, "formula": formula,
                             "score_e_per_atom": "", "error": err})

    # Write successful scores
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file","formula","score_e_per_atom","error"])
        w.writeheader()
        w.writerows(rows)

    # B1: Write failed scores
    if failed_rows:
        with open(failed_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file","formula","error_type","error","traceback"])
            w.writeheader()
            w.writerows(failed_rows)

    ok = sum(1 for r in rows if r["score_e_per_atom"] and not r["error"])
    total = len(rows)
    success_rate = (ok / total * 100) if total > 0 else 0.0
    
    # Phase 1.2: Compute and write timing
    score_elapsed = time.perf_counter() - score_start_time
    avg_per_cif = score_elapsed / total if total > 0 else 0.0
    avg_per_ok = (sum(per_cif_times) / len(per_cif_times)) if per_cif_times else 0.0
    
    timing_file = out_csv.parent / "scoring_timing.json"
    timing = {
        "stage": "matgl_scoring",
        "total_wall_seconds": round(score_elapsed, 2),
        "total_cifs": total,
        "scored_ok": ok,
        "avg_seconds_per_cif": round(avg_per_cif, 3),
        "avg_seconds_per_scored_cif": round(avg_per_ok, 3),
    }
    with open(timing_file, "w", encoding="utf-8") as f:
        json.dump(timing, f, indent=2, ensure_ascii=False)
    
    print("Wrote:", out_csv, "rows:", total, "ok:", ok, f"({success_rate:.1f}%)")
    print(f"Wall time: {score_elapsed:.1f}s ({avg_per_cif:.3f}s/cif)")
    print(f"Timing: {timing_file}")
    if failed_rows:
        print(f"Failed scores written to: {failed_csv}")
        print("Failure reasons:")
        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  {reason}: {count}")

if __name__ == "__main__":
    main()
