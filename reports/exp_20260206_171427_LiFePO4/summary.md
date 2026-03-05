# DPO-CrystaLLM Comparison Report: LiFePO4

**Experiment**: reports

## Summary Statistics

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| Validity Rate | 1.0000 | 1.0000 | +0.0000 |
| Composition Hit Rate | 0.0006 | 0.0000 | -0.0006 |

## MatGL Energy/Atom Statistics (lower is better)

| Metric | Baseline | DPO | Change |
|--------|----------|-----|--------|
| Mean | -3.235170 | -3.757524 | -0.522354 |
| Median | -3.400748 | -3.600337 | -0.199589 |
| P95 | -1.313900 | -1.401862 | -0.087962 |
| P99 | -0.816086 | -0.754391 | +0.061695 |
| Worst | 400.652496 | 34.495625 | -366.156871 |

## Detailed Statistics

### Baseline
- Total samples: 1627
- Valid: 1627 (100.00%)
- Hit target: 1 (0.06%)
- Scored: 1046
- Mean score: -3.235170
- Median score: -3.400748

### DPO
- Total samples: 1605
- Valid: 1605 (100.00%)
- Hit target: 0 (0.00%)
- Scored: 1078
- Mean score: -3.757524
- Median score: -3.600337
