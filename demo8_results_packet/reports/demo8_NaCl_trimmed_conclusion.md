## Demo8 NaCl: DPO pair construction ablation (MatGL proxy)

**Metric:** MatGL proxy energy per atom (lower / more negative is better).

### Summary
- **Baseline:** mean −3.2415, median −3.2307, worst-case (max) −2.3768
- **DPO (untrimmed top vs bottom pairs):** mean −3.2562, median −3.3046, but worst-case −1.9040 (bad tail/outliers)
- **DPO (trimmed rejected pool, exclude extreme high-energy outliers):** mean −3.2643, median −3.3047, worst-case −2.0642

### Interpretation
DPO improves the center of the distribution for NaCl, but naive extreme pairs can create rare high-energy polymorph outliers. Trimming the rejected pool keeps mean/median gains while substantially improving the worst-case tail.

### Example outlier type
The remaining worst samples are still valid NaCl but correspond to a higher-energy tetragonal `P4/mmm` cell with elongated `c` (e.g., `sample_158.cif`).
