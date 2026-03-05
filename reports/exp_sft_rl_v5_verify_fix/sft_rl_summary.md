# SFT + RL (DPO) Pipeline — exp_sft_rl_v5_verify_fix Ablation Results

## Experiment Configuration

- **Experiment**: exp_sft_rl_v5_verify_fix
- **Targets**: LiFePO4 NaCl TiO2
- **Samples per target**: 120
- **SFT Branches**: lora64 full_ft
- **DPO**: steps=120, lr=5e-6, loss=dpo, beta=2.5
- **Reward weights (Plan B)**: proxy=0.70, geom=0.10, comp=0.10, novel=0.10
- **Reward-weighted DPO**: 1 (alpha=1.0)
- **Ehull reference**: Fallback-only (MP_API_KEY not set)

## Per-Branch Per-Target Results

| Target | Branch | Baseline Stability | SFT Stability | DPO Stability |
|--------|--------|-------------------|---------------|---------------|
| LiFePO4 | lora64 | 0.1333 | 0.1333 | 0.1333 |
| NaCl | lora64 | 0.0500 | 0.0500 | 0.0500 |
| TiO2 | lora64 | 0.0417 | 0.0417 | 0.0333 |
| LiFePO4 | full_ft | 0.1333 | 0.1333 | 0.1417 |
| NaCl | full_ft | 0.0500 | 0.0500 | 0.0500 |
| TiO2 | full_ft | 0.0417 | 0.0417 | 0.0417 |

Generated at: 2026年 03月 02日 星期一 09:38:52 CST
