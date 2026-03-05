
# Helper: check reward spread after composite reward scoring (using shared module)
check_reward_spread() {
    local scored_dir="$1" label="$2"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" check_reward_spread \
        --scored_dir "$scored_dir" --label "$label" || true
}

# Helper: merge labels.csv + ehull_scores.csv -> eval.csv (using shared module)
merge_eval_csv() {
    local scored_dir="$1"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" merge_eval \
        --scored_dir "$scored_dir" || echo "WARNING: eval.csv merge failed for $scored_dir"
}

# Helper: count rows in a CSV (excluding header) - using shared module
count_csv_rows() {
    local csv_path="$1"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" count_csv --csv "$csv_path" --type rows 2>/dev/null || echo 0
}

# Helper: count non-empty MatGL score rows (excluding header/failed rows) - using shared module
count_scored_rows() {
    local scores_csv="$1"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" count_csv --csv "$scores_csv" --type scored 2>/dev/null || echo 0
}

# Helper: count CIF files under a directory - using shared module
count_cif_files() {
    local cif_dir="$1"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" count_csv --csv "$cif_dir" --type cifs 2>/dev/null || echo 0
}

# Helper: check failed-score rate using scores_failed.csv and ehull_scores.csv - using shared module
check_score_fail_rate() {
    local scored_dir="$1"
    local label="$2"
    local mode="${SCORE_FAILED_GATE_MODE:-warn}"
    local threshold="${SCORE_FAILED_RATE_FAIL:-0.05}"

    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" check_fail_rate \
        --scored_dir "$scored_dir" --label "$label" --mode "$mode" --threshold "$threshold"
    local rc=$?
    if [ "$mode" = "fail" ] && [ "$rc" -ne 0 ]; then
        return 1
    fi
    return 0
}

# Helper: warn if Phase 6 produced no rendered images.
warn_if_no_visualizations() {
    local viz_dir="$1"
    python3 -c "
from pathlib import Path
viz_dir = Path('$viz_dir')
if not viz_dir.exists():
    print(f'WARNING: Visualization output dir missing: {viz_dir}')
    raise SystemExit(0)
exts = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
n = sum(1 for p in viz_dir.rglob('*') if p.suffix.lower() in exts)
if n == 0:
    print(f'WARNING: Phase 6 rendered 0 images under {viz_dir}. Check input ranking files or rendering backend.')
else:
    print(f'Phase 6 rendered images: {n}')
" 2>&1 || true
}

# Helper: build CIF-format prompt for a target
build_prompt() {
    local target="$1"
    local z="${PROMPT_Z_MAP_DICT[$target]:-1}"
    # #region agent log
    debug_log "pre-fix-1" "H4" "run_sft_rl_pipeline.sh:BUILD_PROMPT" "Resolved prompt Z value for target" "{\"target\":\"$target\",\"z_raw\":\"$z\"}"
    # #endregion
    python3 -c "
import re
formula, z = '$target', int('$z')
pairs = re.findall(r'([A-Z][a-z]?)(\d*)', formula)
parts = []
for elem, cnt in pairs:
    if not elem: continue
    n = int(cnt) if cnt else 1
    n *= z
    parts.append(f'{elem}{n}' if n > 1 else elem)
print(f'data_{\"\" .join(parts)}')
"
}

# ---- Ablation branch support ----
# If SFT_BRANCHES is set, we run multiple SFT→DPO pipelines.
# Otherwise fall back to single-branch behaviour using top-level SFT_* vars.
if [ -n "$SFT_BRANCHES" ]; then
    IFS=',' read -ra BRANCH_LIST <<< "$SFT_BRANCHES"
else
    BRANCH_LIST=("default")
fi

# Lookup branch-specific variable; fall back to top-level SFT_* default.
branch_var() {
    local branch="$1" var="$2" default="$3"
    local full="SFT_${branch}_${var}"
    if [ -n "${!full+x}" ]; then
        echo "${!full}"
    else
        echo "$default"
    fi
}

echo "SFT branches: ${BRANCH_LIST[*]} (${#BRANCH_LIST[@]})"

