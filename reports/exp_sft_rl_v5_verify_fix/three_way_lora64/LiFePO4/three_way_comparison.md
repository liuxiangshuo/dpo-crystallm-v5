# Three-Way Comparison Report: LiFePO4

**Models**: Baseline vs SFT vs SFT+DPO

## 1. Key Metrics

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Validity Rate | 1.0000 | 1.0000 | 1.0000 | +0.0000 | +0.0000 |
| **Stability Rate** | 0.1333 | 0.1333 | **0.1333** | +0.0000 | +0.0000 |
| Stable Count | 16 | 16 | 16 | +0 | +0 |
| Composition Hit Rate | 0.4917 | 0.4917 | 0.4917 | +0.0000 | +0.0000 |

## 2. MatGL Energy Distribution (eV/atom, lower is better)

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Mean | -4.4995 | -4.4995 | -4.6562 | +0.0000 | -0.1566 |
| Median | -5.0165 | -5.0165 | -5.0798 | +0.0000 | -0.0633 |
| Std | 1.6774 | 1.6774 | 1.2188 | +0.0000 | -0.4585 |

**Baseline**: P10=-5.5981, P90=-2.6709, Best=-6.1312, Worst=5.9980
**SFT**: P10=-5.5981, P90=-2.6709, Best=-6.1312, Worst=5.9980
**SFT+DPO**: P10=-5.5921, P90=-2.7980, Best=-6.1312, Worst=0.5055

## 3. Composite Reward

| Metric | Baseline | SFT | SFT+DPO |
|--------|----------|-----|--------|
| R_proxy | 0.5000 | 0.5019 | 0.5086 |
| R_geom | 0.6596 | 0.6596 | 0.6661 |
| R_comp | 0.9874 | 0.9874 | 0.9874 |
| R_novel | 1.0000 | 0.0000 | 0.0500 |
| R_total | 0.6147 | 0.5160 | 0.5264 |

## 4. Visualizations

![Energy Histogram](plots/energy_histogram.png)

![Stability Comparison](plots/stability_comparison.png)

![Energy CDF](plots/energy_cdf.png)

## 5. Interpretation

SFT+DPO does not improve stability rate over baseline (delta=0.00%). Consider tuning hyperparameters or increasing training data.

