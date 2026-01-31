import argparse, json, os, sys, types, importlib.util
from pathlib import Path
import torch
import torch.nn.functional as F

def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod

def load_crystallm_components(crystallm_root: Path):
    tok_mod = load_module(crystallm_root / "_tokenizer.py", "crystallm_tokenizer_file")
    stub = types.ModuleType("crystallm")
    stub.CIFTokenizer = tok_mod.CIFTokenizer
    sys.modules["crystallm"] = stub
    mdl_mod = load_module(crystallm_root / "_model.py", "crystallm_model_file")
    return tok_mod.CIFTokenizer, mdl_mod.GPT, mdl_mod.GPTConfig

def load_model(GPT, GPTConfig, ckpt_dir: str, device: str):
    ckpt_path = os.path.join(ckpt_dir, "ckpt.pt")
    checkpoint = torch.load(ckpt_path, map_location=device)
    gptconf = GPTConfig(**checkpoint["model_args"])
    model = GPT(gptconf)

    state_dict = checkpoint["model"]
    unwanted_prefix = "_orig_mod."
    for k, v in list(state_dict.items()):
        if k.startswith(unwanted_prefix):
            state_dict[k[len(unwanted_prefix):]] = state_dict.pop(k)
    model.load_state_dict(state_dict)

    model.eval()
    model.to(device)
    return model

@torch.no_grad()
def get_full_logits(model, x: torch.Tensor):
    """
    CrystaLLM/nanoGPT-style models often return only last-token logits when targets=None.
    Passing targets forces full-sequence logits.
    """
    try:
        out = model(x, targets=x)
    except TypeError:
        try:
            out = model(x, x)
        except TypeError:
            out = model(x)

    if isinstance(out, (tuple, list)):
        logits = out[0]
    elif hasattr(out, "logits"):
        logits = out.logits
    else:
        logits = out

    return logits

@torch.no_grad()
def logp_sequence(model, token_ids, prompt_len: int, device: str):
    x = torch.tensor(token_ids, dtype=torch.long, device=device).unsqueeze(0)  # [1,T]
    logits = get_full_logits(model, x)  # want [1,T,V]
    if logits.shape[1] != x.shape[1]:
        raise RuntimeError(f"Expected full logits length {x.shape[1]}, got {logits.shape[1]}")

    logprobs = F.log_softmax(logits, dim=-1)
    tgt = x[:, 1:]  # [1,T-1]
    lp = logprobs[:, :-1, :].gather(-1, tgt.unsqueeze(-1)).squeeze(-1)  # [1,T-1]

    start = max(0, prompt_len - 1)
    return lp[:, start:].sum().item()

def encode_text(tokenizer, text: str):
    return tokenizer.encode(tokenizer.tokenize_cif(text))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/dpo_pairs/pairs_phase3_LiFePO4_many.jsonl")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--ckpt_dir", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm_v1_small")
    ap.add_argument("--crystallm_pkg_dir", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm")
    args = ap.parse_args()

    ckpt_dir = os.path.expanduser(args.ckpt_dir)
    pkg_dir = Path(os.path.expanduser(args.crystallm_pkg_dir))

    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)
    tokenizer = CIFTokenizer()
    model = load_model(GPT, GPTConfig, ckpt_dir, args.device)

    lines = Path(args.pairs).read_text(encoding="utf-8").splitlines()
    ex = json.loads(lines[args.index])

    prompt = ex["prompt"]
    chosen = ex["chosen"]
    rejected = ex["rejected"]

    prompt_ids = encode_text(tokenizer, prompt + "\n")
    chosen_ids = encode_text(tokenizer, prompt + "\n" + chosen)
    rejected_ids = encode_text(tokenizer, prompt + "\n" + rejected)

    lp_c = logp_sequence(model, chosen_ids, prompt_len=len(prompt_ids), device=args.device)
    lp_r = logp_sequence(model, rejected_ids, prompt_len=len(prompt_ids), device=args.device)

    print("prompt:", prompt)
    print("chosen_file:", ex.get("chosen_file"))
    print("rejected_file:", ex.get("rejected_file"))
    print("chosen_score:", ex.get("chosen_score"))
    print("rejected_score:", ex.get("rejected_score"))
    print("logp(chosen)  =", lp_c)
    print("logp(rejected)=", lp_r)
    print("delta (c-r)   =", lp_c - lp_r)

if __name__ == "__main__":
    main()
