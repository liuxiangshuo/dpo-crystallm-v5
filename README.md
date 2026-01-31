# dpo-crystallm

DPO alignment pipeline for CrystaLLM (generate → validate → MatGL score → build preference pairs → DPO train → resample → re-score).

Large artifacts (CIFs, checkpoints, run logs) are intentionally ignored via .gitignore.

## Results (MatGL proxy energy/atom)

Lower (more negative) is better.

### LiFePO4: baseline vs DPO
See: `reports/compare_baseline_vs_dpo_matgl_summary.md`

### NaCl: baseline vs DPO vs trimmed-DPO (pair ablation)
See: `reports/compare_NaCl_baseline_vs_dpo_vs_trimmed_matgl.md`
