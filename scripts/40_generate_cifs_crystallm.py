#!/usr/bin/env python3
"""
Generate CIF files using a CrystaLLM checkpoint.

NOTE:
- This script is a lightweight generator used inside the DPO pipeline.
- It dynamically loads CrystaLLM's tokenizer/model python files from pkg_dir.
"""

import argparse
import os
import sys
import types
import importlib.util
import json
import math
from pathlib import Path
from collections import defaultdict

import time

import torch

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    from pymatgen.core import Structure
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False
    print("WARNING: pymatgen not available, structure validation will be skipped")


def load_module(path: Path, name: str):
    """Dynamically load a Python module from file or .pyc."""
    if path.exists():
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore
        return mod

    # Try .pyc file fallback
    import marshal
    pyc_dir = path.parent / "__pycache__"
    if pyc_dir.exists():
        pyc_files = list(pyc_dir.glob(f"{path.name.split('.')[0]}*.pyc"))
        if pyc_files:
            pyc_file = pyc_files[0]
            with open(pyc_file, "rb") as f:
                f.read(16)  # header
                code = marshal.load(f)
                mod = types.ModuleType(name)
                mod.__file__ = str(path)
                exec(code, mod.__dict__)
                return mod

    raise FileNotFoundError(f"Could not find {path} or corresponding .pyc file")


def load_crystallm_components(pkg_dir: Path):
    """Load CIFTokenizer, GPT, and GPTConfig from CrystaLLM package directory."""
    tok_mod = load_module(pkg_dir / "_tokenizer.py", "tok")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    mdl_mod = load_module(pkg_dir / "_model.py", "mdl")
    return tok_mod.CIFTokenizer, mdl_mod.GPT, mdl_mod.GPTConfig


def _get_block_size(model):
    """Detect the model's block_size / context length."""
    if hasattr(model, "config"):
        if hasattr(model.config, "n_positions"):
            return model.config.n_positions
        if hasattr(model.config, "block_size"):
            return model.config.block_size
    if hasattr(model, "block_size"):
        return model.block_size
    return 1024


def _model_forward(model, x):
    """Call model forward with nanoGPT-style convention handling."""
    try:
        out = model(x, targets=x)
    except (TypeError, RuntimeError):
        try:
            out = model(x, x)
        except (TypeError, RuntimeError):
            out = model(x)
    if isinstance(out, (tuple, list)):
        return out[0]
    if hasattr(out, "logits"):
        return out.logits
    return out


def _decode_safe(tokenizer, token_ids, vocab_size, unk_id=0):
    """Decode token_ids with vocab clamping and error recovery."""
    if vocab_size:
        max_valid = vocab_size - 1
        token_ids = [min(int(t), max_valid) for t in token_ids]
    try:
        return tokenizer.decode(token_ids)
    except (KeyError, IndexError):
        safe = [(t if (not vocab_size or t < vocab_size) else unk_id) for t in token_ids]
        return tokenizer.decode(safe)


# ---- Batched generation (Phase 2.1) ----------------------------------------

def sample_cif_batch(
    model,
    tokenizer,
    prompt: str,
    batch_size: int,
    max_tokens: int,
    top_k,
    temperature,
    device: str,
    seeds: list = None,
):
    """
    Generate *batch_size* CIF continuations in a single batched forward loop.
    Returns a list of decoded CIF strings (one per batch element).

    ``temperature`` and ``top_k`` may be scalars (applied uniformly) or
    lists of length *batch_size* for per-sample diversity.
    """
    # vocab_size is a property (not a method) for CrystaLLM tokenizer
    vocab_size = getattr(tokenizer, "vocab_size", None)
    if vocab_size is None:
        vocab_size = tokenizer.vocab_size
    # UNK token " " is the last token in vocab (ID = vocab_size - 1)
    unk_id = vocab_size - 1 if vocab_size else 0
    eos_id = getattr(tokenizer, "eos_token_id", None)

    prompt_tokens = tokenizer.encode(tokenizer.tokenize_cif(prompt + "\n"))
    prompt_len = len(prompt_tokens)
    block_size = _get_block_size(model)
    max_gen = min(max_tokens, block_size - 1 - prompt_len)
    if max_gen <= 0:
        raise ValueError(f"Prompt too long ({prompt_len} tokens) for block_size {block_size}")

    if isinstance(temperature, (list, tuple)):
        temp_tensor = torch.tensor(temperature, dtype=torch.float, device=device).unsqueeze(1)
    else:
        temp_tensor = torch.full((batch_size, 1), float(temperature), device=device)

    if isinstance(top_k, (list, tuple)):
        topk_list = list(top_k)
    else:
        topk_list = [int(top_k)] * batch_size
    max_topk = max(topk_list)

    model.eval()

    generated = torch.tensor(
        [prompt_tokens] * batch_size, dtype=torch.long, device=device
    )
    finished = torch.zeros(batch_size, dtype=torch.bool, device=device)

    with torch.no_grad():
        for step in range(max_gen):
            if finished.all() or generated.size(1) >= block_size - 1:
                break

            logits = _model_forward(model, generated)       # [B, T, V]
            next_logits = logits[:, -1, :] / temp_tensor     # [B, V]

            if max_topk > 0:
                for bi in range(batch_size):
                    k = topk_list[bi]
                    if k > 0 and k < next_logits.size(-1):
                        kth = torch.topk(next_logits[bi], k).values[-1]
                        next_logits[bi][next_logits[bi] < kth] = float("-inf")

            # Vocab clamp
            if vocab_size and next_logits.size(-1) > vocab_size:
                next_logits[:, vocab_size:] = float("-inf")

            probs = torch.softmax(next_logits, dim=-1)
            next_tokens = torch.multinomial(probs, num_samples=1)  # [B, 1]

            # Replace tokens for already-finished sequences with UNK token
            next_tokens[finished] = unk_id
            generated = torch.cat([generated, next_tokens], dim=1)

            # EOS check
            if eos_id is not None:
                finished |= (next_tokens.squeeze(-1) == eos_id)

    # Decode each element
    results = []
    prompt_text = prompt + "\n"
    is_cif_prompt = prompt.strip().startswith("data_")
    for b in range(batch_size):
        tokens = generated[b].cpu().tolist()
        decoded = _decode_safe(tokenizer, tokens, vocab_size, unk_id)
        if is_cif_prompt:
            # CIF-format prompt: keep prompt as part of CIF (it IS the data_ header)
            cif = decoded.strip()
        elif decoded.startswith(prompt_text):
            cif = decoded[len(prompt_text):].strip()
        else:
            cif = decoded.strip()
        results.append(cif)
    return results


# ---- Single-sample fallback (kept for retry/adaptive backoff) ---------------

def sample_cif(
    model,
    tokenizer,
    prompt: str,
    max_tokens: int,
    top_k: int,
    temperature: float,
    device: str,
    seed: int = None,
):
    """Sample a single CIF-like text continuation from the model."""
    if seed is not None:
        torch.manual_seed(seed)
        if "cuda" in device:
            torch.cuda.manual_seed(seed)

    # vocab_size is a property (not a method) for CrystaLLM tokenizer
    vocab_size = getattr(tokenizer, "vocab_size", None)
    if vocab_size is None:
        vocab_size = tokenizer.vocab_size
    # UNK token " " is the last token in vocab (ID = vocab_size - 1)
    unk_id = vocab_size - 1 if vocab_size else 0

    prompt_tokens = tokenizer.encode(tokenizer.tokenize_cif(prompt + "\n"))
    prompt_len = len(prompt_tokens)
    prompt_ids = torch.tensor([prompt_tokens], dtype=torch.long, device=device)

    block_size = _get_block_size(model)
    max_gen = min(max_tokens, block_size - 1 - prompt_len)
    if max_gen <= 0:
        raise ValueError(f"Prompt too long ({prompt_len}) for block_size {block_size}")

    model.eval()
    generated = prompt_ids.clone()

    with torch.no_grad():
        for step in range(max_gen):
            if generated.size(1) >= block_size - 1:
                break

            logits = _model_forward(model, generated)
            next_logits = logits[0, -1, :] / temperature

            if top_k > 0:
                kth = torch.topk(next_logits, top_k)[0][..., -1, None]
                next_logits[next_logits < kth] = float("-inf")

            if vocab_size and next_logits.size(0) > vocab_size:
                next_logits[vocab_size:] = float("-inf")

            probs = torch.softmax(next_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)

            generated = torch.cat([generated, next_token.unsqueeze(0)], dim=1)

            # EOS check
            eos_id = getattr(tokenizer, "eos_token_id", None)
            if eos_id is not None and next_token.item() == eos_id:
                break

    tokens = generated[0].cpu().tolist()
    decoded = _decode_safe(tokenizer, tokens, vocab_size, unk_id)

    prompt_text = prompt + "\n"
    # If prompt starts with data_, it IS the CIF header -- keep it in output
    if prompt.strip().startswith("data_"):
        return decoded.strip()
    if decoded.startswith(prompt_text):
        return decoded[len(prompt_text):].strip()
    return decoded.strip()


def validate_structure(cif_content: str, min_sites: int = 2, max_sites: int = 300):
    """
    Validate CIF structure using pymatgen with strict rules.
    Returns (is_valid, error_type).
    """
    if not HAS_PYMATGEN:
        return True, ""  # Skip validation if pymatgen not available
    
    try:
        # Check for data_ block
        if "data_" not in cif_content.lower():
            return False, "no_data_block"
        
        # Try to parse with pymatgen CifParser
        from pymatgen.io.cif import CifParser
        from io import StringIO
        parser = CifParser.from_str(cif_content)
        s = parser.parse_structures(primitive=False)[0]
        
        # Check site count
        n_sites = len(s)
        if n_sites < min_sites or n_sites > max_sites:
            return False, f"n_sites_out_of_range_{n_sites}"
        
        # Check lattice parameters
        lattice = s.lattice
        a, b, c = lattice.abc
        alpha, beta, gamma = lattice.angles
        
        if a <= 0 or b <= 0 or c <= 0:
            return False, "negative_lattice_length"
        
        if not (0 < alpha < 180 and 0 < beta < 180 and 0 < gamma < 180):
            return False, "invalid_lattice_angle"
        
        # Check atomic coordinates (should be finite and wrap-able)
        for site in s:
            coords = site.frac_coords
            if not all(math.isfinite(c) for c in coords):
                return False, "non_finite_coords"
            # Check if coordinates can be wrapped to [0,1)
            wrapped = [c % 1.0 for c in coords]
            if not all(0 <= w < 1.0 for w in wrapped):
                return False, "coords_out_of_range"
        
        # Optional: check for obvious garbage (high repetition)
        lines = cif_content.split('\n')
        if len(lines) > 10:
            char_counts = defaultdict(int)
            for line in lines[:50]:  # Check first 50 lines
                for char in line:
                    char_counts[char] += 1
            total_chars = sum(char_counts.values())
            if total_chars > 0:
                max_char_ratio = max(char_counts.values()) / total_chars
                if max_char_ratio > 0.5:  # More than 50% same character
                    return False, "high_repetition"
        
        return True, ""
    
    except Exception as e:
        error_type = type(e).__name__
        if "parse" in str(e).lower() or "syntax" in str(e).lower():
            return False, "parse_error"
        return False, f"validation_error_{error_type}"


def extract_first_data_block(cif_content: str) -> str:
    """Extract the first data_ block from CIF content."""
    lines = cif_content.split('\n')
    data_start = None
    data_end = None
    
    for i, line in enumerate(lines):
        if not line.strip().lower().startswith('data_'):
            continue
        if data_start is None:
            data_start = i
        else:
            data_end = i
            break
    
    if data_start is not None:
        if data_end is not None:
            return '\n'.join(lines[data_start:data_end])
        else:
            return '\n'.join(lines[data_start:])
    
    return cif_content


def main():
    ap = argparse.ArgumentParser(description="Generate CIF files using CrystaLLM")
    ap.add_argument("--ckpt_dir", required=True, help="Path to checkpoint directory (contains ckpt.pt) or ckpt.pt file")
    ap.add_argument("--pkg_dir", required=True, help="Path to CrystaLLM package directory (contains _tokenizer.py, _model.py)")
    ap.add_argument("--out_dir", required=True, help="Output directory for CIF files")
    ap.add_argument("--prompt", default="Generate a stable crystal structure in CIF format.", help="Prompt for generation")
    ap.add_argument("--n", type=int, default=100, help="Number of samples to generate")
    ap.add_argument("--max_tokens", type=int, default=1024, help="Max tokens to generate (<=1024 recommended)")
    ap.add_argument("--top_k", type=int, default=10, help="Top-k sampling")
    ap.add_argument("--temperature", type=float, default=1.0, help="Sampling temperature")
    ap.add_argument("--seed", type=int, default=None, help="Random seed")
    ap.add_argument("--device", default="cuda", help="Device (cuda/cpu)")
    ap.add_argument("--batch_size", type=int, default=1,
                    help="Batch size for parallel generation (>1 uses batched forward)")
    # Sampling diversity: randomise temperature and top_k per sample
    ap.add_argument("--temperature_range", default=None,
                    help="Randomise temperature per sample within range, e.g. '0.7,1.3'. "
                         "Overrides --temperature with a random value in [lo, hi] for each sample.")
    ap.add_argument("--top_k_range", default=None,
                    help="Randomise top_k per sample within range, e.g. '5,20'. "
                         "Overrides --top_k with a random int in [lo, hi] for each sample.")
    args = ap.parse_args()

    # Parse diversity ranges
    import random as _random
    _diversity_rng = _random.Random(args.seed if args.seed else 42)
    _temp_range = None
    _topk_range = None
    if args.temperature_range:
        parts = args.temperature_range.split(",")
        if len(parts) == 2:
            _temp_range = (float(parts[0]), float(parts[1]))
            print(f"Sampling diversity: temperature_range={_temp_range}")
    if args.top_k_range:
        parts = args.top_k_range.split(",")
        if len(parts) == 2:
            _topk_range = (int(parts[0]), int(parts[1]))
            print(f"Sampling diversity: top_k_range={_topk_range}")

    def _sample_temperature():
        if _temp_range:
            return _diversity_rng.uniform(_temp_range[0], _temp_range[1])
        return args.temperature

    def _sample_top_k():
        if _topk_range:
            return _diversity_rng.randint(_topk_range[0], _topk_range[1])
        return args.top_k

    # Resolve checkpoint path with clear error messages
    ckpt_input = Path(os.path.expanduser(args.ckpt_dir))
    if ckpt_input.suffix == ".pt":
        # User passed a checkpoint file directly
        if not ckpt_input.exists():
            print(f"ERROR: Checkpoint file does not exist: {ckpt_input}", file=sys.stderr)
            sys.exit(1)
        ckpt_file = ckpt_input
    else:
        # User passed a directory, look for ckpt.pt inside
        if not ckpt_input.exists():
            print(f"ERROR: Checkpoint directory does not exist: {ckpt_input}", file=sys.stderr)
            sys.exit(1)
        if not ckpt_input.is_dir():
            print(f"ERROR: --ckpt_dir must be a directory or a .pt file: {ckpt_input}", file=sys.stderr)
            sys.exit(1)
        ckpt_file = ckpt_input / "ckpt.pt"
        if not ckpt_file.exists():
            print(f"ERROR: Checkpoint file not found in directory: {ckpt_file}", file=sys.stderr)
            sys.exit(1)

    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading CrystaLLM components...")
    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)
    tokenizer = CIFTokenizer()

    print(f"Loading checkpoint from {ckpt_file}...")
    ckpt = torch.load(ckpt_file, map_location=args.device)
    config = GPTConfig(**ckpt["model_args"])
    model = GPT(config).to(args.device)
    
    # Check vocab size alignment
    model_vocab_size = getattr(config, 'vocab_size', None)
    tokenizer_vocab_size = getattr(tokenizer, 'vocab_size', None)
    if model_vocab_size and tokenizer_vocab_size:
        if model_vocab_size != tokenizer_vocab_size:
            print(f"WARNING: Vocab size mismatch! Model: {model_vocab_size}, Tokenizer: {tokenizer_vocab_size}")
            print("This may cause KeyError during decoding. Will clamp token IDs to tokenizer vocab size.")
    print(f"Model vocab_size: {model_vocab_size}, Tokenizer vocab_size: {tokenizer_vocab_size}")

    # Clean state dict (torch.compile prefix)
    state_dict = ckpt["model"]
    unwanted = "_orig_mod."
    if any(k.startswith(unwanted) for k in state_dict.keys()):
        state_dict = {(k[len(unwanted):] if k.startswith(unwanted) else k): v for k, v in state_dict.items()}

    model.load_state_dict(state_dict)
    print("Model loaded.")

    # Quality tracking
    quality_dir = out_dir.parent / "quality" if "baseline" in str(out_dir) or "dpo" in str(out_dir) else out_dir / "quality"
    quality_dir.mkdir(parents=True, exist_ok=True)
    validity_detail_file = quality_dir / "validity_detail.jsonl"
    summary_file = quality_dir / "summary.json"
    
    failure_counts = defaultdict(int)
    success_count = 0
    total_attempts = 0
    
    # Get max retries from environment or use default
    max_retries = int(os.environ.get("MAX_RETRIES", 5))
    
    batch_size = max(1, args.batch_size)
    print(f"Generating {args.n} samples (batch_size={batch_size}, max_retries={max_retries})...")
    
    # Phase 1.2: Timing infrastructure
    gen_start_time = time.perf_counter()
    per_sample_times = []  # wall-clock seconds per successful sample

    # Helper: validate + write a single candidate, return True if valid
    def _process_candidate(sample_idx, cif_raw, top_k_used, temp_used, attempt):
        nonlocal success_count
        cif_content = extract_first_data_block(cif_raw)
        is_valid, error_type = validate_structure(cif_content)
        if not is_valid:
            failure_counts[error_type] += 1
            with open(validity_detail_file, "a", encoding="utf-8") as flog:
                json.dump({"sample_id": sample_idx, "attempt": attempt,
                           "error_type": error_type, "top_k": top_k_used,
                           "temperature": temp_used}, flog, ensure_ascii=False)
                flog.write("\n")
            return False
        out_file = out_dir / f"sample_{sample_idx:04d}.cif"
        out_file.write_text(cif_content, encoding="utf-8")
        success_count += 1
        with open(validity_detail_file, "a", encoding="utf-8") as flog:
            json.dump({"sample_id": sample_idx, "attempt": attempt,
                       "error_type": "", "top_k": top_k_used,
                       "temperature": temp_used, "status": "success"},
                      flog, ensure_ascii=False)
            flog.write("\n")
        return True

    # --- Main generation: batch first pass, then single-sample retries --------
    # Collect indices that still need generation
    pending = list(range(args.n))
    done = set()

    # Progress bar over total samples
    pbar = tqdm(total=args.n, desc="Generating CIFs", unit="sample") if HAS_TQDM else None

    # --- Pass 1: batched generation (fast) ------------------------------------
    if batch_size > 1:
        for batch_start in range(0, len(pending), batch_size):
            batch_indices = pending[batch_start : batch_start + batch_size]
            b = len(batch_indices)
            batch_t0 = time.perf_counter()
            total_attempts += b

            try:
                seeds = [(args.seed + idx if args.seed is not None else None)
                         for idx in batch_indices]
                # Set seed for the whole batch to the first seed
                if seeds[0] is not None:
                    torch.manual_seed(seeds[0])
                    if "cuda" in args.device:
                        torch.cuda.manual_seed(seeds[0])

                # Sampling diversity: per-sample temperature and top_k
                per_temps = [_sample_temperature() for _ in range(b)]
                per_topks = [_sample_top_k() for _ in range(b)]

                cif_texts = sample_cif_batch(
                    model=model, tokenizer=tokenizer, prompt=args.prompt,
                    batch_size=b, max_tokens=args.max_tokens,
                    top_k=per_topks, temperature=per_temps,
                    device=args.device, seeds=seeds,
                )
            except Exception as e:
                error_name = type(e).__name__
                failure_counts[f"exception_{error_name}"] += b
                cif_texts = [None] * b
                per_temps = [args.temperature] * b
                per_topks = [args.top_k] * b

            elapsed_batch = time.perf_counter() - batch_t0

            for j, idx in enumerate(batch_indices):
                cif_raw = cif_texts[j] if cif_texts[j] is not None else ""
                if cif_raw and _process_candidate(idx, cif_raw, per_topks[j], per_temps[j], 1):
                    done.add(idx)
                    per_sample_times.append(elapsed_batch / b)

            if pbar:
                pbar.update(b)
                pbar.set_postfix(ok=success_count,
                                 rate=f"{success_count/max(1,len(done)+len(pending)-len(pending[batch_start+batch_size:]))*100:.0f}%")

        # Remaining indices that failed the batch pass
        pending = [i for i in pending if i not in done]

    # --- Pass 2: sequential retries (with adaptive backoff) -------------------
    retry_iter = pending
    if pbar is None and HAS_TQDM:
        retry_iter = tqdm(pending, desc="Retrying failed", unit="sample")
    elif pbar is None:
        retry_iter = pending

    for i in retry_iter:
        sample_start = time.perf_counter()
        seed = args.seed + i if args.seed is not None else None
        sample_success = False
        # Start with diversity-sampled params (or defaults)
        current_top_k = _sample_top_k()
        current_temp = _sample_temperature()

        # If batch_size==1, this is the first attempt; otherwise starts at attempt 2
        start_attempt = 0 if batch_size <= 1 else 1
        for attempt in range(start_attempt, max_retries):
            total_attempts += 1
            try:
                if attempt > 0:
                    current_temp = max(0.6, current_temp * 0.8)
                    current_top_k = max(5, current_top_k // 2)

                cif_content = sample_cif(
                    model=model, tokenizer=tokenizer, prompt=args.prompt,
                    max_tokens=args.max_tokens, top_k=current_top_k,
                    temperature=current_temp, device=args.device, seed=seed,
                )
                if _process_candidate(i, cif_content, current_top_k, current_temp, attempt + 1):
                    sample_success = True
                    per_sample_times.append(time.perf_counter() - sample_start)
                    break
            except Exception as e:
                error_name = type(e).__name__
                failure_counts[f"exception_{error_name}"] += 1
                with open(validity_detail_file, "a", encoding="utf-8") as flog:
                    json.dump({"sample_id": i, "attempt": attempt + 1,
                               "error_type": f"exception_{error_name}",
                               "error_msg": str(e)[:200], "top_k": current_top_k,
                               "temperature": current_temp}, flog, ensure_ascii=False)
                    flog.write("\n")

        if not sample_success and batch_size <= 1:
            # Only print for first-pass failures (batch>1 already retried)
            pass

        if pbar and batch_size <= 1:
            pbar.update(1)
            pbar.set_postfix(ok=success_count, rate=f"{success_count/max(1,i+1)*100:.0f}%")

        # Plain progress for non-tqdm
        if not HAS_TQDM and (i + 1) % 50 == 0:
            sr = success_count / (i + 1) * 100
            print(f"Progress: {i + 1}/{args.n}, ok={success_count} ({sr:.1f}%)")

        # Periodic GPU memory cleanup for long runs
        if (i + 1) % 1000 == 0 and "cuda" in args.device:
            torch.cuda.empty_cache()

    if pbar:
        pbar.close()
    
    # Phase 1.2: Compute timing
    gen_elapsed = time.perf_counter() - gen_start_time
    avg_time_per_sample = gen_elapsed / args.n if args.n > 0 else 0.0
    avg_time_per_valid = (sum(per_sample_times) / len(per_sample_times)) if per_sample_times else 0.0
    
    # Write summary
    total_generated = success_count
    valid_rate = success_count / args.n if args.n > 0 else 0.0
    
    summary = {
        "total_samples": args.n,
        "successful": success_count,
        "valid_rate": valid_rate,
        "total_attempts": total_attempts,
        "failure_counts": dict(failure_counts),
    }
    
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    # Phase 1.2: Write timing.json
    timing_file = quality_dir / "timing.json"
    timing = {
        "stage": "generation",
        "total_wall_seconds": round(gen_elapsed, 2),
        "total_samples_requested": args.n,
        "successful_samples": success_count,
        "avg_seconds_per_sample": round(avg_time_per_sample, 3),
        "avg_seconds_per_valid_sample": round(avg_time_per_valid, 3),
        "device": args.device,
    }
    with open(timing_file, "w", encoding="utf-8") as f:
        json.dump(timing, f, indent=2, ensure_ascii=False)
    
    print(f"\nGeneration complete:")
    print(f"  Total samples requested: {args.n}")
    print(f"  Successfully generated: {success_count}")
    print(f"  Valid rate: {valid_rate:.2%}")
    print(f"  Total attempts: {total_attempts}")
    print(f"  Wall time: {gen_elapsed:.1f}s ({avg_time_per_sample:.2f}s/sample)")
    print(f"  Quality logs: {quality_dir}")
    print(f"  Timing: {timing_file}")
    print(f"Generated {success_count} valid samples in {out_dir}")


if __name__ == "__main__":
    main()

