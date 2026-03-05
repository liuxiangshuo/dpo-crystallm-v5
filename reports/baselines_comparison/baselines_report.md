# Baseline Comparison Report: Best-of-N & Rejection Sampling

**Target**: LiFePO4

## 1. Best-of-N Sampling

Select top-K samples by MatGL energy from the full baseline pool.

| K (selected) | Selection % | Stability Rate | Mean Energy | Median Energy | Stable Count | GPU-s/stable |
|-------------|------------|----------------|-------------|---------------|-------------|-------------|
| 100 | 0.2% | 100.0% | -6.1746 | -6.1683 | 100 | 790.0s |
| 500 | 1.0% | 100.0% | -6.0958 | -6.0877 | 500 | 158.0s |
| 1,000 | 2.0% | 100.0% | -6.0248 | -6.0200 | 1,000 | 79.0s |
| 2,000 | 4.0% | 93.25% | -5.9028 | -5.8883 | 1,865 | 42.4s |
| 5,000 | 10.0% | 68.44% | -5.7516 | -5.6782 | 3,422 | 23.1s |
| 10,000 | 20.0% | 34.23% | -5.6662 | -5.6169 | 3,423 | 23.1s |
| 20,000 | 40.0% | 30.1% | -5.5622 | -5.5473 | 6,020 | 13.1s |
| 50,000 | 100.0% | 12.124% | -4.4082 | -5.1711 | 6,062 | 13.0s |

## 2. Rejection Sampling

Keep only samples below an energy threshold.

| Threshold (eV/atom) | Remaining | Survival % | Stability Rate | Stable Count | Mean Energy |
|--------------------|-----------|-----------:|----------------|-------------|------------|
| -6.0 | 581 | 1.16% | 100.0% | 581 | -6.083714 |
| -5.5 | 13,076 | 26.15% | 26.1854% | 3,424 | -5.632972 |
| -5.0 | 27,630 | 55.26% | 21.9037% | 6,052 | -5.463536 |
| -4.5 | 33,073 | 66.15% | 18.311% | 6,056 | -5.345439 |
| -4.0 | 38,473 | 76.95% | 15.7435% | 6,057 | -5.192512 |
| -3.5 | 42,677 | 85.35% | 14.1997% | 6,060 | -5.051683 |
| -3.0 | 45,410 | 90.82% | 13.3473% | 6,061 | -4.945235 |

## Plots

- `plots/bon_stability_curve.png` — Best-of-N stability vs K
- `plots/rejection_stability_curve.png` — Rejection sampling stability vs threshold
- `plots/method_comparison.png` — Combined comparison
