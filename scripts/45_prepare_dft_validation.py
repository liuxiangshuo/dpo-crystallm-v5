#!/usr/bin/env python3
"""
Phase 4.3: DFT Validation Preparation

Selects top-N generated structures (by Ehull proxy) for DFT validation.
Outputs:
  - POSCAR files for VASP input
  - QE input files for Quantum ESPRESSO
  - Summary CSV with rankings and proxy scores
  - Analysis of DFT vs proxy correlation (after DFT results are provided)

Usage:
    # Step 1: Prepare DFT inputs
    python scripts/45_prepare_dft_validation.py prepare \
        --cif_dir outputs/exp_ablation_dpo/dpo/raw_cifs \
        --ehull_csv outputs/exp_ablation_dpo/dpo/scored/ehull_estimates.csv \
        --scores_csv outputs/exp_ablation_dpo/dpo/scored/ehull_scores.csv \
        --out_dir reports/dft_validation \
        --top_n 20

    # Step 2: Analyze DFT results (after DFT calculations complete)
    python scripts/45_prepare_dft_validation.py analyze \
        --proxy_csv reports/dft_validation/selected_structures.csv \
        --dft_csv reports/dft_validation/dft_results.csv \
        --out_dir reports/dft_validation
"""

import argparse
import csv
import json
import os
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")


def prepare_dft_inputs(args):
    """Select top-N structures and prepare DFT input files."""
    from pymatgen.core import Structure
    from pymatgen.io.vasp import Poscar
    from pymatgen.io.pwscf import PWInput

    # Load ehull estimates
    ehull_data = {}
    if args.ehull_csv and Path(args.ehull_csv).exists():
        with open(args.ehull_csv) as f:
            for row in csv.DictReader(f):
                fname = row["file"]
                try:
                    ehull = float(row.get("ehull_proxy", "999"))
                    ehull_data[fname] = ehull
                except (ValueError, KeyError):
                    pass

    # Load MatGL scores
    scores_data = {}
    if args.scores_csv and Path(args.scores_csv).exists():
        with open(args.scores_csv) as f:
            for row in csv.DictReader(f):
                fname = row["file"]
                try:
                    score = float(row.get("score_e_per_atom", ""))
                    scores_data[fname] = score
                except (ValueError, KeyError):
                    pass

    # Rank by ehull (lower is better)
    ranked = sorted(ehull_data.items(), key=lambda x: x[1])
    top_n = ranked[:args.top_n]

    print(f"Selected top {len(top_n)} structures by Ehull proxy:")
    for i, (fname, ehull) in enumerate(top_n):
        energy = scores_data.get(fname, "N/A")
        print(f"  {i+1:>3d}. {fname}: ehull={ehull:.4f} eV/atom, energy={energy}")

    # Create output directories
    out_dir = Path(args.out_dir)
    poscar_dir = out_dir / "poscar"
    qe_dir = out_dir / "qe_inputs"
    cif_selected_dir = out_dir / "selected_cifs"
    poscar_dir.mkdir(parents=True, exist_ok=True)
    qe_dir.mkdir(parents=True, exist_ok=True)
    cif_selected_dir.mkdir(parents=True, exist_ok=True)

    # Process each structure
    results = []
    for rank, (fname, ehull) in enumerate(top_n, 1):
        cif_path = Path(args.cif_dir) / fname
        if not cif_path.exists():
            print(f"  WARNING: {cif_path} not found, skipping")
            continue

        try:
            structure = Structure.from_file(str(cif_path))

            # Save POSCAR
            poscar = Poscar(structure, comment=f"DPO-CrystaLLM rank={rank} ehull={ehull:.4f}")
            poscar.write_file(str(poscar_dir / f"POSCAR_{rank:03d}_{fname.replace('.cif', '')}"))

            # Save QE input (basic template)
            try:
                # Pseudo-potentials (placeholder - user needs to set actual paths)
                pseudos = {}
                for elem in structure.composition.elements:
                    pseudos[str(elem)] = f"{elem}.UPF"

                pwinput = PWInput(
                    structure,
                    pseudo=pseudos,
                    control={
                        "calculation": "relax",
                        "prefix": f"rank{rank:03d}",
                        "pseudo_dir": "./pseudo/",
                        "outdir": "./tmp/",
                        "tstress": True,
                        "tprnfor": True,
                    },
                    system={
                        "ecutwfc": 50.0,
                        "ecutrho": 400.0,
                        "occupations": "smearing",
                        "smearing": "gaussian",
                        "degauss": 0.01,
                    },
                    electrons={
                        "conv_thr": 1.0e-6,
                        "mixing_beta": 0.7,
                    },
                    kpoints_mode="automatic",
                    kpoints_grid=(4, 4, 4),
                )
                pwinput.write_file(str(qe_dir / f"rank{rank:03d}.in"))
            except Exception as e:
                print(f"  WARNING: QE input generation failed for {fname}: {e}")

            # Copy selected CIF
            import shutil
            shutil.copy2(cif_path, cif_selected_dir / f"rank{rank:03d}_{fname}")

            results.append({
                "rank": rank,
                "file": fname,
                "ehull_proxy": round(ehull, 6),
                "matgl_energy": round(scores_data.get(fname, 0), 6),
                "formula": structure.composition.reduced_formula,
                "n_atoms": len(structure),
                "volume": round(structure.lattice.volume, 4),
                "spacegroup": "",  # Will be filled if available
            })

            # Try to get space group
            try:
                from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
                sga = SpacegroupAnalyzer(structure, symprec=0.1)
                results[-1]["spacegroup"] = sga.get_space_group_symbol()
            except:
                pass

        except Exception as e:
            print(f"  ERROR: Failed to process {fname}: {e}")

    # Save summary CSV
    csv_path = out_dir / "selected_structures.csv"
    if results:
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=results[0].keys())
            w.writeheader()
            w.writerows(results)
        print(f"\nSummary CSV: {csv_path}")

    # Generate DFT template CSV for user to fill in
    dft_template = out_dir / "dft_results_template.csv"
    with open(dft_template, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "file", "dft_energy_per_atom", "dft_converged", "dft_spacegroup", "notes"])
        for r in results:
            w.writerow([r["rank"], r["file"], "", "", "", ""])
    print(f"DFT results template: {dft_template}")
    print("  -> Fill in dft_energy_per_atom after running DFT calculations")
    print(f"  -> Then run: python {__file__} analyze --proxy_csv {csv_path} --dft_csv {dft_template}")

    # Generate report
    md_path = out_dir / "dft_validation_prep.md"
    with open(md_path, "w") as f:
        f.write("# DFT Validation: Selected Structures\n\n")
        f.write(f"**Top {len(results)} structures selected by Ehull proxy**\n\n")
        f.write("| Rank | File | Formula | Ehull Proxy | MatGL Energy | SG | Atoms |\n")
        f.write("|------|------|---------|-------------|-------------|-----|-------|\n")
        for r in results:
            f.write(f"| {r['rank']} | {r['file']} | {r['formula']} | "
                    f"{r['ehull_proxy']:.4f} | {r['matgl_energy']:.4f} | "
                    f"{r['spacegroup']} | {r['n_atoms']} |\n")
        f.write("\n## DFT Input Files\n\n")
        f.write(f"- VASP POSCAR files: `{poscar_dir}/`\n")
        f.write(f"- QE input files: `{qe_dir}/`\n")
        f.write(f"- Selected CIF files: `{cif_selected_dir}/`\n")
        f.write(f"\n## Next Steps\n\n")
        f.write("1. Run VASP/QE structural relaxation for each structure\n")
        f.write("2. Record DFT energies in `dft_results_template.csv`\n")
        f.write(f"3. Run: `python {Path(__file__).name} analyze --proxy_csv selected_structures.csv "
                f"--dft_csv dft_results.csv --out_dir {out_dir}`\n")

    print(f"Report: {md_path}")


def analyze_dft_results(args):
    """Analyze correlation between proxy scores and DFT results."""
    from scipy import stats as scipy_stats

    # Load proxy data
    proxy_data = {}
    with open(args.proxy_csv) as f:
        for row in csv.DictReader(f):
            proxy_data[int(row["rank"])] = {
                "file": row["file"],
                "ehull_proxy": float(row["ehull_proxy"]),
                "matgl_energy": float(row["matgl_energy"]),
                "formula": row.get("formula", ""),
            }

    # Load DFT data
    dft_data = {}
    with open(args.dft_csv) as f:
        for row in csv.DictReader(f):
            rank = int(row["rank"])
            dft_e = row.get("dft_energy_per_atom", "").strip()
            if dft_e:
                try:
                    dft_data[rank] = {
                        "dft_energy": float(dft_e),
                        "converged": row.get("dft_converged", "").lower() in ("true", "yes", "1"),
                        "dft_spacegroup": row.get("dft_spacegroup", ""),
                    }
                except ValueError:
                    pass

    if not dft_data:
        print("ERROR: No DFT results found. Please fill in dft_results_template.csv first.")
        return

    # Merge
    merged = []
    for rank in sorted(set(proxy_data.keys()) & set(dft_data.keys())):
        entry = {**proxy_data[rank], **dft_data[rank], "rank": rank}
        merged.append(entry)

    print(f"Matched {len(merged)} structures with both proxy and DFT data")

    if len(merged) < 3:
        print("Not enough data points for correlation analysis (need >= 3)")
        return

    # Compute correlations
    proxy_energies = np.array([m["matgl_energy"] for m in merged])
    dft_energies = np.array([m["dft_energy"] for m in merged])
    proxy_ehull = np.array([m["ehull_proxy"] for m in merged])

    # Pearson correlation
    pearson_r, pearson_p = scipy_stats.pearsonr(proxy_energies, dft_energies)
    # Spearman rank correlation
    spearman_r, spearman_p = scipy_stats.spearmanr(proxy_energies, dft_energies)
    # Kendall tau
    kendall_tau, kendall_p = scipy_stats.kendalltau(proxy_energies, dft_energies)
    # MAE
    mae = float(np.mean(np.abs(proxy_energies - dft_energies)))
    # RMSE
    rmse = float(np.sqrt(np.mean((proxy_energies - dft_energies) ** 2)))

    results = {
        "n_structures": len(merged),
        "pearson_r": round(pearson_r, 4),
        "pearson_p": round(pearson_p, 6),
        "spearman_r": round(spearman_r, 4),
        "spearman_p": round(spearman_p, 6),
        "kendall_tau": round(kendall_tau, 4),
        "kendall_p": round(kendall_p, 6),
        "mae_eV": round(mae, 4),
        "rmse_eV": round(rmse, 4),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save results
    with open(out_dir / "dft_correlation.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nCorrelation results:")
    for k, v in results.items():
        print(f"  {k}: {v}")

    # Generate scatter plot
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        plots_dir = out_dir / "plots"
        plots_dir.mkdir(exist_ok=True)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

        # Plot 1: MatGL vs DFT scatter
        ax1.scatter(dft_energies, proxy_energies, s=60, alpha=0.7, color="#2196F3",
                    edgecolor="white", linewidth=0.5)
        # Fit line
        z = np.polyfit(dft_energies, proxy_energies, 1)
        p = np.poly1d(z)
        x_range = np.linspace(dft_energies.min(), dft_energies.max(), 100)
        ax1.plot(x_range, p(x_range), "r--", alpha=0.5)
        # Perfect correlation line
        lims = [min(dft_energies.min(), proxy_energies.min()),
                max(dft_energies.max(), proxy_energies.max())]
        ax1.plot(lims, lims, "k--", alpha=0.3, label="y = x")
        ax1.set_xlabel("DFT Energy (eV/atom)", fontsize=12)
        ax1.set_ylabel("MatGL Proxy Energy (eV/atom)", fontsize=12)
        ax1.set_title(f"MatGL vs DFT (r={pearson_r:.3f}, MAE={mae:.3f})", fontsize=13)
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        # Add annotations for each point
        for m in merged:
            ax1.annotate(f"R{m['rank']}", (m["dft_energy"], m["matgl_energy"]),
                         fontsize=7, alpha=0.5)

        # Plot 2: Rank correlation
        proxy_ranks = np.argsort(np.argsort(proxy_energies)) + 1
        dft_ranks = np.argsort(np.argsort(dft_energies)) + 1
        ax2.scatter(dft_ranks, proxy_ranks, s=60, alpha=0.7, color="#4CAF50",
                    edgecolor="white", linewidth=0.5)
        ax2.plot([0, len(merged)+1], [0, len(merged)+1], "k--", alpha=0.3, label="Perfect rank")
        ax2.set_xlabel("DFT Rank", fontsize=12)
        ax2.set_ylabel("MatGL Proxy Rank", fontsize=12)
        ax2.set_title(f"Rank Correlation (Spearman={spearman_r:.3f})", fontsize=13)
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(plots_dir / "dft_vs_proxy_correlation.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Plot saved: {plots_dir}/dft_vs_proxy_correlation.png")
    except ImportError:
        print("WARNING: matplotlib not available, skipping plots")

    # Generate report
    md_path = out_dir / "dft_validation_results.md"
    with open(md_path, "w") as f:
        f.write("# DFT Validation Results\n\n")
        f.write(f"**Structures validated**: {len(merged)}\n\n")

        f.write("## Correlation Metrics\n\n")
        f.write("| Metric | Value | p-value |\n")
        f.write("|--------|-------|---------|\n")
        f.write(f"| Pearson r | {pearson_r:.4f} | {pearson_p:.2e} |\n")
        f.write(f"| Spearman rho | {spearman_r:.4f} | {spearman_p:.2e} |\n")
        f.write(f"| Kendall tau | {kendall_tau:.4f} | {kendall_p:.2e} |\n")
        f.write(f"| MAE | {mae:.4f} eV/atom | - |\n")
        f.write(f"| RMSE | {rmse:.4f} eV/atom | - |\n\n")

        f.write("## Per-Structure Results\n\n")
        f.write("| Rank | Formula | MatGL Energy | DFT Energy | Error | Converged |\n")
        f.write("|------|---------|-------------|------------|-------|----------|\n")
        for m in sorted(merged, key=lambda x: x["rank"]):
            error = m["matgl_energy"] - m["dft_energy"]
            conv = "Yes" if m.get("converged") else "No"
            f.write(f"| {m['rank']} | {m['formula']} | {m['matgl_energy']:.4f} | "
                    f"{m['dft_energy']:.4f} | {error:+.4f} | {conv} |\n")

        f.write("\n## Interpretation\n\n")
        if spearman_r > 0.8:
            f.write("**Strong rank correlation** between MatGL proxy and DFT energies. "
                    "The proxy scoring is reliable for ranking generated structures.\n")
        elif spearman_r > 0.5:
            f.write("**Moderate rank correlation** between MatGL proxy and DFT energies. "
                    "The proxy is partially reliable but has notable ranking discrepancies.\n")
        else:
            f.write("**Weak rank correlation** between MatGL proxy and DFT energies. "
                    "The proxy scoring may not be reliable for this system. "
                    "Consider alternative scoring methods.\n")

    print(f"Report: {md_path}")


def main():
    parser = argparse.ArgumentParser(description="DFT Validation for DPO-CrystaLLM")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command")

    # Prepare sub-command
    prep = subparsers.add_parser("prepare", help="Prepare DFT input files")
    prep.add_argument("--cif_dir", required=True, help="Directory with generated CIF files")
    prep.add_argument("--ehull_csv", required=True, help="Ehull estimates CSV")
    prep.add_argument("--scores_csv", required=True, help="MatGL scores CSV")
    prep.add_argument("--out_dir", required=True, help="Output directory")
    prep.add_argument("--top_n", type=int, default=20, help="Number of top structures to select")

    # Analyze sub-command
    anal = subparsers.add_parser("analyze", help="Analyze DFT results")
    anal.add_argument("--proxy_csv", required=True, help="Proxy scores CSV (from prepare step)")
    anal.add_argument("--dft_csv", required=True, help="DFT results CSV (filled by user)")
    anal.add_argument("--out_dir", required=True, help="Output directory")

    args = parser.parse_args()

    if args.command == "prepare":
        prepare_dft_inputs(args)
    elif args.command == "analyze":
        analyze_dft_results(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
