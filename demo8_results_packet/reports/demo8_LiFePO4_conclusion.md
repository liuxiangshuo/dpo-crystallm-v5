## Demo8 LiFePO4: DPO improves MatGL proxy distribution

**Metric:** MatGL proxy energy per atom (lower / more negative is better).

### Summary (n≈200)
From `reports/compare_baseline_vs_dpo_matgl_summary.md`:

- Mean improved by **−1.30 eV/atom** (baseline −2.77 → DPO −4.07)
- Median improved by **−0.31 eV/atom** (baseline −4.36 → DPO −4.67)
- 90th percentile improved by **−2.42 eV/atom** (baseline +0.40 → DPO −2.02)
- Worst-case improved by **−10.71 eV/atom** (baseline 31.10 → DPO 20.38)

### Interpretation
DPO substantially shifts the score distribution toward lower-energy LiFePO4 structures and reduces extreme high-energy outliers under the MatGL proxy.
