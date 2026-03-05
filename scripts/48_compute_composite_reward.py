#!/usr/bin/env python3
"""
Plan B stability-focused composite reward.

R_total = 0.45 * R_proxy + 0.30 * R_geom + 0.20 * R_comp + 0.05 * R_novel

Key updates:
  - R_proxy uses percentile rank in a target-wise rolling energy buffer.
  - Hard validity gates are applied before composite scoring.
  - R_geom captures geometric sanity (distance, density, coordination).
  - R_comp enforces stoichiometric alignment with missing/extra element penalty.
  - R_novel is a lightweight duplicate penalty over a rolling structure-key window.
"""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from pymatgen.core import Composition, Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer

KNOWN_REFS = {
    "LiFePO4": {"density": 3.5},
    "NaCl": {"density": 2.16},
    "TiO2": {"density": 4.25},
    "BaTiO3": {"density": 6.02},
    "_default": {"density": 3.5},
}


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


def _safe_float(v, default=float("nan")):
    try:
        return float(v)
    except Exception:
        return default


def _percentile_rank(value, sorted_buffer):
    if not sorted_buffer:
        return 0.5
    arr = np.asarray(sorted_buffer, dtype=float)
    n = arr.size
    if n == 0:
        return 0.5
    # Lower energy -> lower percentile.
    rank = np.searchsorted(arr, value, side="left")
    if n == 1:
        return 0.5
    return rank / (n - 1)


def _lattice_signature(structure):
    lat = structure.lattice
    return (
        round(lat.a, 2),
        round(lat.b, 2),
        round(lat.c, 2),
        round(lat.alpha, 1),
        round(lat.beta, 1),
        round(lat.gamma, 1),
    )


def _min_interatomic_distance(structure):
    min_d = float("inf")
    for i, site in enumerate(structure):
        nbrs = structure.get_neighbors(site, r=4.0)
        for n in nbrs:
            if n.index == i:
                continue
            if n.nn_distance < min_d:
                min_d = n.nn_distance
    if math.isinf(min_d):
        return float("nan")
    return float(min_d)


def _coordination_stats(structure):
    cns = []
    for site in structure:
        cns.append(len(structure.get_neighbors(site, r=3.0)))
    if not cns:
        return float("nan"), float("nan")
    return float(np.mean(cns)), float(np.max(cns))


def _fractional_dict(comp):
    return {str(el): frac for el, frac in comp.fractional_composition.as_dict().items()}


def _cosine_similarity(frac_a, frac_b):
    all_els = set(frac_a) | set(frac_b)
    dot = sum(frac_a.get(e, 0.0) * frac_b.get(e, 0.0) for e in all_els)
    norm_a = math.sqrt(sum(v * v for v in frac_a.values())) or 1e-12
    norm_b = math.sqrt(sum(v * v for v in frac_b.values())) or 1e-12
    return dot / (norm_a * norm_b)


def _component_stats(values):
    arr = np.asarray(values, dtype=float)
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return {"mean": 0.0, "std": 0.0, "p05": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "mean": round(float(np.mean(valid)), 4),
        "std": round(float(np.std(valid)), 4),
        "p05": round(float(np.percentile(valid, 5)), 4),
        "p50": round(float(np.percentile(valid, 50)), 4),
        "p95": round(float(np.percentile(valid, 95)), 4),
    }


def _load_json(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser(description="Compute Plan B composite reward")
    ap.add_argument("--scores_csv", required=True)
    ap.add_argument("--cif_dir", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--out_csv", required=True)

    # Plan B weights
    ap.add_argument("--w_proxy", type=float, default=0.45)
    ap.add_argument("--w_geom", type=float, default=0.30)
    ap.add_argument("--w_comp", type=float, default=0.20)
    ap.add_argument("--w_novel", type=float, default=0.05)
    # Backward-compatible aliases
    ap.add_argument("--w_energy", type=float, default=None)
    ap.add_argument("--w_structure", type=float, default=None)
    ap.add_argument("--w_composition", type=float, default=None)

    # Gate / geometry controls
    ap.add_argument("--min_interatomic_distance", type=float, default=0.6)
    ap.add_argument("--enable_density_gate", action="store_true")
    ap.add_argument("--density_min", type=float, default=0.1)
    ap.add_argument("--density_max", type=float, default=30.0)

    # Rolling buffers
    ap.add_argument("--rolling_buffer_dir", default=None,
                    help="Directory to persist target-wise rolling buffers")
    ap.add_argument("--proxy_buffer_size", type=int, default=50000)
    ap.add_argument("--novelty_window", type=int, default=2000)
    ap.add_argument("--max_structures", type=int, default=None)
    args = ap.parse_args()

    # Alias mapping for backward compatibility.
    if args.w_energy is not None:
        args.w_proxy = args.w_energy
    if args.w_structure is not None:
        args.w_geom = args.w_structure
    if args.w_composition is not None:
        args.w_comp = args.w_composition

    target = args.target
    cif_dir = Path(args.cif_dir)
    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    # Normalize weights to sum to 1.0
    # This ensures the composite reward is well-defined even if user inputs are not normalized
    # Note: If weights already sum to 1.0 (e.g., 0.70 + 0.10 + 0.10 + 0.10), this is a no-op
    w_sum = args.w_proxy + args.w_geom + args.w_comp + args.w_novel
    if abs(w_sum - 1.0) > 0.001:
        print(f"WARNING: Weights sum to {w_sum:.3f}, normalizing to 1.0")
    w_proxy = args.w_proxy / w_sum
    w_geom = args.w_geom / w_sum
    w_comp = args.w_comp / w_sum
    w_novel = args.w_novel / w_sum
    print(
        "Weights(normalized): "
        f"proxy={w_proxy:.3f} geom={w_geom:.3f} comp={w_comp:.3f} novel={w_novel:.3f}"
    )

    # Load scored energies.
    score_rows = []
    with open(args.scores_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            e = _safe_float((row.get("score_e_per_atom") or "").strip(), default=float("nan"))
            if not math.isfinite(e):
                continue
            score_rows.append(
                {
                    "file": row["file"],
                    "formula": row.get("formula", ""),
                    "e_per_atom": e,
                }
            )
    if args.max_structures:
        score_rows = score_rows[: args.max_structures]
    if not score_rows:
        print("No valid scored rows found.")
        return

    # Buffer persistence.
    buffer_root = Path(args.rolling_buffer_dir) if args.rolling_buffer_dir else out_csv.parent
    proxy_buffer_path = buffer_root / "reward_proxy_buffer.json"
    novelty_buffer_path = buffer_root / "reward_novelty_buffer.json"
    proxy_state = _load_json(proxy_buffer_path)
    novelty_state = _load_json(novelty_buffer_path)
    target_proxy_buffer = list(proxy_state.get(target, []))
    target_novelty_buffer = list(novelty_state.get(target, []))

    if not target_proxy_buffer:
        target_proxy_buffer = [r["e_per_atom"] for r in score_rows]
    sorted_proxy_ref = sorted(float(x) for x in target_proxy_buffer if math.isfinite(_safe_float(x)))
    novelty_seen = set(target_novelty_buffer[-args.novelty_window :])

    target_comp = Composition(target)
    target_frac = _fractional_dict(target_comp)
    target_elements = set(target_frac.keys())
    ref_density = KNOWN_REFS.get(target, KNOWN_REFS["_default"])["density"]

    rows_out = []
    gate_counter = Counter()
    duplicate_hits = 0

    r_proxy_vals = []
    r_geom_vals = []
    r_comp_vals = []
    r_novel_vals = []
    r_total_vals = []

    for row in score_rows:
        fn = row["file"]
        e_per_atom = row["e_per_atom"]
        fpath = cif_dir / fn

        gate_failed = False
        gate_reason = ""
        min_dist = float("nan")
        density = float("nan")
        mean_cn = float("nan")
        max_cn = float("nan")
        formula = row["formula"] or ""
        sg_symbol = ""
        reduced_formula = ""

        r_proxy = 0.0
        r_geom = 0.0
        r_comp = 0.0
        r_novel = 0.0
        r_total = -1.0
        percentile_proxy = float("nan")
        duplicate_flag = 0

        try:
            structure = Structure.from_file(str(fpath))
            comp = structure.composition
            formula = formula or comp.formula
            reduced_formula = comp.reduced_formula
            density = float(structure.density)
            min_dist = _min_interatomic_distance(structure)
            mean_cn, max_cn = _coordination_stats(structure)

            if not math.isfinite(min_dist):
                gate_failed = True
                gate_reason = "min_distance_nan"
            elif min_dist < args.min_interatomic_distance:
                gate_failed = True
                gate_reason = "min_distance_below_threshold"

            if (not gate_failed) and args.enable_density_gate:
                if (not math.isfinite(density)) or density < args.density_min or density > args.density_max:
                    gate_failed = True
                    gate_reason = "density_out_of_range"

            if gate_failed:
                gate_counter[gate_reason] += 1
            else:
                # R_proxy.
                percentile_proxy = _percentile_rank(e_per_atom, sorted_proxy_ref)
                percentile_proxy = _clip(percentile_proxy, 0.05, 0.95)
                r_proxy = 1.0 - percentile_proxy

                # R_geom: distance, density sanity, coordination sanity.
                dist_score = _clip((min_dist - args.min_interatomic_distance) / 0.8, 0.0, 1.0)
                density_ratio = abs(math.log(max(density, 1e-8) / max(ref_density, 1e-8)))
                density_score = _clip(1.0 - density_ratio / 1.5, 0.0, 1.0)
                cn_anomaly = 0.0
                if (math.isfinite(mean_cn) and (mean_cn < 1.0 or mean_cn > 12.0)) or (
                    math.isfinite(max_cn) and max_cn > 16.0
                ):
                    cn_anomaly = 1.0
                cn_score = 1.0 - cn_anomaly
                r_geom = _clip((dist_score + density_score + cn_score) / 3.0, 0.0, 1.0)

                # R_comp: cosine with explicit missing/extra element penalty.
                gen_frac = _fractional_dict(comp)
                base_comp = _clip(_cosine_similarity(target_frac, gen_frac), 0.0, 1.0)
                gen_elements = set(gen_frac.keys())
                missing = len(target_elements - gen_elements)
                extra = len(gen_elements - target_elements)
                miss_frac = missing / max(len(target_elements), 1)
                extra_frac = extra / max(len(gen_elements), 1)
                comp_penalty = 0.35 * miss_frac + 0.25 * extra_frac
                if reduced_formula == target_comp.reduced_formula:
                    r_comp = 1.0
                else:
                    r_comp = _clip(base_comp - comp_penalty, 0.0, 1.0)

                # R_novel: duplicate key in rolling window -> 0 else 1.
                try:
                    sg_symbol = SpacegroupAnalyzer(structure, symprec=0.1).get_space_group_symbol()
                except Exception:
                    sg_symbol = "SG_UNKNOWN"
                struct_key = f"{reduced_formula}|{sg_symbol}|{_lattice_signature(structure)}"
                if struct_key in novelty_seen:
                    r_novel = 0.0
                    duplicate_flag = 1
                    duplicate_hits += 1
                else:
                    r_novel = 1.0
                target_novelty_buffer.append(struct_key)
                novelty_seen.add(struct_key)
                if len(target_novelty_buffer) > args.novelty_window:
                    target_novelty_buffer = target_novelty_buffer[-args.novelty_window :]
                    novelty_seen = set(target_novelty_buffer)

                r_total = _clip(
                    w_proxy * r_proxy + w_geom * r_geom + w_comp * r_comp + w_novel * r_novel,
                    0.0,
                    1.0,
                )
        except Exception:
            gate_failed = True
            gate_reason = "parse_or_structure_fail"
            gate_counter[gate_reason] += 1

        rows_out.append(
            {
                "file": fn,
                "formula": formula,
                "e_per_atom": round(e_per_atom, 6),
                "r_proxy": round(r_proxy, 6),
                "r_geom": round(r_geom, 6),
                "r_comp": round(r_comp, 6),
                "r_novel": round(r_novel, 6),
                "r_total": round(-1.0 if gate_failed else r_total, 6),
                "gate_failed": int(gate_failed),
                "gate_reason": gate_reason,
                "percentile_proxy": "" if not math.isfinite(percentile_proxy) else round(percentile_proxy, 6),
                "duplicate_flag": duplicate_flag,
                "min_interatomic_distance": "" if not math.isfinite(min_dist) else round(min_dist, 6),
                "density": "" if not math.isfinite(density) else round(density, 6),
                "mean_cn": "" if not math.isfinite(mean_cn) else round(mean_cn, 4),
                "max_cn": "" if not math.isfinite(max_cn) else round(max_cn, 4),
            }
        )

        # Track stats only for gate-passed samples.
        if not gate_failed:
            r_proxy_vals.append(r_proxy)
            r_geom_vals.append(r_geom)
            r_comp_vals.append(r_comp)
            r_novel_vals.append(r_novel)
            r_total_vals.append(r_total)
            target_proxy_buffer.append(e_per_atom)

    # Persist rolling buffers.
    target_proxy_buffer = target_proxy_buffer[-args.proxy_buffer_size :]
    proxy_state[target] = target_proxy_buffer
    novelty_state[target] = target_novelty_buffer[-args.novelty_window :]
    _save_json(proxy_buffer_path, proxy_state)
    _save_json(novelty_buffer_path, novelty_state)

    # Write per-sample CSV.
    fieldnames = [
        "file",
        "formula",
        "e_per_atom",
        "r_proxy",
        "r_geom",
        "r_comp",
        "r_novel",
        "r_total",
        "gate_failed",
        "gate_reason",
        "percentile_proxy",
        "duplicate_flag",
        "min_interatomic_distance",
        "density",
        "mean_cn",
        "max_cn",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows_out:
            w.writerow(row)

    # Summary.
    total_n = len(rows_out)
    passed_n = sum(1 for r in rows_out if int(r["gate_failed"]) == 0)
    gate_failed_n = total_n - passed_n
    duplicate_rate = duplicate_hits / max(passed_n, 1)
    summary = {
        "n_structures": total_n,
        "n_gate_passed": passed_n,
        "n_gate_failed": gate_failed_n,
        "gate_failure_rate": round(gate_failed_n / max(total_n, 1), 4),
        "duplicate_rate": round(duplicate_rate, 4),
        "target": target,
        "weights": {
            "proxy": round(w_proxy, 4),
            "geom": round(w_geom, 4),
            "comp": round(w_comp, 4),
            "novel": round(w_novel, 4),
        },
        "gate_failures_by_reason": dict(gate_counter),
        "r_proxy": _component_stats(r_proxy_vals),
        "r_geom": _component_stats(r_geom_vals),
        "r_comp": _component_stats(r_comp_vals),
        "r_novel": _component_stats(r_novel_vals),
        "r_total": _component_stats(r_total_vals),
        "proxy_buffer_size": len(target_proxy_buffer),
        "novelty_window_size": min(len(target_novelty_buffer), args.novelty_window),
    }
    summary_path = out_csv.parent / "composite_reward_summary.json"
    _save_json(summary_path, summary)

    print(f"\nWrote: {out_csv} ({total_n} rows)")
    print(f"Summary: {summary_path}")
    print(f"  Gate pass: {passed_n}/{total_n} ({passed_n / max(total_n, 1):.2%})")
    print(f"  Duplicate rate: {duplicate_rate:.2%}")
    print(
        f"  R_total(mean/std/p05/p50/p95): "
        f"{summary['r_total']['mean']:.4f}/"
        f"{summary['r_total']['std']:.4f}/"
        f"{summary['r_total']['p05']:.4f}/"
        f"{summary['r_total']['p50']:.4f}/"
        f"{summary['r_total']['p95']:.4f}"
    )


if __name__ == "__main__":
    main()
