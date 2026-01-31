from pathlib import Path
from collections import Counter
from pymatgen.core import Structure

ROOT = Path("~/projects/crystallm-repro/reports/demo6_prompt_sweep_n200/processed/LiFePO4").expanduser()
models = ["baseline", "nacl_ft_small", "mix154_ft_small"]
target = "LiFePO4"

for m in models:
    d = ROOT / m
    if not d.exists():
        print(f"[MISS] {m}: {d} not found")
        continue
    cifs = sorted(d.glob("*.cif"))
    cnt = Counter()
    ok = 0
    for p in cifs:
        try:
            s = Structure.from_file(str(p))
            f = s.composition.reduced_formula
            cnt[f] += 1
            ok += 1
        except:
            cnt["__invalid__"] += 1
    print(f"\n=== {m} ===")
    print("total =", len(cifs), "parsed =", ok, "target_hits =", cnt.get(target, 0))
    print("top10 formulas:")
    for f, n in cnt.most_common(10):
        print(f"  {n:4d}  {f}")
