import argparse
from pathlib import Path
from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from trl import DPOTrainer

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=str, default="data/dpo_pairs/pairs.jsonl")
    ap.add_argument("--model", type=str, default="gpt2")
    ap.add_argument("--out", type=str, default="outputs/dpo_smoke")
    ap.add_argument("--steps", type=int, default=20)
    args = ap.parse_args()

    data_path = Path(args.data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    ds = load_dataset("json", data_files=str(data_path), split="train")

    tok = AutoTokenizer.from_pretrained(args.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    model = AutoModelForCausalLM.from_pretrained(args.model)
    ref_model = AutoModelForCausalLM.from_pretrained(args.model)

    training_args = TrainingArguments(
        output_dir=str(out_dir),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=1,
        learning_rate=5e-6,
        max_steps=args.steps,
        logging_steps=1,
        save_steps=10,
        fp16=False,  # keep simple; can switch later
        report_to=[],
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=ref_model,
        args=training_args,
        train_dataset=ds,
        tokenizer=tok,
        beta=0.1,
        max_length=512,
        max_prompt_length=128,
    )

    trainer.train()
    trainer.save_model(str(out_dir / "final"))
    tok.save_pretrained(str(out_dir / "final"))
    print("Saved:", out_dir / "final")

if __name__ == "__main__":
    main()
