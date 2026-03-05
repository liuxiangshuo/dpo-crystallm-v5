# Three-Way Comparison Report: TiO2

**Models**: Baseline vs SFT vs SFT+DPO

## 1. Key Metrics

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Validity Rate | 1.0000 | 1.0000 | 1.0000 | +0.0000 | +0.0000 |
| **Stability Rate** | 0.0417 | 0.0417 | **0.0417** | +0.0000 | +0.0000 |
| Stable Count | 5 | 5 | 5 | +0 | +0 |
| Composition Hit Rate | 0.3667 | 0.3667 | 0.3667 | +0.0000 | +0.0000 |

## 2. MatGL Energy Distribution (eV/atom, lower is better)

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Mean | -5.2250 | -5.2247 | -5.2195 | +0.0004 | +0.0055 |
| Median | -5.7179 | -5.7179 | -5.7179 | +0.0000 | +0.0000 |
| Std | 4.7473 | 4.7473 | 4.7473 | -0.0000 | -0.0000 |

**Baseline**: P10=-6.5799, P90=-4.9840, Best=-8.3329, Worst=42.9726
**SFT**: P10=-6.5799, P90=-4.9840, Best=-8.3329, Worst=42.9726
**SFT+DPO**: P10=-6.5799, P90=-4.9321, Best=-8.3329, Worst=42.9726

## 3. Composite Reward

| Metric | Baseline | SFT | SFT+DPO |
|--------|----------|-----|--------|
| R_proxy | 0.5076 | 0.5050 | 0.5051 |
| R_geom | 0.6794 | 0.6794 | 0.6796 |
| R_comp | 0.9678 | 0.9678 | 0.9678 |
| R_novel | 0.9661 | 0.0000 | 0.0000 |
| R_total | 0.6167 | 0.5182 | 0.5183 |

## 4. Visualizations

![Energy Histogram](plots/energy_histogram.png)

![Stability Comparison](plots/stability_comparison.png)

![Energy CDF](plots/energy_cdf.png)

## 5. Interpretation

SFT+DPO does not improve stability rate over baseline (delta=0.00%). Consider tuning hyperparameters or increasing training data.

