# Preference Pair Quality Analysis Report

**Dataset**: primary

## Overview

| Metric | Value |
|--------|-------|
| Total pairs | 5,000 |
| Unique prompts | 1 |
| Mean pairs/prompt | 5000.0 |
| Scenario distribution | {'A': 5000} |

## Energy Gap Statistics

| Statistic | Value (eV/atom) |
|-----------|----------------|
| MEAN | 4.183435 |
| MEDIAN | 2.586249 |
| STD | 5.985273 |
| MIN | 1.721464 |
| MAX | 108.414885 |
| P10 | 1.923062 |
| P25 | 2.124882 |
| P75 | 3.836578 |
| P90 | 7.007369 |

## Energy Statistics

| | Chosen | Rejected |
|--|--------|----------|
| Mean | -5.6633 | -1.4799 |
| Median | -5.6162 | -3.0852 |
| Std | 0.1351 | 5.9847 |

## Token Length Statistics

| | Chosen | Rejected |
|--|--------|----------|
| Mean | 462.9 | 528.7 |
| Median | 434.0 | 465.0 |
| Std | 73.6 | 98.9 |
| Min | 433 | 403 |
| Max | 738 | 800 |

## Plots

- `plots/gap_distribution.png` — Energy gap histogram
- `plots/chosen_vs_rejected.png` — Chosen vs rejected scatter
- `plots/token_length_dist.png` — Token length distribution
- `plots/token_vs_energy.png` — Token length vs energy correlation
