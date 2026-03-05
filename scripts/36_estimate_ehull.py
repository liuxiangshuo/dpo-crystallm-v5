#!/usr/bin/env python3
"""
Estimate Ehull (energy above convex hull) for scored CIF structures.

Strategy:
  1. Query Materials Project API for hull reference energies of each composition.
  2. Compute Ehull_proxy = E_matgl_per_atom - E_hull_ref_per_atom.
  3. Fallback: if MP API unavailable, use relative ranking within composition group.

Requires: mp-api package and MP_API_KEY environment variable.

Output: ehull_estimates.csv with columns:
  file, formula, e_per_atom, ehull_proxy, ehull_method
"""
import argparse
import csv
import json
import os
from pathlib import Path
from collections import defaultdict

def query_mp_hull_energies(formulas: list, api_key: str = None) -> dict:
    """
    Query Materials Project for the hull energy (energy_above_hull=0 reference)
    for each unique formula. Returns {formula: e_per_atom_on_hull}.
    """
    hull_refs = {}
    try:
        from mp_api.client import MPRester
        key = api_key or os.environ.get("MP_API_KEY", "")
        if not key:
            print("WARNING: MP_API_KEY not set. Ehull estimation will use fallback method.")
            return hull_refs

        with MPRester(key) as mpr:
            for formula in set(formulas):
                try:
                    # Search for stable (on-hull) entries
                    docs = mpr.thermo.search(
                        formula=formula,
                        energy_above_hull=(0, 0.001),  # near-hull entries
                        fields=["energy_per_atom", "formula_pretty", "energy_above_hull"],
                    )
                    if docs:
                        # Take the entry with lowest energy_per_atom
                        best = min(docs, key=lambda d: d.energy_per_atom)
                        hull_refs[formula] = best.energy_per_atom
                        print(f"  MP hull ref for {formula}: {best.energy_per_atom:.4f} eV/atom")
                    else:
                        print(f"  MP: no hull entry for {formula}")
                except Exception as e:
                    print(f"  MP query failed for {formula}: {e}")
    except ImportError:
        print("WARNING: mp-api not installed. Ehull estimation will use fallback method.")
    return hull_refs


def main():
    ap = argparse.ArgumentParser(description="Estimate Ehull from MatGL scores + MP hull references")
    ap.add_argument("--scores_csv", required=True, help="MatGL scores CSV (file, formula, score_e_per_atom)")
    ap.add_argument("--out_csv", required=True, help="Output CSV with ehull estimates")
    ap.add_argument("--api_key", default=None, help="Materials Project API key (or set MP_API_KEY env)")
    ap.add_argument("--fallback_percentile", type=float, default=0.1,
                    help="Fallback: treat bottom percentile as hull reference")
    args = ap.parse_args()

    # Load scores
    rows = []
    formulas = []
    with open(args.scores_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            e_str = (row.get("score_e_per_atom") or "").strip()
            if e_str:
                try:
                    e = float(e_str)
                    rows.append({
                        "file": row["file"],
                        "formula": row.get("formula", ""),
                        "e_per_atom": e,
                    })
                    formulas.append(row.get("formula", ""))
                except ValueError:
                    pass

    if not rows:
        print("No scored rows to process.")
        return

    print(f"Loaded {len(rows)} scored structures across {len(set(formulas))} formulas.")

    # Try MP API for hull references
    hull_refs = query_mp_hull_energies(formulas, api_key=args.api_key)

    # Fallback: use per-formula bottom percentile as hull reference
    by_formula = defaultdict(list)
    for r in rows:
        by_formula[r["formula"]].append(r["e_per_atom"])

    fallback_refs = {}
    for formula, energies in by_formula.items():
        if formula not in hull_refs:
            sorted_e = sorted(energies)
            k = max(1, int(len(sorted_e) * args.fallback_percentile))
            fallback_refs[formula] = sum(sorted_e[:k]) / k
            print(f"  Fallback hull ref for {formula}: {fallback_refs[formula]:.4f} eV/atom (bottom {k} samples)")

    # Compute Ehull proxy
    out_rows = []
    for r in rows:
        formula = r["formula"]
        if formula in hull_refs:
            ref = hull_refs[formula]
            method = "mp_api"
        elif formula in fallback_refs:
            ref = fallback_refs[formula]
            method = "fallback_percentile"
        else:
            ref = r["e_per_atom"]
            method = "self"

        ehull = r["e_per_atom"] - ref
        out_rows.append({
            "file": r["file"],
            "formula": formula,
            "e_per_atom": f'{r["e_per_atom"]:.6f}',
            "hull_ref_e_per_atom": f"{ref:.6f}",
            "ehull_proxy": f"{ehull:.6f}",
            "ehull_method": method,
        })

    # Write output
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[
            "file", "formula", "e_per_atom", "hull_ref_e_per_atom", "ehull_proxy", "ehull_method"
        ])
        w.writeheader()
        w.writerows(out_rows)

    # Summary
    ehull_values = [float(r["ehull_proxy"]) for r in out_rows]
    stable_count = sum(1 for e in ehull_values if e < 0.05)
    total = len(ehull_values)
    stability_rate = stable_count / total if total > 0 else 0

    summary = {
        "total_scored": total,
        "stable_count_ehull_005": stable_count,
        "stability_rate": round(stability_rate, 4),
        "mp_api_formulas": len(hull_refs),
        "fallback_formulas": len(fallback_refs),
    }
    summary_file = out_csv.parent / "ehull_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"\nWrote: {out_csv}")
    print(f"  Total: {total}, Stable (Ehull<0.05): {stable_count} ({stability_rate:.2%})")
    print(f"  MP API refs: {len(hull_refs)}, Fallback refs: {len(fallback_refs)}")
    print(f"  Summary: {summary_file}")


if __name__ == "__main__":
    main()
