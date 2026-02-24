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
from pathlib import Path

import torch


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
    """Sample a CIF-like text continuation from the model."""
    if seed is not None:
        torch.manual_seed(seed)
        if "cuda" in device:
            torch.cuda.manual_seed(seed)
    
    # Get tokenizer vocab size for clamping
    tokenizer_vocab_size = getattr(tokenizer, 'vocab_size', None)
    unk_token_id = getattr(tokenizer, 'unk_token_id', 0)

    # Encode prompt
    prompt_tokens = tokenizer.encode(tokenizer.tokenize_cif(prompt + "\n"))
    prompt_len = len(prompt_tokens)
    prompt_ids = torch.tensor([prompt_tokens], dtype=torch.long, device=device)

    # Determine block size
    block_size = 1024
    if hasattr(model, "config"):
        if hasattr(model.config, "n_positions"):
            block_size = model.config.n_positions
        elif hasattr(model.config, "block_size"):
            block_size = model.config.block_size
    elif hasattr(model, "block_size"):
        block_size = model.block_size

    print(f"Debug: prompt_len={prompt_len}, block_size={block_size}, max_tokens={max_tokens}")

    # Strictly keep total length < block_size
    max_gen_tokens = min(max_tokens, block_size - 1 - prompt_len)
    if max_gen_tokens <= 0:
        raise ValueError(f"Prompt too long ({prompt_len} tokens) for block_size {block_size}")

    print(f"Debug: max_gen_tokens={max_gen_tokens}")

    model.eval()
    generated = prompt_ids.clone()

    with torch.no_grad():
        for step in range(max_gen_tokens):
            if generated.size(1) >= block_size - 1:
                break

            # Model forward (try common calling conventions)
            try:
                out = model(generated, targets=generated)
            except (TypeError, RuntimeError):
                try:
                    out = model(generated, generated)
                except (TypeError, RuntimeError):
                    out = model(generated)

            if isinstance(out, (tuple, list)):
                logits = out[0]
            elif hasattr(out, "logits"):
                logits = out.logits
            else:
                logits = out

            next_token_logits = logits[0, -1, :] / temperature

            # Top-k filtering
            if top_k > 0:
                kth = torch.topk(next_token_logits, top_k)[0][..., -1, None]
                indices_to_remove = next_token_logits < kth
                next_token_logits[indices_to_remove] = float("-inf")

            # Sample
            probs = torch.softmax(next_token_logits, dim=-1)
            next_token = torch.multinomial(probs, num_samples=1)
            
            # Ensure token ID is within tokenizer vocabulary
            token_id = next_token.item()
            if tokenizer_vocab_size and token_id >= tokenizer_vocab_size:
                # Token ID out of range - use top valid token instead
                if tokenizer_vocab_size <= next_token_logits.size(0):
                    valid_logits = next_token_logits[:tokenizer_vocab_size]
                    if valid_logits.numel() > 0:
                        probs_valid = torch.softmax(valid_logits, dim=-1)
                        next_token = torch.multinomial(probs_valid, num_samples=1)
                    else:
                        # Fallback: use UNK token or token 0
                        next_token = torch.tensor([[unk_token_id]], device=device)
                else:
                    # Fallback: use UNK token
                    next_token = torch.tensor([[unk_token_id]], device=device)

            # Append
            generated = torch.cat([generated, next_token.unsqueeze(0)], dim=1)

            # EOS check
            try:
                if hasattr(tokenizer, "eos_token_id") and tokenizer.eos_token_id is not None:
                    if next_token.item() == tokenizer.eos_token_id:
                        break
            except Exception:
                pass

            # Early stopping heuristic (optional)
            if generated.size(1) % 50 == 0:
                try:
                    tmp_tokens = generated[0].cpu().tolist()
                    # Clamp tokens for safety during intermediate decode
                    if tokenizer_vocab_size:
                        max_valid_id = tokenizer_vocab_size - 1
                        tmp_tokens = [min(int(tid), max_valid_id) for tid in tmp_tokens]
                    decoded_tmp = tokenizer.decode(tmp_tokens)
                    if "_atom_site" in decoded_tmp and decoded_tmp.count("loop_") >= 2:
                        if len(decoded_tmp) > len(prompt) + 200:
                            lines = decoded_tmp.split("\n")
                            if len([l for l in lines if l.strip().startswith("data_")]) > 1:
                                break
                except Exception:
                    pass

    # Decode full sequence (this is where KeyError(token_id) often happens if vocab mismatches)
    full_tokens = generated[0].cpu().tolist()
    
    # Clamp any out-of-vocab token IDs before decoding
    if tokenizer_vocab_size:
        max_valid_id = tokenizer_vocab_size - 1
        full_tokens = [min(int(tid), max_valid_id) for tid in full_tokens]
    
    try:
        decoded = tokenizer.decode(full_tokens)
    except (KeyError, IndexError) as e:
        # Last resort: replace invalid tokens with UNK
        import traceback
        print(f"Decode error {type(e).__name__}: {e}")
        if isinstance(e, KeyError):
            try:
                print(f"  KeyError token_id={e.args[0]}")
            except Exception:
                pass
        print(f"  Attempting recovery by replacing invalid tokens...")
        print(f"  full_tokens_len={len(full_tokens)}")
        print(f"  tokenizer.vocab_size={tokenizer_vocab_size}")
        
        # Replace invalid tokens with UNK
        valid_tokens = []
        for tid in full_tokens:
            tid_int = int(tid)
            if tokenizer_vocab_size and tid_int < tokenizer_vocab_size:
                valid_tokens.append(tid_int)
            else:
                valid_tokens.append(unk_token_id)
        
        try:
            decoded = tokenizer.decode(valid_tokens)
        except Exception as e2:
            print(f"  Recovery failed: {type(e2).__name__}: {e2}")
            print("Traceback:\n" + traceback.format_exc())
            raise
    except Exception as e:
        import traceback
        print(f"Decode failed with unexpected error: {type(e).__name__}: {e}")
        print("Traceback:\n" + traceback.format_exc())
        raise

    # Extract CIF content (after prompt)
    prompt_text = prompt + "\n"
    if decoded.startswith(prompt_text):
        cif_content = decoded[len(prompt_text) :].strip()
    else:
        cif_content = decoded.strip()
    
    # Validate CIF content - check if it contains actual CIF structure, not just element symbols
    # A valid CIF should contain CIF keywords like data_, loop_, _cell_, _atom_site, etc.
    cif_keywords = ['data_', 'loop_', '_cell_', '_atom_site', '_symmetry', '_chemical']
    has_cif_structure = any(keyword in cif_content for keyword in cif_keywords)
    
    # Check if content is just repeated element symbols (common failure mode)
    # If content is mostly single characters or very repetitive, it's likely invalid
    if len(cif_content) > 0:
        unique_chars = len(set(cif_content[:100]))  # Check first 100 chars
        if unique_chars < 3 and len(cif_content) > 50:
            # Very low diversity, likely just repeated characters
            has_cif_structure = False
    
    if not has_cif_structure:
        # Content doesn't look like valid CIF, raise error to trigger retry or skip
        raise ValueError(f"Generated content does not contain valid CIF structure. Content preview: {cif_content[:100]}")

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
    args = ap.parse_args()

    ckpt_path = Path(os.path.expanduser(args.ckpt_dir))
    ckpt_file = (ckpt_path / "ckpt.pt") if ckpt_path.is_dir() else ckpt_path

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

    print(f"Generating {args.n} samples...")
    successful = 0
    failed = 0
    max_retries_per_sample = 3  # Retry up to 3 times per sample if generation fails
    
    for i in range(args.n):
        seed = args.seed + i if args.seed is not None else None
        retry_count = 0
        success = False
        
        while retry_count < max_retries_per_sample and not success:
            try:
                # Adjust seed for retries
                current_seed = seed + retry_count * 1000 if seed is not None else None
                cif_content = sample_cif(
                    model=model,
                    tokenizer=tokenizer,
                    prompt=args.prompt,
                    max_tokens=args.max_tokens,
                    top_k=args.top_k,
                    temperature=args.temperature,
                    device=args.device,
                    seed=current_seed,
                )
                out_file = out_dir / f"sample_{i:04d}.cif"
                out_file.write_text(cif_content, encoding="utf-8")
                successful += 1
                success = True
                
                if successful % 100 == 0:
                    print(f"Generated {successful} valid samples (attempted {i+1}/{args.n}, failed {failed})...")
            except ValueError as e:
                # CIF validation failed - this is expected for low-quality generations
                failed += 1
                retry_count += 1
                if retry_count >= max_retries_per_sample:
                    # Max retries reached, skip this sample silently if it's just invalid CIF
                    if "does not contain valid CIF structure" not in str(e):
                        import traceback
                        print(f"Error generating sample {i} after {max_retries_per_sample} retries: {type(e).__name__}: {e}")
            except Exception as e:
                import traceback
                failed += 1
                retry_count += 1
                if retry_count >= max_retries_per_sample:
                    print(f"Error generating sample {i} after {max_retries_per_sample} retries: {type(e).__name__}: {e}")
                    if isinstance(e, KeyError):
                        print(f"  KeyError details: token_id={e.args[0] if e.args else 'unknown'}")
                        print(f"  Tokenizer vocab_size: {getattr(tokenizer, 'vocab_size', 'unknown')}")
                        print(f"  Model vocab_size: {getattr(getattr(model, 'config', None), 'vocab_size', 'unknown')}")
                    print("Traceback:\n" + traceback.format_exc())
    
    print(f"Generation complete: {successful} valid samples, {failed} failed attempts")
    print(f"Success rate: {successful/args.n*100:.2f}%")
    print(f"Output directory: {out_dir}")


if __name__ == "__main__":
    main()
