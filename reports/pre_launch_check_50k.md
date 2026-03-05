# Pre-Launch Check Report: 50K DPO-CrystaLLM Experiment

**Date:** 2025-02-07  
**Purpose:** Identify and fix issues before running the ~50K sample, 8–12 hour experiment.

---

## 1. MatGL Scoring High Failure Rate (39/73 = 53.4%)

### Finding
- **scores_failed.csv** shows 34 failures, all with the same error:
  - `ValueError: 'zip() argument 2 is longer than argument 1'`
  - Raised inside **pymatgen** `CifParser.from_str()` / `CifFile.from_str()` when parsing the CIF (traceback points to `pymatgen/io/cif.py` line 286).
- This typically occurs when a CIF has **multiple `data_` blocks** in one file: the parser sees a loop whose column count and value count don’t match (e.g. mixing or spanning blocks).
- Inspecting **sample_0003.cif** (one of the failed files) shows **multiple data_ blocks** in a single file (e.g. `data_Li4Fe4P4O16`, then `data_Ba2Ca2As4`, then `data_K4Li4Ca4`). pymatgen expects one block per file (or proper multi-block handling); concatenated blocks cause the zip error.

### Root cause
- **extract_first_data_block()** in `scripts/40_generate_cifs_crystallm.py` had a logic bug: the second `data_` line was never used to set `data_end` (the `elif` was unreachable after the first `if`), so the **entire decoded string** (including extra blocks) was written to disk. Those multi-block CIFs then fail in MatGL scoring when pymatgen parses them.

### Fix applied
- **extract_first_data_block()** was corrected so that when a second `data_` line is seen, `data_end = i` and the loop breaks; only the first block is returned and written. Regenerating CIFs with the fixed script will produce single-block CIFs and avoid this class of MatGL parse failures.

### Recommendations
1. **Use the fixed generator** for the 50K run (fix is in `40_generate_cifs_crystallm.py`).
2. **Keep pipeline order:** run **11_validate_cifs.py** (which uses the same `Structure.from_file()` as pymatgen) and pass **valid_cifs** to MatGL scoring so only parseable CIFs are scored.
3. **Confirm scoring input:** In `demo8_dpo_driver.sh`, MatGL is correctly called with `--in_dir $BASELINE_VALID_DIR` (valid_cifs). Ensure no manual or one-off runs use `raw_cifs` for scoring.
4. If failures persist, align **pymatgen** versions between `myenv` (used by 11/12) and `matgl_env` (used by 35) so parsing behavior is consistent.

---

## 2. Token Length Near Limit (1022.7 / 1024)

### Finding
- **experiments/exp_final_50k/config.sh** has `MAX_TOKENS=1024`.
- Average pair token length in the smoke test is 1022.7; many valid pairs will be close to or over 1024 and risk being rejected by the token filter in **41_build_pairs_with_token_filter.py**.

### Recommendation
- **Increase MAX_TOKENS** in `experiments/exp_final_50k/config.sh` to **1280** or **1536** to leave headroom and avoid dropping good pairs. CrystaLLM small’s block size is 1024; if the model/config supports a larger context, use it; otherwise keep 1024 but expect more pairs to be filtered and consider lowering pair_min_per_prompt or relaxing the filter (e.g. cap at 1020) if needed.
- **Action:** In `config.sh` set for example:
  - `export MAX_TOKENS=1280`
  - (Only if the model and tokenizer actually support 1280; otherwise document that many pairs will be near the limit and monitor pair counts after the run.)

---

## 3. Disk Space

### Finding
- `df -h /home/liuxiangshuo/`: **2.7 TB free** on `/home` (29% used).
- 50K CIFs × 2 runs (baseline + DPO) + checkpoints (~600 MB each) + logs is well within this.

### Recommendation
- No change needed. Optionally run `du -sh` on `outputs/` after the experiment to confirm usage.

---

## 4. Screen / tmux Availability

### Finding
- **tmux:** Present at `/usr/bin/tmux`, version 3.0a.
- **screen:** Command returned exit 127 (not available or not in PATH).

### Recommendation
- Use **tmux** for the 8–12 hour run so the session survives disconnects:
  - `tmux new -s crystallm50k`
  - `cd /home/liuxiangshuo/projects/dpo-crystallm && source experiments/exp_final_50k/config.sh && bash experiments/exp_final_50k/run.sh`
  - Detach: `Ctrl+b d`. Reattach: `tmux attach -t crystallm50k`.

---

## 5. valid_cifs Directory and 11_validate_cifs.py

### Finding
- **valid_cifs** at `outputs/exp_smoke_test_v2/baseline/scored/valid_cifs/` is **empty** (no files).
- **11_validate_cifs.py** reads `--in_dir` (default `data/raw_cifs`), parses each CIF with `Structure.from_file()`, and copies:
  - parseable → `out_dir/valid_cifs/`
  - unparseable → `out_dir/invalid_cifs/`
  - and writes `parse_summary.csv`.

So valid_cifs is populated only when 11 is run with the correct `--out_dir`. If 11 was skipped or pointed elsewhere for the smoke run, valid_cifs would be empty. Scoring then either ran on **raw_cifs** (which would explain 73 input files and 34 parse failures in 35) or on an older/copied valid_cifs.

### Recommendation
1. Ensure **Step 2** of the driver always runs **11_validate_cifs.py** with:
   - `--in_dir` = baseline/dpo raw_cifs dir
   - `--out_dir` = baseline/dpo scored dir
   so that `scored/valid_cifs/` is populated before MatGL.
2. Keep **35_score_dir_matgl.py** using `--in_dir $BASELINE_VALID_DIR` (valid_cifs). Do not point it at raw_cifs.
3. For the 50K run, after Step 2, verify:
   - `ls outputs/<exp>/baseline/scored/valid_cifs/ | wc -l`
   - and that this count is used as input to scoring (not raw_cifs count).

---

## 6. Labels vs Scoring Alignment

### Finding
- **labels.csv** has **73 rows** (one per raw CIF), produced by **12_label_cifs.py** from **raw_cifs** (same `Structure.from_file()` as 11).
- Only **39** CIFs were successfully scored (ehull_scores.csv / ehull_estimates.csv).
- The merge step in the driver builds **eval.csv** by joining labels (all 73) with scores (only files that got a score); rows without a score get an empty `score_e_per_atom`.
- So: labels = all raw CIFs; scores = only CIFs that were in the **scoring input** and parsed + scored successfully. If scoring is run on **valid_cifs**, then only CIFs that passed 11 (parseable) get scores; the rest remain in labels but with no score. That is the intended design.

### Conclusion
- Alignment is correct **provided** scoring uses **valid_cifs**. The smoke test’s 73 labels vs 39 scores is consistent with scoring having been run on **raw_cifs** (73 files, 34 parse failures in pymatgen). With the fixed generator and scoring on valid_cifs, you should see:
  - labels = all raw (e.g. 50K),
  - valid_cifs = parseable subset,
  - scores = one row per file in valid_cifs (all of which should parse in 35 if they parsed in 11).

No script changes required beyond using valid_cifs for scoring and the fixed first-block extraction.

---

## 7. Ehull Estimates CSV (LiFePO4 and Values)

### Finding
- **ehull_estimates.csv** has **39 rows** (one per successfully scored CIF).
- Formulas include **LiFePO4** (majority), **LiFePO3**, **LiFePO2**.
- **LiFePO4** reference hull energy: **hull_ref_e_per_atom = -6.010381**.
- **ehull_proxy** = e_per_atom - hull_ref_e_per_atom. Examples:
  - sample_0073.cif: -6.076520, ehull_proxy **-0.066** (stable)
  - sample_0082.cif: -6.011598, ehull_proxy **-0.001**
  - sample_0012.cif: +6.76, ehull_proxy **+12.77** (unstable)
- **ehull_summary.json**: 39 total scored, 5 with ehull < 0.05 (“stable”), stability rate 12.82%.

### Recommendation
- No change needed. Ehull estimates and LiFePO4 reference look consistent. Use the same setup for the 50K run.

---

## 8. GPU Memory During 50K Generation

### Finding
- **40_generate_cifs_crystallm.py**:
  - Loads the model once and runs in `torch.no_grad()` and `model.eval()`.
  - No obvious accumulation of tensors; per-sample/batch tensors go out of scope.
  - No `torch.cuda.empty_cache()` or `gc.collect()` in the repo.

### Recommendation
1. **Default:** Run as-is; the model is small (~300 MB) and 50K sequential generations are unlikely to leak if tensors are released each iteration.
2. **If you see OOM** mid-run, add periodic cleanup in the generation loop (e.g. every 1000 or 5000 samples):
   - `import gc`
   - `torch.cuda.empty_cache(); gc.collect()`
3. Optionally log GPU memory (e.g. `torch.cuda.memory_allocated()`) every N samples to confirm stable usage.

---

## Summary: What to Fix Before the 50K Run

| # | Item | Severity | Action |
|---|------|----------|--------|
| 1 | MatGL failures (multi-block CIF) | **High** | **Done:** Fixed `extract_first_data_block()` in `40_generate_cifs_crystallm.py`. Use this script for 50K. Ensure scoring uses **valid_cifs** and 11 runs first. |
| 2 | MAX_TOKENS=1024 too tight | **Medium** | Increase to 1280 (or 1536) in `experiments/exp_final_50k/config.sh` if the model supports it; otherwise keep 1024 and monitor pair counts. |
| 3 | Disk space | OK | 2.7 TB free; no action. |
| 4 | Persistent session | OK | Use **tmux** (available); avoid relying on screen. |
| 5 | valid_cifs empty in smoke | **Medium** | Ensure 11_validate_cifs runs and 35 uses valid_cifs; verify valid_cifs count after Step 2 for 50K. |
| 6 | Labels vs scores | OK | Design is correct; keep scoring on valid_cifs. |
| 7 | Ehull CSV | OK | LiFePO4 and values look fine; no change. |
| 8 | GPU memory | Low | No change unless OOM; then add periodic empty_cache/gc. |

---

## Suggested Pre-Flight Commands

```bash
# 1) Use tmux
tmux new -s crystallm50k

# 2) Optional: bump MAX_TOKENS in config (if model supports it)
# Edit experiments/exp_final_50k/config.sh: MAX_TOKENS=1280

# 3) Run from project root (driver will source config from env or experiment dir)
cd /home/liuxiangshuo/projects/dpo-crystallm
source experiments/exp_final_50k/config.sh
bash experiments/exp_final_50k/run.sh

# 4) After Step 2 (baseline generation + validation + scoring), spot-check:
# ls outputs/<EXP_NAME>/baseline/scored/valid_cifs/ | wc -l
# wc -l outputs/<EXP_NAME>/baseline/scored/ehull_scores.csv
```

After the run, re-check that most generated CIFs are single-block (no zip errors in scores_failed.csv) and that pair counts meet MIN_PAIRS.
