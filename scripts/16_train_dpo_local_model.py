import argparse
from pathlib import Path

import torch
from datasets import load_dataset
from transformers import GPT2Config, GPT2LMHeadModel, PreTrainedTokenizerFast
from trl import DPOTrainer, DPOConfig

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default="data/dpo_pairs/pairs.jsonl")
    ap.add_argument("--tok_dir", type=str, default="local_tokenizer")
    ap.add_argument("--out", type=str, default="outputs/dpo_local_smoke_01")
    ap.add_argument("--steps", type=int, default=3)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("json", data_files=args.data, split="train")

    tok_json = Path(args.tok_dir) / "tokenizer.json"
    tok = PreTrainedTokenizerFast(
        tokenizer_file=str(tok_json),
        unk_token="<unk>",
        bos_token="<s>",
        eos_token="</s>",
        pad_token="<pad>",
    )

    config = GPT2Config(
        vocab_size=tok.vocab_size,
        n_positions=256,
        n_ctx=256,
        n_embd=128,
        n_layer=2,
        n_head=2,
        bos_token_id=tok.bos_token_id,
        eos_token_id=tok.eos_token_id,
        pad_token_id=tok.pad_token_id,
    )

    model = GPT2LMHeadModel(config)
    ref_model = GPT2LMHeadModel(config)

    if torch.cuda.is_available():
        model = model.cuda()
        ref_model = ref_model.cuda()

    dpo_args = DPOConfig(
        output_dir=str(out_dir),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=5e-5,
        max_steps=args.steps,
        logging_steps=1,
        save_steps=2,
        fp16=False,
        report_to=[],
        remove_unused_columns=False,

        beta=0.1,
        max_length=256,
        max_prompt_length=128,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=ref_model,
        args=dpo_args,
        train_dataset=ds,
        tokenizer=tok,
    )

    trainer.train()
    trainer.save_model(str(out_dir / "final"))
    tok.save_pretrained(str(out_dir / "final"))
    print("Saved:", out_dir / "final")

if __name__ == "__main__":
    main()
