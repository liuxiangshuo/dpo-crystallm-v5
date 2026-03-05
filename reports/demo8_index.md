# Demo8 index (DPO-CrystaLLM)

## Key writeups
- Formal results section: `reports/demo8_results_formal_writeup.md`
- LiFePO4 summary table: `reports/compare_baseline_vs_dpo_matgl_summary.md`
- NaCl 3-way comparison: `reports/compare_NaCl_baseline_vs_dpo_vs_trimmed_matgl.md`
- NaCl trimmed conclusion note: `reports/demo8_NaCl_trimmed_conclusion.md`
- LiFePO4 conclusion note: `reports/demo8_LiFePO4_conclusion.md`

## Packaged bundle
- `reports/demo8_results_packet.zip`

## Driver
- (in your other repo) `~/projects/crystallm-repro/scripts/demo8_dpo_driver.sh`

## Important paths used
- Baseline CrystaLLM dir: `~/projects/crystallm-repro/external/CrystaLLM/crystallm_v1_small`
- CrystaLLM python package dir: `~/projects/crystallm-repro/external/CrystaLLM/crystallm`

## Notes
- MatGL env requires: `export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"` before importing `matgl`.
- CrystaLLM block_size = 1024: filter pairs to <=1024 tokens.
