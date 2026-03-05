#!/usr/bin/env python3
"""Build DPO preference pairs with Plan-B top/bottom percentile sampling."""
import argparse
import csv
import json
import os
import sys
import types
import importlib.util
from pathlib import Path

def load_crystallm_tokenizer(pkg_dir: Path):
    """Load CIFTokenizer from CrystaLLM package."""
    tok_mod = load_module(pkg_dir / "_tokenizer.py", "tok")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    return tok_mod.CIFTokenizer

def load_module(path: Path, name: str):
    """Dynamically load a Python module from file or .pyc."""
    # Try .py file first
    if path.exists():
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return mod
    
    # Try .pyc file
    import marshal
    pyc_dir = path.parent / "__pycache__"
    if pyc_dir.exists():
        # Find matching .pyc file
        pyc_files = list(pyc_dir.glob(f"{path.name.split('.')[0]}*.pyc"))
        if pyc_files:
            pyc_file = pyc_files[0]  # Use first match
            with open(pyc_file, 'rb') as f:
                # Skip magic number (4 bytes), flags (4 bytes), timestamp (4 bytes), size (4 bytes)
                f.read(16)
                code = marshal.load(f)
                # Create module
                mod = types.ModuleType(name)
                mod.__file__ = str(path)  # Set file path for reference
                exec(code, mod.__dict__)
                return mod
    
    raise FileNotFoundError(f"Could not find {path} or corresponding .pyc file")

def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")

def strip_data_header(cif_text: str) -> str:
    """Strip the first data_XXX line from CIF content (used when prompt_cif is set)."""
    lines = cif_text.split("\n")
    if lines and lines[0].strip().startswith("data_"):
        return "\n".join(lines[1:])
    return cif_text

def count_tokens(tokenizer, text: str) -> int:
    """Count tokens in text."""
    try:
        tokens = tokenizer.tokenize_cif(text)
        return len(tokenizer.encode(tokens))
    except:
        # Fallback: rough estimate
        return len(text.split())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels_csv", required=True)
    ap.add_argument("--scores_csv", required=True)
    ap.add_argument("--cif_dir", required=True)
    ap.add_argument("--pkg_dir", required=True, help="CrystaLLM package directory for tokenizer")
    ap.add_argument("--out_jsonl", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--strategy", default="trimmed", choices=["trimmed", "all"])
    ap.add_argument("--max_tokens", type=int, default=1024)
    ap.add_argument("--gap", type=float, default=0.1, help="Minimum R_total gap between chosen and rejected")
    ap.add_argument("--q", type=float, default=0.3, help="Deprecated alias; use top/bottom percent")
    ap.add_argument("--top_percent", type=float, default=0.3, help="Top percentile for chosen pool")
    ap.add_argument("--bottom_percent", type=float, default=0.3, help="Bottom percentile for rejected pool")
    ap.add_argument("--num_pairs", type=int, default=None, help="Max pairs to generate (None = all possible)")
    ap.add_argument("--seed", type=int, default=123)
    # C1: Minimum/maximum pairs per prompt
    ap.add_argument("--pair_min_per_prompt", type=int, default=1, help="Minimum pairs per prompt (default: 1)")
    ap.add_argument("--pair_max_per_prompt", type=int, default=15000, help="Maximum pairs per prompt (default: 15000)")
    # Skip hit_target filter - use all valid scored samples
    ap.add_argument("--skip_hit_target", action="store_true", help="Skip hit_target filter, use all valid scored samples")
    # Scenario B kept for compatibility, but disabled in Plan B.
    ap.add_argument("--enable_scenario_b", action="store_true", help="Deprecated in Plan B")
    ap.add_argument("--scenario_b_max", type=int, default=None, help="Deprecated in Plan B")
    ap.add_argument("--prompt_cif", default=None, help="CIF-format prompt (e.g. data_Li4Fe4P4O16). If set, used as pair prompt and stripped from CIF content.")
    # Composite reward support
    ap.add_argument("--reward_csv", default=None,
                    help="Composite reward CSV (from 48_compute_composite_reward.py). "
                         "When provided, pairs are ranked by r_total instead of raw MatGL energy.")
    args = ap.parse_args()

    import random
    rng = random.Random(args.seed)

    # Load tokenizer
    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    print(f"Loading tokenizer from {pkg_dir}...")
    tokenizer = load_crystallm_tokenizer(pkg_dir)()
    print("Tokenizer loaded.")

    # Load labels
    labels = {}
    with open(args.labels_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels[row["file"]] = row

    # Load scores
    scores = {}
    with open(args.scores_csv, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            v = (row.get("score_e_per_atom") or "").strip()
            if not v:
                continue
            try:
                scores[row["file"]] = float(v)
            except:
                pass

    # Load composite reward (required for Plan B ranking).
    reward_scores = {}
    reward_gate = {}
    reward_gate_reason = {}
    if args.reward_csv and os.path.isfile(args.reward_csv):
        with open(args.reward_csv, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rt = (row.get("r_total") or "").strip()
                if rt:
                    try:
                        reward_scores[row["file"]] = float(rt)
                    except (ValueError, KeyError):
                        pass
                reward_gate[row.get("file", "")] = str(row.get("gate_failed", "0")) == "1"
                reward_gate_reason[row.get("file", "")] = row.get("gate_reason", "")
        print(f"Loaded composite reward for {len(reward_scores)} files from {args.reward_csv}")
        print("  (Pairs ranked by Plan-B composite r_total)")
    else:
        raise SystemExit("Plan B requires --reward_csv with r_total for pair construction.")

    rank_scores = {fn: reward_scores.get(fn, -1.0) for fn in scores}

    cif_dir = Path(args.cif_dir)
    out_jsonl = Path(args.out_jsonl)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    # Filter: valid + has score + has reward + gate passed.
    dropped = {
        "invalid_or_mismatch": 0,
        "missing_score": 0,
        "missing_reward": 0,
        "gate_failed": 0,
        "negative_reward": 0,
    }
    candidates = []
    if args.skip_hit_target:
        for fn, r in labels.items():
            if r.get("valid") != "True":
                dropped["invalid_or_mismatch"] += 1
                continue
            if fn not in scores:
                dropped["missing_score"] += 1
                continue
            if fn not in reward_scores:
                dropped["missing_reward"] += 1
                continue
            if reward_gate.get(fn, False):
                dropped["gate_failed"] += 1
                continue
            if reward_scores.get(fn, -1.0) < 0:
                dropped["negative_reward"] += 1
                continue
            candidates.append(fn)
        print(f"Using all valid scored gate-passed samples: {len(candidates)} candidates")
    else:
        for fn, r in labels.items():
            if not (r.get("valid") == "True" and r.get("hit_target") == "True"):
                dropped["invalid_or_mismatch"] += 1
                continue
            if fn not in scores:
                dropped["missing_score"] += 1
                continue
            if fn not in reward_scores:
                dropped["missing_reward"] += 1
                continue
            if reward_gate.get(fn, False):
                dropped["gate_failed"] += 1
                continue
            if reward_scores.get(fn, -1.0) < 0:
                dropped["negative_reward"] += 1
                continue
            candidates.append(fn)
        print(f"Using hit_target + gate-passed samples: {len(candidates)} candidates")

    if len(candidates) < 2:
        raise SystemExit(f"Too few candidates with scores: {len(candidates)}")

    # Use CIF-format prompt if provided; otherwise fall back to target formula
    prompt = args.prompt_cif if args.prompt_cif else args.target
    _use_cif_prompt = bool(args.prompt_cif)
    print(f"Pair prompt: {prompt!r} (cif_format={_use_cif_prompt})")
    candidates_by_prompt = {prompt: candidates}
    
    # Sort candidates: highest rank_score first (= most stable / highest reward)
    candidates_sorted_by_prompt = {}
    for p, cands in candidates_by_prompt.items():
        candidates_sorted_by_prompt[p] = sorted(
            cands, key=lambda fn: rank_scores.get(fn, 0.0), reverse=True)

    # Build pairs based on strategy, per prompt
    pairs = []
    pair_stats_by_prompt = {}  # Track pairs per prompt
    
    for prompt, candidates_sorted in candidates_sorted_by_prompt.items():
        n = len(candidates_sorted)
        if n < 2:
            pair_stats_by_prompt[prompt] = {"count": 0, "reason": "insufficient_candidates"}
            continue
        
        prompt_pairs = []
        
        if args.strategy == "trimmed":
            top_k = max(1, int(n * args.top_percent))
            bottom_k = max(1, int(n * args.bottom_percent))
            top_pool = candidates_sorted[:top_k]
            bot_pool = candidates_sorted[-bottom_k:]
            strategy_detail = f"trimmed(top={top_k}, bottom={bottom_k})"
            pair_tag = "plan_b_trimmed"
        else:
            # "all": allow pairing over the full candidate set.
            top_k = n
            bottom_k = n
            top_pool = candidates_sorted
            bot_pool = candidates_sorted
            strategy_detail = "all(full_pool)"
            pair_tag = "plan_b_all"
        max_pairs_for_prompt = min(
            args.pair_max_per_prompt,
            args.num_pairs if args.num_pairs else len(top_pool) * len(bot_pool),
        )
        min_pairs_for_prompt = args.pair_min_per_prompt

        print(
            f"Prompt '{prompt}': strategy={strategy_detail} from {n} candidates, "
            f"target_pairs={max_pairs_for_prompt}"
        )
        tries = 0
        max_tries = max_pairs_for_prompt * 20 if max_pairs_for_prompt > 0 else 0
        seen_pairs = set()
        dropped_pair = {"same_file": 0, "duplicate_pair": 0, "gap": 0, "token": 0}

        while len(prompt_pairs) < max_pairs_for_prompt and tries < max_tries:
            tries += 1
            chosen_file = rng.choice(top_pool)
            rejected_file = rng.choice(bot_pool)

            if chosen_file == rejected_file:
                dropped_pair["same_file"] += 1
                continue
            pair_key = (chosen_file, rejected_file)
            if pair_key in seen_pairs:
                dropped_pair["duplicate_pair"] += 1
                continue
            seen_pairs.add(pair_key)

            gap_val = reward_scores.get(chosen_file, -1.0) - reward_scores.get(rejected_file, -1.0)
            if gap_val < args.gap:
                dropped_pair["gap"] += 1
                continue

            chosen_cif = read_text(cif_dir / chosen_file)
            rejected_cif = read_text(cif_dir / rejected_file)
            if _use_cif_prompt:
                chosen_cif = strip_data_header(chosen_cif)
                rejected_cif = strip_data_header(rejected_cif)

            chosen_tokens = count_tokens(tokenizer, prompt + "\n" + chosen_cif)
            rejected_tokens = count_tokens(tokenizer, prompt + "\n" + rejected_cif)
            if chosen_tokens > args.max_tokens or rejected_tokens > args.max_tokens:
                dropped_pair["token"] += 1
                continue

            prompt_pairs.append({
                "prompt": prompt,
                "target": args.target,
                "chosen": chosen_cif,
                "rejected": rejected_cif,
                "chosen_file": chosen_file,
                "rejected_file": rejected_file,
                "chosen_score": scores[chosen_file],
                "rejected_score": scores[rejected_file],
                "chosen_reward": reward_scores.get(chosen_file, -1.0),
                "rejected_reward": reward_scores.get(rejected_file, -1.0),
                "chosen_tokens": chosen_tokens,
                "rejected_tokens": rejected_tokens,
                "tag": pair_tag,
            })

        if len(prompt_pairs) < min_pairs_for_prompt:
            print(
                f"WARNING: prompt '{prompt}' generated {len(prompt_pairs)} pairs < "
                f"min_required {min_pairs_for_prompt}"
            )
        
        pairs.extend(prompt_pairs)
        pair_stats_by_prompt[prompt] = {
            "count": len(prompt_pairs),
            "candidates": n,
            "top_pool": top_k,
            "bottom_pool": bottom_k,
            "min_required": args.pair_min_per_prompt,
            "max_allowed": args.pair_max_per_prompt,
            "dropped": dropped_pair,
        }

    if args.enable_scenario_b:
        print("WARNING: --enable_scenario_b is deprecated in Plan B and ignored.")

    all_pairs = pairs

    # Write pairs
    with open(out_jsonl, "w", encoding="utf-8") as f:
        for rec in all_pairs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # C1: Write pair statistics
    pair_stats_file = out_jsonl.parent / "pair_stats.json"
    with open(pair_stats_file, "w", encoding="utf-8") as f:
        json.dump({
            "total_pairs": len(all_pairs),
            "scenario_a_pairs": len(pairs),
            "scenario_b_pairs": 0,
            "strategy": args.strategy,
            "enable_scenario_b": args.enable_scenario_b,
            "use_composite_reward": bool(reward_scores),
            "reward_csv": args.reward_csv,
            "candidate_filter_dropped": dropped,
            "by_prompt": pair_stats_by_prompt,
            "summary": {
                "min_pairs_per_prompt": args.pair_min_per_prompt,
                "max_pairs_per_prompt": args.pair_max_per_prompt,
                "top_percent": args.top_percent,
                "bottom_percent": args.bottom_percent,
                "gap": args.gap,
            }
        }, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(all_pairs)} pairs to {out_jsonl} (Plan-B pairs)")
    print(f"Pair stats written to {pair_stats_file}")
    print(f"Strategy: {args.strategy}")
    print(f"Pairs by prompt:")
    for prompt, stats in pair_stats_by_prompt.items():
        print(f"  '{prompt}': {stats.get('count', 0)} pairs from {stats.get('candidates', 0)} candidates")
    if all_pairs:
        avg_chosen_tokens = sum(p["chosen_tokens"] for p in all_pairs) / len(all_pairs)
        avg_rejected_tokens = sum(p["rejected_tokens"] for p in all_pairs) / len(all_pairs)
        print(f"Avg tokens - chosen: {avg_chosen_tokens:.1f}, rejected: {avg_rejected_tokens:.1f}")

if __name__ == "__main__":
    main()
