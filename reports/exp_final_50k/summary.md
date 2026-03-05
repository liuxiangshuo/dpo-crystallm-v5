# DPO-CrystaLLM Comparison Report: LiFePO4

## 1. Key Metrics (Done Criteria)

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| **Validity Rate** | 1.0000 | 1.0000 | +0.0000 |
| **Stability Rate** (Ehull<0.05) | 0.1212 | 0.1227 | +0.0015 |
| **Efficiency** (GPU s/stable) | 13.2s | 13.0s | - |
| **Novelty** | N/A | N/A | N/A |
| Composition Hit Rate | 0.5575 | 0.5532 | -0.0043 |

## 2. MatGL Energy / Atom (eV, lower is better)

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| Mean | -4.408218 | -4.407494 | +0.000724 |
| Median | -5.171051 | -5.178731 | -0.007680 |
| Std | 3.135087 | 3.151303 | +0.016217 |
| P10 (best 10%) | -5.616938 | -5.618572 | -0.001634 |
| P90 | -3.104878 | -3.111726 | -0.006848 |
| Best | -6.525834 | -6.525834 | +0.000000 |
| Worst | 102.763297 | 102.763297 | +0.000000 |

## 3. Visualizations

### Energy Distribution
![Energy Histogram](plots/energy_histogram.png)

### Cumulative Distribution
![Energy CDF](plots/energy_cdf.png)

### Training Loss
![Training Loss](plots/training_loss.png)


## 4. Failure Analysis

### Baseline Generation

- Requested: 50000
- Successful: 50000
- Valid rate: 1.0
- Failure breakdown:
  - `validation_error_AssertionError`: 17
  - `validation_error_ValueError`: 13
  - `validation_error_ZeroDivisionError`: 10

### DPO Generation

- Requested: 50000
- Successful: 50000
- Valid rate: 1.0
- Failure breakdown:
  - `validation_error_ValueError`: 16
  - `validation_error_AssertionError`: 12
  - `validation_error_ZeroDivisionError`: 10


## 5. Detailed Counts

### Baseline
- Total: 50000
- Valid: 50000 (100.00%)
- Hit target: 27873 (55.75%)
- Scored: 50000

### DPO
- Total: 50000
- Valid: 50000 (100.00%)
- Hit target: 27658 (55.32%)
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
