# Three-Way Comparison Report: LiFePO4

**Models**: Baseline vs SFT vs SFT+DPO

## 1. Key Metrics

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Validity Rate | 1.0000 | 1.0000 | 1.0000 | +0.0000 | +0.0000 |
| **Stability Rate** | 0.1250 | 0.1240 | **0.1240** | -0.0010 | -0.0010 |
| Stable Count | 250 | 248 | 248 | -2 | -2 |
| Composition Hit Rate | 0.5090 | 0.5120 | 0.5120 | +0.0030 | +0.0030 |

## 2. MatGL Energy Distribution (eV/atom, lower is better)

| Metric | Baseline | SFT | SFT+DPO | SFT vs Base | SFT+DPO vs Base |
|--------|----------|-----|---------|-------------|----------------|
| Mean | -4.4646 | -4.4757 | -4.4584 | -0.0111 | +0.0061 |
| Median | -5.1652 | -5.1620 | -5.1624 | +0.0032 | +0.0027 |
| Std | 2.6218 | 2.7187 | 2.6949 | +0.0969 | +0.0732 |

**Baseline**: P10=-5.6263, P90=-3.1867, Best=-6.1918, Worst=49.5498
**SFT**: P10=-5.6268, P90=-3.2092, Best=-6.1920, Worst=48.9680
**SFT+DPO**: P10=-5.6263, P90=-3.1818, Best=-6.1964, Worst=48.9680

## 3. Composite Reward

| Metric | Baseline | SFT | SFT+DPO |
|--------|----------|-----|--------|
| R_energy | 0.8158 | 0.8028 | 0.8072 |
| R_structure | 0.5 | 0.5 | 0.5 |
| R_difficulty | 0.9999 | 0.0503 | 0.0503 |
| R_composition | 0.7545 | 0.9891 | 0.9891 |

## 4. Visualizations

![Energy Histogram](plots/energy_histogram.png)

![Stability Comparison](plots/stability_comparison.png)

![Energy CDF](plots/energy_cdf.png)

## 5. Interpretation

SFT+DPO does not improve stability rate over baseline (delta=-0.10%). Consider tuning hyperparameters or increasing training data.

