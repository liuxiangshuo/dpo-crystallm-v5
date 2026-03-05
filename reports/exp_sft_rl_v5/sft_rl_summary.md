# SFT + RL (DPO) Pipeline — exp_sft_rl_v5 Ablation Results

## Experiment Configuration

- **Experiment**: exp_sft_rl_v5
- **Targets**: LiFePO4 NaCl TiO2
- **Samples per target**: 2000
- **SFT Branches**: lora64 full_ft
- **DPO**: steps=12000, lr=5e-6, loss=dpo, beta=2.5
- **Reward weights (Plan B)**: proxy=0.70, geom=0.10, comp=0.10, novel=0.10
- **Reward-weighted DPO**: 1 (alpha=1.0)
- **Ehull reference**: Fallback-only (MP_API_KEY not set)

## Per-Branch Per-Target Results

| Target | Branch | Baseline Stability | SFT Stability | DPO Stability |
|--------|--------|-------------------|---------------|---------------|
| LiFePO4 | lora64 | 0.1250 | 0.1230 | 0.1235 |
| NaCl | lora64 | 0.0505 | 0.0500 | 0.0330 |
| TiO2 | lora64 | 0.0510 | 0.0490 | 0.0530 |
| LiFePO4 | full_ft | 0.1250 | 0.1072 | 0.1015 |
| NaCl | full_ft | 0.0505 | 0.0444 | 0.0473 |
| TiO2 | full_ft | 0.0510 | 0.0468 | 0.0607 |

Generated at: 2026年 03月 04日 星期三 23:36:26 CST
