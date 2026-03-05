# SFT + RL (DPO) Two-Stage Pipeline Results

## Experiment Configuration

- **Experiment**: exp_sft_rl
- **Targets**: LiFePO4 NaCl TiO2 BaTiO3
- **Samples per target**: 10000
- **SFT**: steps=6000, lr=5e-8, strategy=lora
- **DPO**: steps=4000, lr=1e-7, loss=dpo, beta=2.5
- **Reward weights**: energy=0.4, structure=0.2, difficulty=0.2, composition=0.2
- **Reward-weighted DPO**: 1 (alpha=1.0)

## Per-Target Results

See individual reports in `reports/exp_sft_rl/<target>/` for detailed comparisons.

| Target | Baseline Stability | SFT+DPO Stability | Change |
|--------|-------------------|-------------------|--------|
| LiFePO4 | 0.1276 | 0.1239 | - |
| NaCl | 0.0563 | 0.0578 | - |
| TiO2 | 0.0512 | 0.0582 | - |
| BaTiO3 | N/A | SKIPPED (0 on-target compositions) | - |

Generated at: 2026年 02月 21日 星期六 08:53:10 CST
