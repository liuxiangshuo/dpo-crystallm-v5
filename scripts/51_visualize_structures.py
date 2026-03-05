#!/usr/bin/env python3
"""
Crystal structure visualisation — VESTA CLI + ASE fallback.

Selects the Top-N structures (by lowest ehull / highest composite reward)
from each evaluation phase (Baseline, SFT, SFT+DPO) and renders ball-and-stick
PNG images annotated with space group and lattice parameters.

Two rendering backends:
  1. VESTA CLI  — high-quality publication figures (requires VESTA >=3.5)
  2. ASE        — headless fallback using matplotlib (no GPU / display needed)

Usage:
    python scripts/51_visualize_structures.py \
        --exp_dir  outputs/exp_sft_rl_v2 \
        --targets  LiFePO4,NaCl,TiO2 \
        --branches full_ft,lora64 \
        --top_n    10 \
        --out_dir  reports/exp_sft_rl_v2/visualizations \
        --backend  vesta          # or 'ase'

    # VESTA path override:
    --vesta_bin ~/tools/VESTA/VESTA
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import warnings
warnings.filterwarnings("ignore")


def _load_ehull_top_n(scored_dir: Path, n: int):
    """Return list of (filename, ehull_eV) for the top-N most stable structures."""
    ehull_csv = scored_dir / "ehull_estimates.csv"
    if not ehull_csv.exists():
        ehull_csv = scored_dir / "ehull_scores.csv"
    if not ehull_csv.exists():
        return []

    rows = []
    with open(ehull_csv, "r") as f:
        for row in csv.DictReader(f):
            try:
                e_str = (row.get("ehull_eV")
                         or row.get("ehull_proxy")
                         or row.get("score_e_per_atom")
                         or "nan")
                e = float(e_str)
                rows.append((row["file"], e))
            except (ValueError, KeyError):
                continue

    rows.sort(key=lambda x: x[1])
    return rows[:n]


def _get_struct_info(cif_path: Path):
    """Return (spacegroup_symbol, spacegroup_number, lattice_params_str)."""
    try:
        from pymatgen.core import Structure
        from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
        s = Structure.from_file(str(cif_path))
        sga = SpacegroupAnalyzer(s, symprec=0.1)
        sg_sym = sga.get_space_group_symbol()
        sg_num = sga.get_space_group_number()
        lat = s.lattice
        params = (f"a={lat.a:.2f} b={lat.b:.2f} c={lat.c:.2f}  "
                  f"α={lat.alpha:.1f} β={lat.beta:.1f} γ={lat.gamma:.1f}")
        return sg_sym, sg_num, params, s
    except Exception as exc:
        return "?", 0, str(exc)[:60], None


# ---------------------------------------------------------------------------
# Backend: ASE (headless matplotlib)
# ---------------------------------------------------------------------------

def render_ase(structure, out_png: Path, title: str = ""):
    """Render a pymatgen Structure to PNG via ASE + matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ase.io import read as ase_read
    from ase.visualize.plot import plot_atoms
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".cif", delete=False) as tmp:
        structure.to(filename=tmp.name)
        atoms = ase_read(tmp.name)
    os.unlink(tmp.name)

    fig, ax = plt.subplots(1, 1, figsize=(6, 6))
    plot_atoms(atoms, ax, radii=0.5, rotation="10x,10y,0z")
    ax.set_title(title, fontsize=10, pad=10)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(str(out_png), dpi=200, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Backend: VESTA CLI
# ---------------------------------------------------------------------------

VESTA_SCRIPT_TEMPLATE = textwrap.dedent("""\
    OPEN {cif_path}
    EXPORT_IMAGE {png_path} 1200 1200
    QUIT
""")


def render_vesta(cif_path: Path, out_png: Path, vesta_bin: str, title: str = ""):
    """Render CIF to PNG using VESTA CLI (headless via xvfb-run if available)."""
    script_content = VESTA_SCRIPT_TEMPLATE.format(
        cif_path=str(cif_path.resolve()),
        png_path=str(out_png.resolve()),
    )
    script_file = out_png.with_suffix(".vesta_script")
    script_file.write_text(script_content)

    xvfb = shutil.which("xvfb-run")
    cmd = [vesta_bin, "-nogui", "-script", str(script_file)]
    if xvfb:
        cmd = [xvfb, "--auto-servernum", "--server-args=-screen 0 1280x1024x24"] + cmd

    try:
        subprocess.run(cmd, timeout=60, capture_output=True, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"  VESTA render failed: {e}")
    finally:
        script_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Visualise top crystal structures")
    ap.add_argument("--exp_dir", required=True, help="Experiment output dir")
    ap.add_argument("--targets", required=True, help="Comma-separated target compositions")
    ap.add_argument("--branches", default="", help="Comma-separated SFT branch names")
    ap.add_argument("--top_n", type=int, default=10, help="Number of top structures per phase")
    ap.add_argument("--out_dir", required=True, help="Output directory for PNG images")
    ap.add_argument("--backend", default="ase", choices=["ase", "vesta"],
                    help="Rendering backend")
    ap.add_argument("--vesta_bin", default="", help="Path to VESTA binary")
    ap.add_argument("--export_cifs", action="store_true",
                    help="Export CIF files instead of rendering images")
    args = ap.parse_args()

    exp_dir = Path(args.exp_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    branches = [b.strip() for b in args.branches.split(",") if b.strip()] if args.branches else ["default"]

    vesta_bin = args.vesta_bin or shutil.which("VESTA") or os.path.expanduser("~/tools/VESTA/VESTA")

    if args.backend == "vesta" and not Path(vesta_bin).exists():
        print(f"WARNING: VESTA not found at {vesta_bin}, falling back to ASE backend")
        args.backend = "ase"

    manifest = []

    for target in targets:
        phases = [("baseline", exp_dir / target / "baseline")]
        for branch in branches:
            phases.append((f"sft_{branch}", exp_dir / target / f"sft_{branch}"))
            phases.append((f"dpo_{branch}", exp_dir / target / f"dpo_{branch}"))

        for phase_name, phase_dir in phases:
            scored_dir = phase_dir / "scored"
            cif_dir = phase_dir / "raw_cifs"
            if not scored_dir.exists():
                print(f"SKIP: {scored_dir} not found")
                continue

            top_structs = _load_ehull_top_n(scored_dir, args.top_n)
            if not top_structs:
                print(f"SKIP: No scored structures in {scored_dir}")
                continue

            phase_out = out_dir / target / phase_name
            phase_out.mkdir(parents=True, exist_ok=True)

            print(f"\n--- {target} / {phase_name}: rendering top {len(top_structs)} ---")

            for rank, (fn, ehull) in enumerate(top_structs, 1):
                cif_path = cif_dir / fn
                if not cif_path.exists():
                    valid_cif = scored_dir / "valid_cifs" / fn
                    if valid_cif.exists():
                        cif_path = valid_cif
                    else:
                        continue

                sg_sym, sg_num, lat_str, struct = _get_struct_info(cif_path)
                title = f"{target} [{phase_name}] #{rank}\nSG: {sg_sym} ({sg_num})  Ehull≈{ehull:.4f}\n{lat_str}"

                if args.export_cifs:
                    # Export CIF file instead of rendering
                    out_cif = phase_out / f"rank{rank:02d}_{fn}"
                    shutil.copy(cif_path, out_cif)
                    if out_cif.exists():
                        manifest.append({
                            "target": target,
                            "phase": phase_name,
                            "rank": rank,
                            "file": fn,
                            "ehull": round(ehull, 6),
                            "spacegroup": f"{sg_sym} ({sg_num})",
                            "lattice": lat_str,
                            "cif_path": str(out_cif.relative_to(out_dir)),
                        })
                        print(f"  [OK] rank {rank}: {fn}  SG={sg_sym}({sg_num})  ehull={ehull:.4f} (CIF exported)")
                else:
                    # Render image
                    out_png = phase_out / f"rank{rank:02d}_{fn.replace('.cif', '.png')}"

                    if args.backend == "vesta":
                        render_vesta(cif_path, out_png, vesta_bin, title)
                    elif struct is not None:
                        try:
                            render_ase(struct, out_png, title)
                        except Exception as e:
                            print(f"  ASE render failed for {fn}: {e}")
                            continue

                    if out_png.exists():
                        manifest.append({
                            "target": target,
                            "phase": phase_name,
                            "rank": rank,
                            "file": fn,
                            "ehull": round(ehull, 6),
                            "spacegroup": f"{sg_sym} ({sg_num})",
                            "lattice": lat_str,
                            "image": str(out_png.relative_to(out_dir)),
                        })
                        print(f"  [OK] rank {rank}: {fn}  SG={sg_sym}({sg_num})  ehull={ehull:.4f}")

    manifest_file = out_dir / "manifest.json"
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    # Comparison panel markdown
    md_file = out_dir / "comparison.md"
    with open(md_file, "w") as f:
        f.write("# Crystal Structure Visualisation — Top Structures\n\n")
        for target in targets:
            f.write(f"## {target}\n\n")
            for branch in branches:
                f.write(f"### Branch: {branch}\n\n")
                f.write("| Rank | Baseline | SFT | SFT+DPO |\n")
                f.write("|------|----------|-----|--------|\n")
                for rank in range(1, args.top_n + 1):
                    baseline_img = f"{target}/baseline/rank{rank:02d}_*.png"
                    sft_img = f"{target}/sft_{branch}/rank{rank:02d}_*.png"
                    dpo_img = f"{target}/dpo_{branch}/rank{rank:02d}_*.png"
                    f.write(f"| {rank} | ![B]({baseline_img}) | ![S]({sft_img}) | ![D]({dpo_img}) |\n")
                f.write("\n")

    print(f"\nDone! {len(manifest)} images rendered.")
    print(f"  Manifest: {manifest_file}")
    print(f"  Comparison: {md_file}")


if __name__ == "__main__":
    main()
