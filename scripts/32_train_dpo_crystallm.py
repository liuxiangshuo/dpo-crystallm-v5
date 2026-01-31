import argparse, json, os, sys, types, importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F

def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def load_crystallm_components(pkg_dir: Path):
    tok_mod = load_module(pkg_dir / "_tokenizer.py", "tok")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    mdl_mod = load_module(pkg_dir / "_model.py", "mdl")
    return tok_mod.CIFTokenizer, mdl_mod.GPT, mdl_mod.GPTConfig

def clean_state_dict(sd: dict):
    unwanted = "_orig_mod."
    if any(k.startswith(unwanted) for k in sd.keys()):
        return { (k[len(unwanted):] if k.startswith(unwanted) else k): v for k, v in sd.items() }
    return sd

def build_model(GPT, GPTConfig, ckpt: dict, device: str):
    conf = GPTConfig(**ckpt["model_args"])
    m = GPT(conf).to(device)
    m.load_state_dict(clean_state_dict(ckpt["model"]))
    return m

def get_full_logits(model, x: torch.Tensor):
    # force full-seq logits by passing targets like nanoGPT
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
    x = torch.tensor(token_ids, dtype=torch.long, device=device).unsqueeze(0)  # [1,T]
    logits = get_full_logits(model, x)  # [1,T,V]
    logprobs = F.log_softmax(logits, dim=-1)
    tgt = x[:, 1:]
    lp = logprobs[:, :-1, :].gather(-1, tgt.unsqueeze(-1)).squeeze(-1)  # [1,T-1]
    start = max(0, prompt_len - 1)
    return lp[:, start:].sum()

def encode_text(tokenizer, text: str):
    return tokenizer.encode(tokenizer.tokenize_cif(text))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/dpo_pairs/pairs_phase3_LiFePO4_many.jsonl")
    ap.add_argument("--ckpt_dir", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm_v1_small")
    ap.add_argument("--pkg_dir", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm")
    ap.add_argument("--out_dir", default="out/dpo_lifepo4_small")
    ap.add_argument("--steps", type=int, default=10)
    ap.add_argument("--beta", type=float, default=0.1)
    ap.add_argument("--lr", type=float, default=1e-6)
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

    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)
    tokenizer = CIFTokenizer()

    ckpt = torch.load(os.path.join(ckpt_dir, "ckpt.pt"), map_location=args.device)

    policy = build_model(GPT, GPTConfig, ckpt, args.device).train()
    ref = build_model(GPT, GPTConfig, ckpt, args.device).eval()
    for p in ref.parameters():
        p.requires_grad_(False)

    opt = torch.optim.AdamW(policy.parameters(), lr=args.lr)

    pairs = [json.loads(x) for x in Path(args.pairs).read_text(encoding="utf-8").splitlines()]
    if not pairs:
        raise RuntimeError("No pairs loaded.")

    for step in range(1, args.steps + 1):
        ex = pairs[(step - 1) % len(pairs)]
        prompt = ex["prompt"]
        chosen = ex["chosen"]
        rejected = ex["rejected"]

        prompt_ids = encode_text(tokenizer, prompt + "\n")
        chosen_ids = encode_text(tokenizer, prompt + "\n" + chosen)
        rejected_ids = encode_text(tokenizer, prompt + "\n" + rejected)

        # policy logps (WITH grad)
        lp_c = logp_sequence(policy, chosen_ids, len(prompt_ids), args.device)
        lp_r = logp_sequence(policy, rejected_ids, len(prompt_ids), args.device)

        # ref logps (NO grad)
        with torch.no_grad():
            lpr_c = logp_sequence(ref, chosen_ids, len(prompt_ids), args.device)
            lpr_r = logp_sequence(ref, rejected_ids, len(prompt_ids), args.device)

        adv = (lp_c - lp_r) - (lpr_c - lpr_r)
        loss = -F.logsigmoid(args.beta * adv)

        opt.zero_grad()
        loss.backward()
        opt.step()

        print(f"step={step} loss={loss.item():.6f} adv={adv.item():.3f} piΔ={(lp_c-lp_r).item():.3f} refΔ={(lpr_c-lpr_r).item():.3f}")

    save = {
        "model_args": ckpt["model_args"],
        "model": policy.state_dict(),
    }
    out_ckpt = out_dir / "ckpt.pt"
    torch.save(save, out_ckpt)
    print("Saved:", out_ckpt)

if __name__ == "__main__":
    main()
