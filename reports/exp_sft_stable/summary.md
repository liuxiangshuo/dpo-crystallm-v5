# SFT-CrystaLLM Comparison Report: LiFePO4

## 1. Key Metrics (Done Criteria)

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| **Validity Rate** | 1.0000 | 1.0000 | +0.0000 |
| **Stability Rate** (Ehull<0.05) | 0.1212 | 0.1103 | -0.0110 |
| **Efficiency** (GPU s/stable) | 0.2s | 0.7s | - |
| **Novelty** | N/A | N/A | N/A |
| Composition Hit Rate | 0.5575 | 0.5778 | +0.0204 |

## 2. MatGL Energy / Atom (eV, lower is better)

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| Mean | -4.408218 | -4.329710 | +0.078508 |
| Median | -5.171051 | -5.122064 | +0.048987 |
| Std | 3.135087 | 3.309529 | +0.174443 |
| P10 (best 10%) | -5.616938 | -5.616708 | +0.000230 |
| P90 | -3.104878 | -3.004767 | +0.100111 |
| Best | -6.525834 | -6.525834 | +0.000000 |
| Worst | 102.763297 | 147.358785 | +44.595488 |

## 3. Visualizations

### Energy Distribution
![Energy Histogram](plots/energy_histogram.png)

### Cumulative Distribution
![Energy CDF](plots/energy_cdf.png)

### Training Loss
![Training Loss](plots/training_loss.png)


## 4. Failure Analysis


## 5. Detailed Counts

### Baseline
- Total: 50000
- Valid: 50000 (100.00%)
- Hit target: 27873 (55.75%)
- Scored: 50000

### DPO
- Total: 50000
- Valid: 50000 (100.00%)
- Hit target: 28891 (57.78%)
- Scored: 50000


## 6. Reproducibility

To reproduce this experiment:
```bash
cd experiments/<exp_name>
# Fresh run:
bash run.sh
# Resume from last checkpoint:
RESUME=1 bash run.sh
```
