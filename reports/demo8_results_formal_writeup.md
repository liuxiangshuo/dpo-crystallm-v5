## Experimental setup

We evaluate Direct Preference Optimization (DPO) alignment of CrystaLLM for crystal structure generation. For each target composition, we: (i) sample n≈200 CIFs from the baseline checkpoint with fixed decoding (top-k=10, T=1.0, seed=123), (ii) validate CIF parseability, (iii) score validated structures using a MatGL energy-per-atom proxy (lower/more negative is better), (iv) construct 50 preference pairs by pairing high-quality (low energy) samples against lower-quality (higher energy) samples, and (v) train a DPO checkpoint (300 steps, β=0.1, lr=1e-6). We then resample from the DPO checkpoint using the same decoding settings and compare MatGL score distributions. For NaCl, we additionally test a trimmed rejected pool that excludes the most extreme high-energy rejected candidates.

## Results

### LiFePO4 (baseline vs DPO)

DPO produces a clear shift toward lower MatGL proxy energy. Compared with baseline, DPO improves the mean by −1.30 eV/atom (−2.77 → −4.07) and the median by −0.31 eV/atom (−4.36 → −4.67). The upper tail also improves substantially: the 90th percentile decreases by −2.42 eV/atom (+0.40 → −2.02), and the worst-case outlier decreases by −10.71 eV/atom (31.10 → 20.38), indicating fewer extreme high-energy failures under the proxy.

### NaCl (pair construction ablation)

For NaCl, untrimmed “top vs bottom” pairs improve central tendency but worsen rare outliers: the mean improves slightly (−3.2415 → −3.2562) and the median improves (−3.2307 → −3.3046), but the worst-case becomes significantly higher energy (−2.3768 → −1.9040). Using a trimmed rejected pool preserves and slightly improves central gains (mean −3.2643, median −3.3047) while substantially mitigating outliers (worst-case −2.0642). Remaining outliers are still valid NaCl but correspond to higher-energy tetragonal P4/mmm variants with elongated c axes.
