#!/usr/bin/env python3
"""
Supervised Fine-Tuning (SFT) for CrystaLLM.

Fine-tunes CrystaLLM on a set of high-quality (stable) CIF structures using
standard cross-entropy loss. This is simpler than DPO — no preference pairs,
no reference model — just next-token prediction on desirable outputs.

Supports:
  - Gradient accumulation (--grad_accum_steps)
  - Gradient clipping (--max_grad_norm)
  - Periodic checkpointing (--save_every)
  - Training log in JSONL (training_log.jsonl)
  - Cosine warmup LR schedule
  - Optional LoRA injection (--strategy lora)
  - Data shuffling per epoch

Usage:
  python 33_train_sft_crystallm.py \
    --data_jsonl outputs/exp_sft_stable/sft_data.jsonl \
    --ckpt_dir ~/projects/crystallm-repro/external/CrystaLLM/crystallm_v1_small \
    --pkg_dir ~/projects/crystallm-repro/external/CrystaLLM/crystallm \
    --out_dir outputs/exp_sft_stable/sft/checkpoint \
    --steps 6000 --lr 1e-7 --device cuda
"""
import argparse
import json
import math
import os
import random
import sys
import time
import types
import importlib.util
from pathlib import Path

import torch
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Dynamic loading helpers (CrystaLLM uses nanoGPT-style, not HuggingFace)
# ---------------------------------------------------------------------------

def load_module(path: Path, name: str):
    if path.exists():
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    # .pyc fallback
    import marshal
    pyc_dir = path.parent / "__pycache__"
    if pyc_dir.exists():
        pyc_files = list(pyc_dir.glob(f"{path.name.split('.')[0]}*.pyc"))
        if pyc_files:
            with open(pyc_files[0], "rb") as f:
                f.read(16)
                code = marshal.load(f)
                mod = types.ModuleType(name)
                mod.__file__ = str(path)
                exec(code, mod.__dict__)
                return mod
    raise FileNotFoundError(f"Could not find {path} or .pyc fallback")


def load_crystallm_components(pkg_dir: Path):
    tok_mod = load_module(pkg_dir / "_tokenizer.py", "tok")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    mdl_mod = load_module(pkg_dir / "_model.py", "mdl")
    return tok_mod.CIFTokenizer, mdl_mod.GPT, mdl_mod.GPTConfig


def clean_state_dict(sd: dict):
    prefix = "_orig_mod."
    if any(k.startswith(prefix) for k in sd):
        return {(k[len(prefix):] if k.startswith(prefix) else k): v for k, v in sd.items()}
    return sd


def build_model(GPT, GPTConfig, ckpt: dict, device: str):
    conf = GPTConfig(**ckpt["model_args"])
    m = GPT(conf).to(device)
    m.load_state_dict(clean_state_dict(ckpt["model"]))
    return m


# ---------------------------------------------------------------------------
# LoRA injection (using shared module)
# ---------------------------------------------------------------------------

# Import LoRA utilities from shared module
sys.path.insert(0, str(Path(__file__).parent))
from shared.lora_utils import LoRALinear, inject_lora, merge_lora_state_dict


# ---------------------------------------------------------------------------
# LR schedule: linear warmup + cosine decay
# ---------------------------------------------------------------------------

def cosine_lr(step: int, total_steps: int, lr: float, warmup_steps: int = 100) -> float:
    if step < warmup_steps:
        return lr * step / max(warmup_steps, 1)
    progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
    return lr * 0.5 * (1.0 + math.cos(math.pi * progress))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="SFT training for CrystaLLM")
    ap.add_argument("--data_jsonl", required=True,
                    help="JSONL file from 47_prepare_sft_data.py (each line has 'token_ids')")
    ap.add_argument("--ckpt_dir", required=True, help="Baseline checkpoint dir or ckpt.pt")
    ap.add_argument("--pkg_dir", required=True, help="CrystaLLM package dir")
    ap.add_argument("--out_dir", required=True, help="Output directory for checkpoints")
    ap.add_argument("--steps", type=int, default=6000, help="Total training steps")
    ap.add_argument("--lr", type=float, default=1e-7, help="Peak learning rate")
    ap.add_argument("--grad_accum_steps", type=int, default=8,
                    help="Gradient accumulation steps (effective batch size)")
    ap.add_argument("--max_grad_norm", type=float, default=1.0,
                    help="Max gradient norm for clipping")
    ap.add_argument("--save_every", type=int, default=1000,
                    help="Save checkpoint every N steps")
    ap.add_argument("--warmup_steps", type=int, default=300,
                    help="LR warmup steps")
    ap.add_argument("--strategy", default="full", choices=["full", "lora"],
                    help="Training strategy")
    ap.add_argument("--lora_rank", type=int, default=16, help="LoRA rank")
    ap.add_argument("--lora_alpha", type=int, default=32, help="LoRA alpha")
    ap.add_argument("--lora_target_names", default="c_attn",
                    help="Comma-separated module names for LoRA injection "
                         "(e.g. 'c_attn,c_proj,mlp')")
    ap.add_argument("--weight_decay", type=float, default=0.01,
                    help="AdamW weight decay (default 0.01)")
    ap.add_argument("--batch_size", type=int, default=16,
                    help="Batch size for training (default 16). "
                         "Use with --grad_accum_steps for larger effective batch size.")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    if "cuda" in args.device:
        torch.cuda.manual_seed(args.seed)

    ckpt_dir = os.path.expanduser(args.ckpt_dir)
    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load model & tokenizer ---
    print("Loading CrystaLLM components...")
    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)

    # Initialize tokenizer to get vocab info for padding
    tokenizer = CIFTokenizer()
    vocab_size = tokenizer.vocab_size  # vocab_size is a property, not a method
    PAD_TOKEN_ID = vocab_size - 1  # UNK token " " is the last token in vocab
    print(f"Tokenizer loaded: vocab_size={vocab_size}, PAD_TOKEN_ID={PAD_TOKEN_ID}")

    ckpt_path = ckpt_dir if os.path.isfile(ckpt_dir) else os.path.join(ckpt_dir, "ckpt.pt")
    ckpt = torch.load(ckpt_path, map_location=args.device)

    model = build_model(GPT, GPTConfig, ckpt, args.device)
    block_size = ckpt["model_args"].get("block_size", 1024)
    print(f"Model loaded: block_size={block_size}, vocab_size={ckpt['model_args'].get('vocab_size', '?')}")

    # --- Strategy: full fine-tuning or LoRA ---
    model.train()
    if args.strategy == "lora":
        for p in model.parameters():
            p.requires_grad_(False)
        target_names = tuple(n.strip() for n in args.lora_target_names.split(",") if n.strip())
        lora_params = inject_lora(model, rank=args.lora_rank, alpha=args.lora_alpha,
                                  target_names=target_names)
        trainable = lora_params
        print(f"LoRA injected: {len(lora_params)} adapter matrices, rank={args.lora_rank}, "
              f"targets={target_names}")
    else:
        trainable = list(model.parameters())

    total_trainable = sum(p.numel() for p in trainable)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"Strategy: {args.strategy} | Trainable: {total_trainable:,} / {total_params:,} params")

    opt = torch.optim.AdamW(trainable, lr=args.lr, betas=(0.9, 0.95),
                            weight_decay=args.weight_decay)

    # --- Load training data ---
    print(f"Loading training data from {args.data_jsonl}")
    data = []
    with open(args.data_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            token_ids = entry["token_ids"]
            # Ensure within block_size
            if len(token_ids) <= block_size:
                data.append(token_ids)
    if not data:
        raise RuntimeError("No training samples loaded.")
    print(f"Loaded {len(data)} training samples.")

    # --- Training log ---
    log_file = out_dir / "training_log.jsonl"
    log_fh = open(log_file, "w", encoding="utf-8")

    # --- Save hyperparams ---
    hparams = {
        "method": "sft",
        "lr": args.lr,
        "steps": args.steps,
        "batch_size": args.batch_size,
        "grad_accum_steps": args.grad_accum_steps,
        "effective_batch_size": args.batch_size * args.grad_accum_steps,
        "max_grad_norm": args.max_grad_norm,
        "strategy": args.strategy,
        "lora_rank": args.lora_rank if args.strategy == "lora" else None,
        "lora_alpha": args.lora_alpha if args.strategy == "lora" else None,
        "lora_target_names": args.lora_target_names if args.strategy == "lora" else None,
        "warmup_steps": args.warmup_steps,
        "weight_decay": args.weight_decay,
        "seed": args.seed,
        "num_samples": len(data),
        "trainable_params": total_trainable,
        "total_params": total_params,
        "block_size": block_size,
    }
    with open(out_dir / "hparams.json", "w", encoding="utf-8") as f:
        json.dump(hparams, f, indent=2)

    # --- Training loop ---
    rng = random.Random(args.seed)
    t0 = time.perf_counter()

    def make_shuffled_indices():
        idx = list(range(len(data)))
        rng.shuffle(idx)
        return idx

    def get_batch(batch_size):
        """Get a batch of token sequences with padding."""
        nonlocal data_ptr, epoch, data_idx

        batch_token_ids = []
        batch_actual_lengths = []

        for _ in range(batch_size):
            if data_ptr >= len(data_idx):
                epoch += 1
                data_idx = make_shuffled_indices()
                data_ptr = 0

            token_ids = data[data_idx[data_ptr]]
            data_ptr += 1
            batch_token_ids.append(token_ids)
            batch_actual_lengths.append(len(token_ids))

        # Find max length in batch for padding
        max_len = max(batch_actual_lengths)

        # Pad sequences to max length with PAD_TOKEN_ID (UNK token, must be a valid vocab index for CUDA)
        # Padding positions will be ignored via targets=-1 in the loss computation
        padded_x = []
        for token_ids in batch_token_ids:
            padded = token_ids + [PAD_TOKEN_ID] * (max_len - len(token_ids))
            padded_x.append(padded)

        return torch.tensor(padded_x, dtype=torch.long, device=args.device), batch_actual_lengths

    data_idx = make_shuffled_indices()
    data_ptr = 0
    epoch = 0

    opt.zero_grad()
    accum_loss = 0.0
    avg_loss = 0.0
    accum_count = 0
    best_loss = float("inf")
    best_step = 0

    print(f"\nStarting SFT training: {args.steps} steps, {len(data)} samples, "
          f"~{args.steps * args.batch_size / len(data):.1f} epochs")
    print(f"Batch size: {args.batch_size} | Grad accum: {args.grad_accum_steps} | "
          f"Effective batch size: {args.batch_size * args.grad_accum_steps}")
    print(f"LR: {args.lr}, Warmup: {args.warmup_steps}")
    print()

    for step in range(1, args.steps + 1):
        # --- Get next batch (with epoch cycling) ---
        x, batch_lengths = get_batch(args.batch_size)
        batch_max_len = x.shape[1]

        # --- Forward pass: standard cross-entropy ---
        # nanoGPT convention: targets must be pre-shifted (targets[i] = next token after idx[i])
        # The model computes: F.cross_entropy(logits, targets, ignore_index=-1)
        # Create targets by shifting left and masking padded positions
        targets = torch.full_like(x, -1)  # -1 is ignore_index
        for i, length in enumerate(batch_lengths):
            if length > 1:
                targets[i, :length-1] = x[i, 1:length]

        # Forward pass
        logits, _ = model(x, targets=targets)

        # Compute loss manually to properly handle masking
        # Flatten for cross_entropy
        logits_flat = logits.view(-1, logits.size(-1))
        targets_flat = targets.view(-1)

        # Compute loss (ignore_index=-1 handles padding)
        loss = F.cross_entropy(logits_flat, targets_flat, ignore_index=-1)

        (loss / args.grad_accum_steps).backward()
        accum_loss += loss.item()
        accum_count += 1

        # --- Optimizer step (every grad_accum_steps) ---
        if step % args.grad_accum_steps == 0 or step == args.steps:
            # LR schedule
            current_lr = cosine_lr(step, args.steps, args.lr, args.warmup_steps)
            for pg in opt.param_groups:
                pg["lr"] = current_lr

            # Gradient clipping
            grad_norm = torch.nn.utils.clip_grad_norm_(trainable, args.max_grad_norm).item()

            opt.step()
            opt.zero_grad()

            # Log
            avg_loss = accum_loss / accum_count if accum_count else 0
            elapsed = time.perf_counter() - t0
            avg_tokens = sum(batch_lengths) / len(batch_lengths)

            log_entry = {
                "step": step,
                "loss": round(avg_loss, 6),
                "lr": current_lr,
                "grad_norm": round(grad_norm, 4),
                "epoch": epoch,
                "elapsed_s": round(elapsed, 1),
                "n_tokens": avg_tokens,
                "batch_size": args.batch_size,
            }
            log_fh.write(json.dumps(log_entry) + "\n")
            log_fh.flush()

            if step % max(1, args.grad_accum_steps * 10) == 0 or step == args.steps:
                print(
                    f"step={step}/{args.steps} loss={avg_loss:.5f} "
                    f"lr={current_lr:.2e} gnorm={grad_norm:.3f} epoch={epoch} "
                    f"avg_tok={avg_tokens:.0f} [{elapsed:.0f}s]"
                )

            # Track best checkpoint by loss
            if avg_loss < best_loss:
                best_loss = avg_loss
                best_step = step
                sd_best = merge_lora_state_dict(model) if args.strategy == "lora" else model.state_dict()
                torch.save({"model_args": ckpt["model_args"], "model": sd_best}, out_dir / "best_ckpt.pt")

            accum_loss = 0.0
            accum_count = 0

        # --- Periodic checkpoint ---
        if args.save_every > 0 and step % args.save_every == 0 and step < args.steps:
            ckpt_step_dir = out_dir / f"step_{step}"
            ckpt_step_dir.mkdir(exist_ok=True)
            sd = merge_lora_state_dict(model) if args.strategy == "lora" else model.state_dict()
            save = {"model_args": ckpt["model_args"], "model": sd}
            torch.save(save, ckpt_step_dir / "ckpt.pt")
            print(f"  [checkpoint] Saved step {step} -> {ckpt_step_dir}")

    # --- Final save ---
    sd = merge_lora_state_dict(model) if args.strategy == "lora" else model.state_dict()
    save = {"model_args": ckpt["model_args"], "model": sd}
    final_ckpt = out_dir / "ckpt.pt"
    torch.save(save, final_ckpt)
    log_fh.close()

    total_time = time.perf_counter() - t0
    print(f"\nSFT training complete in {total_time:.1f}s ({total_time/3600:.1f}h)")
    print(f"  Final checkpoint: {final_ckpt}")
    if best_step > 0:
        print(f"  Best checkpoint:  {out_dir / 'best_ckpt.pt'} (step {best_step}, loss {best_loss:.5f})")
    else:
        print(f"  Best checkpoint:  not saved (no valid loss recorded)")
    print(f"  Training log: {log_file}")
    print(f"  Hyperparams: {out_dir / 'hparams.json'}")
    print(f"  Epochs completed: {epoch}")
    print(f"  Final loss: {avg_loss:.5f}")


if __name__ == "__main__":
    main()
