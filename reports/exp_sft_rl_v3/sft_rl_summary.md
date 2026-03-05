# SFT + RL (DPO) Pipeline — exp_sft_rl_v3 Ablation Results

## Experiment Configuration

- **Experiment**: exp_sft_rl_v3
- **Targets**: LiFePO4 NaCl TiO2
- **Samples per target**: 2000
- **SFT Branches**: full_ft lora64
- **DPO**: steps=2000, lr=1e-7, loss=dpo, beta=2.5
- **Reward weights**: energy=0.4, structure=0.2, difficulty=0.2, composition=0.2
- **Reward-weighted DPO**: 1 (alpha=1.0)

## Per-Branch Per-Target Results

| Target | Branch | Baseline Stability | SFT Stability | DPO Stability |
|--------|--------|-------------------|---------------|---------------|
| LiFePO4 | full_ft | 0.1250 | 0.1260 | 0.1240 |
| NaCl | full_ft | 0.0505 | 0.0495 | 0.0485 |
| TiO2 | full_ft | 0.0510 | 0.0500 | 0.0510 |
| LiFePO4 | lora64 | 0.1250 | 0.1240 | 0.1240 |
| NaCl | lora64 | 0.0505 | 0.0505 | 0.0505 |
| TiO2 | lora64 | 0.0510 | 0.0485 | 0.0490 |

Generated at: 2026年 02月 24日 星期二 14:07:01 CST
