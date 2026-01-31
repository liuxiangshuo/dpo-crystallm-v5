import json
from pathlib import Path
from tokenizers import ByteLevelBPETokenizer

def main():
    data_path = Path("data/dpo_pairs/pairs.jsonl")
    out_dir = Path("local_tokenizer")
    out_dir.mkdir(parents=True, exist_ok=True)

    corpus = out_dir / "corpus.txt"
    with corpus.open("w", encoding="utf-8") as w:
        for line in data_path.read_text(encoding="utf-8").splitlines():
            ex = json.loads(line)
            w.write(ex["prompt"] + "\n")
            w.write(ex["chosen"] + "\n")
            w.write(ex["rejected"] + "\n")

    tok = ByteLevelBPETokenizer()
    tok.train(
        files=[str(corpus)],
        vocab_size=2000,
        min_frequency=1,
        special_tokens=["<pad>", "<s>", "</s>", "<unk>"],
    )

    # Save both classic files and the unified tokenizer.json
    tok.save_model(str(out_dir))
    tok._tokenizer.save(str(out_dir / "tokenizer.json"))

    print("Saved:", out_dir / "tokenizer.json")

if __name__ == "__main__":
    main()
