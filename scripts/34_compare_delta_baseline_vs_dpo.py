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
    m = GPT(conf).to(device).eval()
    m.load_state_dict(clean_state_dict(ckpt["model"]))
    return m

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

@torch.no_grad()
def logp_sequence(model, token_ids, prompt_len: int, device: str):
    x = torch.tensor(token_ids, dtype=torch.long, device=device).unsqueeze(0)
    logits = get_full_logits(model, x)
    logprobs = F.log_softmax(logits, dim=-1)
    tgt = x[:, 1:]
    lp = logprobs[:, :-1, :].gather(-1, tgt.unsqueeze(-1)).squeeze(-1)
    start = max(0, prompt_len - 1)
    return lp[:, start:].sum().item()

def encode_text(tokenizer, text: str):
    return tokenizer.encode(tokenizer.tokenize_cif(text))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="data/dpo_pairs/pairs_phase3_LiFePO4_many.jsonl")
    ap.add_argument("--index", type=int, default=0)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--pkg_dir", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm")
    ap.add_argument("--baseline_ckpt", default="~/projects/crystallm-repro/external/CrystaLLM/crystallm_v1_small/ckpt.pt")
    ap.add_argument("--dpo_ckpt", default="out/dpo_lifepo4_small/ckpt.pt")
    args = ap.parse_args()

    pkg_dir = Path(os.path.expanduser(args.pkg_dir))
    CIFTokenizer, GPT, GPTConfig = load_crystallm_components(pkg_dir)
    tokenizer = CIFTokenizer()

    ex = json.loads(Path(args.pairs).read_text(encoding="utf-8").splitlines()[args.index])
    prompt = ex["prompt"]
    chosen = ex["chosen"]
    rejected = ex["rejected"]

    prompt_ids = encode_text(tokenizer, prompt + "\n")
    chosen_ids = encode_text(tokenizer, prompt + "\n" + chosen)
    rejected_ids = encode_text(tokenizer, prompt + "\n" + rejected)

    base = torch.load(os.path.expanduser(args.baseline_ckpt), map_location=args.device)
    dpo = torch.load(os.path.expanduser(args.dpo_ckpt), map_location=args.device)

    m_base = build_model(GPT, GPTConfig, base, args.device)
    m_dpo  = build_model(GPT, GPTConfig, dpo,  args.device)

    dc_base = logp_sequence(m_base, chosen_ids, len(prompt_ids), args.device)
    dr_base = logp_sequence(m_base, rejected_ids, len(prompt_ids), args.device)
    dc_dpo  = logp_sequence(m_dpo,  chosen_ids, len(prompt_ids), args.device)
    dr_dpo  = logp_sequence(m_dpo,  rejected_ids, len(prompt_ids), args.device)

    print("pair:", ex.get("chosen_file"), "vs", ex.get("rejected_file"))
    print("baseline delta:", dc_base - dr_base)
    print("dpo delta     :", dc_dpo - dr_dpo)
    print("delta change  :", (dc_dpo - dr_dpo) - (dc_base - dr_base))

if __name__ == "__main__":
    main()
