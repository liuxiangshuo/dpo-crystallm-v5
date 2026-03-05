# DPO Ablation Study: LiFePO4

## Experiment Variants

| Variant | Loss | Beta | LR | Steps | Label Smoothing | SimPO Gamma |
|---------|------|------|----|-------|----------------|-------------|
| exp_final_50k | dpo | 0.1 | 5e-07 | 2000 | - | - |
| exp_ablation_dpo | dpo | 2.5 | 1e-07 | 8000 | None | None |
| exp_ablation_cdpo | cdpo | 2.5 | 1e-07 | 8000 | 0.1 | None |
| exp_ablation_simpo | simpo | 2.0 | 1e-07 | 8000 | None | 1.0 |

## Results Comparison

| Model | Validity | Stability (Ehull<0.05) | Hit Rate | Energy Mean | Energy Median |
|-------|----------|----------------------|----------|-------------|---------------|
| exp_final_50k/baseline | 1.0000 | 0.1212 | 0.5575 | -4.408218 | -5.171051 |
| exp_final_50k/dpo | 1.0000 | 0.1227 | 0.5532 | -4.407494 | -5.178731 |
| exp_ablation_dpo/baseline | 1.0000 | 0.1212 | 0.5575 | -4.408218 | -5.171051 |
| exp_ablation_dpo/dpo | 1.0000 | 0.1216 | 0.5582 | -4.404650 | -5.172206 |
| exp_ablation_cdpo/baseline | 1.0000 | 0.1212 | 0.5575 | -4.408218 | -5.171051 |
| exp_ablation_cdpo/dpo | 1.0000 | 0.1214 | 0.5582 | -4.405549 | -5.172074 |
| exp_ablation_simpo/baseline | 1.0000 | 0.1212 | 0.5575 | -4.408218 | -5.171051 |
| exp_ablation_simpo/dpo | 1.0000 | 0.1214 | 0.5581 | -4.404513 | -5.171420 |

## Conclusion

See individual experiment reports in reports/exp_ablation_*/summary.md
