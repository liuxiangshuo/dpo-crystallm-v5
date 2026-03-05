#!/usr/bin/env python3
"""
DPO training for CrystaLLM.

Supports:
  - Multiple loss types (--loss_type):
      * dpo   — standard DPO (Rafailov et al. 2023)
      * cdpo  — conservative DPO with label smoothing (Mitchell 2023)
      * simpo — reference-free SimPO with length-normalized reward (Meng et al. 2024)
  - Gradient accumulation (--grad_accum_steps)
  - Gradient clipping (--max_grad_norm)
  - Periodic checkpointing (--save_every)
  - Training log in JSONL (training_log.jsonl)
  - Cosine warmup LR schedule
  - Optional LoRA injection (--strategy lora)
  - Data shuffling per epoch
  - Frozen reference model (pi_ref) — skipped for SimPO
"""
import argparse, json, math, os, sys, time, types, importlib.util, copy
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


def resolve_ckpt_path(ckpt_arg: str) -> str:
    """Resolve --ckpt_dir as either a checkpoint file path or checkpoint directory."""
    ckpt_input = os.path.expanduser(ckpt_arg)
    ckpt_path_obj = Path(ckpt_input)

    # Caller passed an explicit checkpoint file path.
    if ckpt_path_obj.suffix == ".pt":
        if not ckpt_path_obj.exists():
            raise FileNotFoundError(
                f"--ckpt_dir points to checkpoint file but it does not exist: {ckpt_path_obj}"
            )
        if not ckpt_path_obj.is_file():
            raise FileNotFoundError(
                f"--ckpt_dir points to checkpoint path but it is not a file: {ckpt_path_obj}"
            )
        return str(ckpt_path_obj)

    # Caller passed a directory path; look for ckpt.pt under it.
    if not ckpt_path_obj.exists():
        raise FileNotFoundError(
            f"--ckpt_dir directory does not exist: {ckpt_path_obj}"
        )
    if not ckpt_path_obj.is_dir():
        raise FileNotFoundError(
            f"--ckpt_dir must be a directory or *.pt file: {ckpt_path_obj}"
        )
    default_ckpt = ckpt_path_obj / "ckpt.pt"
    if not default_ckpt.exists():
        raise FileNotFoundError(
            f"Checkpoint file not found in directory: {default_ckpt}"
        )
    return str(default_ckpt)


# ---------------------------------------------------------------------------
# LoRA injection (using shared module)
# ---------------------------------------------------------------------------

# Import LoRA utilities from shared module
sys.path.insert(0, str(Path(__file__).parent))
from shared.lora_utils import LoRALinear, inject_lora, merge_lora_state_dict


# ---------------------------------------------------------------------------
# Core DPO utilities
# ---------------------------------------------------------------------------

def get_full_logits(model, x: torch.Tensor):
    try:
        out = model(x, targets=x)
    except TypeError:
        try:
            out = model(x, x)
        except TypeError:
            out = model(x)
    if isinstance(out, (tuple, list)):
        return out[0]
    if hasattr(out, "logits"):
        return out.logits
    return out


def logp_sequence(model, token_ids, prompt_len: int, device: str):
    """Sum of log-probs over completion tokens (for DPO / cDPO)."""
    x = torch.tensor(token_ids, dtype=torch.long, device=device).unsqueeze(0)
    logits = get_full_logits(model, x)
    logprobs = F.log_softmax(logits, dim=-1)
    tgt = x[:, 1:]
    lp = logprobs[:, :-1, :].gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    start = max(0, prompt_len - 1)
    return lp[:, start:].sum()


def logp_sequence_avg(model, token_ids, prompt_len: int, device: str):
    """Average log-prob per completion token (for SimPO).

    SimPO uses length-normalized average log-prob as the implicit reward,
    preventing bias toward shorter/longer sequences.
    """
    x = torch.tensor(token_ids, dtype=torch.long, device=device).unsqueeze(0)
    logits = get_full_logits(model, x)
    logprobs = F.log_softmax(logits, dim=-1)
    tgt = x[:, 1:]
    lp = logprobs[:, :-1, :].gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    start = max(0, prompt_len - 1)
    completion_lp = lp[:, start:]
    n_tokens = max(completion_lp.shape[1], 1)
    return completion_lp.sum() / n_tokens


def encode_text(tokenizer, text: str):
    return tokenizer.encode(tokenizer.tokenize_cif(text))


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
    ap = argparse.ArgumentParser(description="DPO training for CrystaLLM")
    ap.add_argument("--pairs", required=True, help="JSONL file with prompt/chosen/rejected")
    ap.add_argument("--ckpt_dir", required=True, help="Baseline checkpoint dir or ckpt.pt")
    ap.add_argument("--pkg_dir", required=True, help="CrystaLLM package dir")
    ap.add_argument("--out_dir", required=True, help="Output directory for checkpoints")
    ap.add_argument("--steps", type=int, default=2000, help="Total training steps")
    ap.add_argument("--beta", type=float, default=2.5, help="DPO beta (KL penalty). Uses per-token avg log-prob; typical range 2.0-5.0")
    ap.add_argument("--lr", type=float, default=1e-6, help="Peak learning rate")
    ap.add_argument("--grad_accum_steps", type=int, default=8, help="Gradient accumulation steps")
    ap.add_argument("--max_grad_norm", type=float, default=1.0, help="Max gradient norm for clipping")
    ap.add_argument("--save_every", type=int, default=500, help="Save checkpoint every N steps")
    ap.add_argument("--warmup_steps", type=int, default=100, help="LR warmup steps")
    ap.add_argument("--strategy", default="full", choices=["full", "lora"], help="Training strategy")
    ap.add_argument("--lora_rank", type=int, default=16, help="LoRA rank (if strategy=lora)")
    ap.add_argument("--lora_alpha", type=int, default=32, help="LoRA alpha (if strategy=lora)")
    ap.add_argument("--loss_type", default="dpo", choices=["dpo", "cdpo", "simpo"],
                    help="Loss function: dpo (standard), cdpo (conservative/label-smoothing), simpo (reference-free)")
    ap.add_argument("--label_smoothing", type=float, default=0.1,
                    help="Label smoothing epsilon for cDPO (probability of label flip)")
    ap.add_argument("--simpo_gamma", type=float, default=1.0,
                    help="Reward margin gamma for SimPO")
    ap.add_argument("--reward_weighted", action="store_true",
                    help="Enable reward-weighted DPO: loss = -log sigmoid(beta*adv + alpha*(r_c - r_r)). "
                         "Requires 'chosen_reward' and 'rejected_reward' fields in pair JSONL.")
    ap.add_argument("--reward_alpha", type=float, default=1.0,
                    help="Scaling factor for reward margin in reward-weighted DPO")
    ap.add_argument("--weight_decay", type=float, default=0.01,
                    help="AdamW weight decay (default 0.01)")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--seed", type=int, default=123)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    if "cuda" in args.device:
        torch.cuda.manual_seed(args.seed)

    ckpt_dir = os.path.expanduser(args.ckpt_dir)
    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- Load model & tokenizer ---
    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)
    tokenizer = CIFTokenizer()

    ckpt_path = resolve_ckpt_path(ckpt_dir)
    ckpt = torch.load(ckpt_path, map_location=args.device)

    policy = build_model(GPT, GPTConfig, ckpt, args.device)

    # SimPO is reference-free — skip loading ref model to save memory
    if args.loss_type != "simpo":
        ref = build_model(GPT, GPTConfig, ckpt, args.device).eval()
        for p in ref.parameters():
            p.requires_grad_(False)
    else:
        ref = None
        print(f"SimPO mode: no reference model loaded (saves ~50% GPU memory)")

    # --- Strategy: full fine-tuning or LoRA ---
    policy.train()
    if args.strategy == "lora":
        for p in policy.parameters():
            p.requires_grad_(False)
        lora_params = inject_lora(policy, rank=args.lora_rank, alpha=args.lora_alpha)
        trainable = lora_params
        print(f"LoRA injected: {len(lora_params)} adapter matrices, rank={args.lora_rank}")
    else:
        trainable = list(policy.parameters())

    total_trainable = sum(p.numel() for p in trainable)
    total_params = sum(p.numel() for p in policy.parameters())
    print(f"Strategy: {args.strategy} | Trainable: {total_trainable:,} / {total_params:,} params")

    opt = torch.optim.AdamW(trainable, lr=args.lr, betas=(0.9, 0.95), weight_decay=args.weight_decay)

    # --- Load data ---
    pairs = [json.loads(x) for x in Path(args.pairs).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not pairs:
        raise RuntimeError("No pairs loaded.")
    print(f"Loaded {len(pairs)} preference pairs.")

    # --- Training log ---
    log_file = out_dir / "training_log.jsonl"
    log_fh = open(log_file, "w", encoding="utf-8")

    # --- Save hyperparams ---
    print(f"Loss type: {args.loss_type}" +
          (f" (label_smoothing={args.label_smoothing})" if args.loss_type == "cdpo" else "") +
          (f" (gamma={args.simpo_gamma})" if args.loss_type == "simpo" else ""))

    hparams = {
        "beta": args.beta,
        "lr": args.lr,
        "steps": args.steps,
        "grad_accum_steps": args.grad_accum_steps,
        "max_grad_norm": args.max_grad_norm,
        "weight_decay": args.weight_decay,
        "strategy": args.strategy,
        "loss_type": args.loss_type,
        "label_smoothing": args.label_smoothing if args.loss_type == "cdpo" else None,
        "simpo_gamma": args.simpo_gamma if args.loss_type == "simpo" else None,
        "reward_weighted": args.reward_weighted,
        "reward_alpha": args.reward_alpha if args.reward_weighted else None,
        "lora_rank": args.lora_rank if args.strategy == "lora" else None,
        "lora_alpha": args.lora_alpha if args.strategy == "lora" else None,
        "warmup_steps": args.warmup_steps,
        "seed": args.seed,
        "num_pairs": len(pairs),
        "trainable_params": total_trainable,
        "total_params": total_params,
    }
    with open(out_dir / "hparams.json", "w", encoding="utf-8") as f:
        json.dump(hparams, f, indent=2)

    # --- Training loop ---
    import random
    rng = random.Random(args.seed)
    t0 = time.perf_counter()

    # Build epoch-shuffled index
    def make_shuffled_indices():
        idx = list(range(len(pairs)))
        rng.shuffle(idx)
        return idx

    data_idx = make_shuffled_indices()
    data_ptr = 0
    epoch = 0

    opt.zero_grad()
    accum_loss = 0.0
    accum_adv = 0.0
    accum_count = 0
    best_loss = float("inf")
    best_step = 0

    for step in range(1, args.steps + 1):
        # --- Get next pair (with epoch cycling) ---
        if data_ptr >= len(data_idx):
            epoch += 1
            data_idx = make_shuffled_indices()
            data_ptr = 0
        ex = pairs[data_idx[data_ptr]]
        data_ptr += 1

        prompt = ex["prompt"]
        chosen = ex["chosen"]
        rejected = ex["rejected"]

        prompt_ids = encode_text(tokenizer, prompt + "\n")
        chosen_ids = encode_text(tokenizer, prompt + "\n" + chosen)
        rejected_ids = encode_text(tokenizer, prompt + "\n" + rejected)

        # ---- Reward margin (optional) ----
        # When --reward_weighted is set, add alpha * (r_chosen - r_rejected) to the
        # logit inside the sigmoid.  This injects external reward signal directly
        # into the DPO objective, acting as a data-dependent regulariser.
        reward_margin = 0.0
        if args.reward_weighted:
            r_c = float(ex.get("chosen_reward", 0.0) or 0.0)
            r_r = float(ex.get("rejected_reward", 0.0) or 0.0)
            reward_margin = args.reward_alpha * (r_c - r_r)

        # ---- Compute loss based on loss_type ----
        # NOTE: All variants use per-token average log-prob (logp_sequence_avg)
        # to prevent numerical explosion on long CIF sequences (~560 tokens).
        if args.loss_type == "simpo":
            # SimPO (Meng et al. 2024): reference-free, length-normalized average log-prob
            # Loss: -log σ(β * (avg_logp_chosen - avg_logp_rejected) - γ)
            # where γ is the reward margin that enforces chosen to be better than rejected by at least γ
            lp_c = logp_sequence_avg(policy, chosen_ids, len(prompt_ids), args.device)
            lp_r = logp_sequence_avg(policy, rejected_ids, len(prompt_ids), args.device)
            adv = lp_c - lp_r
            # Implementation matches paper: beta * (lp_c - lp_r) - gamma
            loss = -F.logsigmoid(args.beta * adv - args.simpo_gamma + reward_margin) / args.grad_accum_steps
        else:
            # DPO / cDPO: need reference model (using per-token avg log-prob)
            lp_c = logp_sequence_avg(policy, chosen_ids, len(prompt_ids), args.device)
            lp_r = logp_sequence_avg(policy, rejected_ids, len(prompt_ids), args.device)
            with torch.no_grad():
                lpr_c = logp_sequence_avg(ref, chosen_ids, len(prompt_ids), args.device)
                lpr_r = logp_sequence_avg(ref, rejected_ids, len(prompt_ids), args.device)
            adv = (lp_c - lp_r) - (lpr_c - lpr_r)

            if args.loss_type == "cdpo":
                # cDPO: label-smoothed loss for noisy preferences
                eps = args.label_smoothing
                loss = (-(1 - eps) * F.logsigmoid(args.beta * adv + reward_margin)
                        - eps * F.logsigmoid(-args.beta * adv - reward_margin)) / args.grad_accum_steps
            else:
                # Standard DPO (optionally reward-weighted)
                loss = -F.logsigmoid(args.beta * adv + reward_margin) / args.grad_accum_steps

        loss.backward()
        accum_loss += loss.item() * args.grad_accum_steps
        accum_adv += adv.item()
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
            avg_adv = accum_adv / accum_count if accum_count else 0
            elapsed = time.perf_counter() - t0

            n_tok_c = max(len(chosen_ids) - len(prompt_ids), 1)
            n_tok_r = max(len(rejected_ids) - len(prompt_ids), 1)
            log_entry = {
                "step": step,
                "loss": round(avg_loss, 6),
                "adv": round(avg_adv, 4),
                "pi_delta": round((lp_c - lp_r).item(), 4),
                "lr": current_lr,
                "grad_norm": round(grad_norm, 4),
                "epoch": epoch,
                "elapsed_s": round(elapsed, 1),
                "n_tok_c": n_tok_c,
                "n_tok_r": n_tok_r,
            }
            if args.loss_type != "simpo":
                log_entry["ref_delta"] = round((lpr_c - lpr_r).item(), 4)
            if args.reward_weighted:
                log_entry["reward_margin"] = round(reward_margin, 4)
            log_fh.write(json.dumps(log_entry) + "\n")
            log_fh.flush()

            if step % max(1, args.grad_accum_steps * 10) == 0 or step == args.steps:
                print(
                    f"step={step}/{args.steps} loss={avg_loss:.5f} adv={avg_adv:.3f} "
                    f"lr={current_lr:.2e} gnorm={grad_norm:.3f} epoch={epoch} "
                    f"[{elapsed:.0f}s]"
                )

            # Track best checkpoint by loss
            if avg_loss < best_loss:
                best_loss = avg_loss
                best_step = step
                sd_best = merge_lora_state_dict(policy) if args.strategy == "lora" else policy.state_dict()
                torch.save({"model_args": ckpt["model_args"], "model": sd_best}, out_dir / "best_ckpt.pt")

            accum_loss = 0.0
            accum_adv = 0.0
            accum_count = 0

        # --- Periodic checkpoint ---
        if args.save_every > 0 and step % args.save_every == 0 and step < args.steps:
            ckpt_step_dir = out_dir / f"step_{step}"
            ckpt_step_dir.mkdir(exist_ok=True)
            sd = merge_lora_state_dict(policy) if args.strategy == "lora" else policy.state_dict()
            save = {"model_args": ckpt["model_args"], "model": sd}
            torch.save(save, ckpt_step_dir / "ckpt.pt")
            print(f"  [checkpoint] Saved step {step} -> {ckpt_step_dir}")

    # --- Final save ---
    sd = merge_lora_state_dict(policy) if args.strategy == "lora" else policy.state_dict()
    save = {"model_args": ckpt["model_args"], "model": sd}
    final_ckpt = out_dir / "ckpt.pt"
    torch.save(save, final_ckpt)
    log_fh.close()

    total_time = time.perf_counter() - t0
    print(f"\nTraining complete in {total_time:.1f}s")
    print(f"  Final checkpoint: {final_ckpt}")
    if best_step > 0:
        print(f"  Best checkpoint:  {out_dir / 'best_ckpt.pt'} (step {best_step}, loss {best_loss:.5f})")
    else:
        print(f"  Best checkpoint:  not saved (no valid loss recorded)")
    print(f"  Training log: {log_file}")
    print(f"  Hyperparams: {out_dir / 'hparams.json'}")


if __name__ == "__main__":
    main()
