# SFT + RL (DPO) Two-Stage Pipeline Results

## Experiment Configuration

- **Experiment**: exp_sft_rl_smoke
- **Targets**: LiFePO4 NaCl
- **Samples per target**: 100
- **SFT**: steps=50, lr=5e-8, strategy=full
- **DPO**: steps=50, lr=1e-7, loss=dpo, beta=2.5
- **Reward weights**: energy=0.4, structure=0.2, difficulty=0.2, composition=0.2
- **Reward-weighted DPO**: 1 (alpha=1.0)

## Per-Target Results

See individual reports in `reports/exp_sft_rl_smoke/<target>/` for detailed comparisons.

| Target | Baseline Stability | SFT+DPO Stability | Change |
|--------|-------------------|-------------------|--------|
| LiFePO4 | 0.1500 | 0.1500 | - |
| NaCl | 0.0500 | 0.0700 | - |

Generated at: 2026年 02月 15日 星期日 22:03:07 CST
