#!/bin/bash
# =============================================================================
# SFT + RL (DPO) Two-Stage Pipeline Driver
#
# Implements the three key improvements from advisor feedback:
#   1. Multi-dimensional reward (composite reward as regularisation)
#   2. Multi-composition data diversity (multiple prompts)
#   3. SFT + RL two-stage pipeline
#
# Pipeline phases:
#   Phase 1: Multi-composition baseline generation + scoring
#   Phase 2: SFT on stable structures from all compositions
#   Phase 3: SFT model resample + composite reward scoring
#   Phase 4: Reward-weighted DPO on top of SFT model
#   Phase 5: Final evaluation + comparison report
#
# Usage (see bottom of file for detailed examples):
#   source experiments/exp_sft_rl/config.sh
#   bash scripts/run_sft_rl_pipeline.sh              # Fresh run
#   RESUME=1 bash scripts/run_sft_rl_pipeline.sh     # Resume from checkpoint
#   CLEAN=1 bash scripts/run_sft_rl_pipeline.sh      # Force clean rerun
# =============================================================================
set -e

# Initialize conda (supports custom CONDA_BASE via environment variable)
CONDA_BASE="${CONDA_BASE:-$HOME/miniconda3}"
if [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    source "$CONDA_BASE/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
    echo "WARNING: Could not find conda.sh. Set CONDA_BASE environment variable."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ---- Required variables ----
: "${EXP_NAME:?'EXP_NAME must be set'}"
: "${TARGETS:?'TARGETS must be set (comma-separated, e.g. LiFePO4,NaCl,TiO2)'}"
: "${CRYSTALLM_CKPT_DIR:?'CRYSTALLM_CKPT_DIR must be set'}"
: "${CRYSTALLM_PKG_DIR:?'CRYSTALLM_PKG_DIR must be set'}"

# #region agent log
python3 - <<'PY'
import json
import os
import time

entry = {
    "sessionId": "25e703",
    "runId": "pre-fix-1",
    "hypothesisId": "H5",
    "location": "scripts/run_sft_rl_pipeline.sh:early_startup",
    "message": "pipeline script entered after required vars",
    "data": {
        "exp_name": os.environ.get("EXP_NAME", ""),
        "targets": os.environ.get("TARGETS", ""),
    },
    "timestamp": int(time.time() * 1000),
}
with open("/home/liuxiangshuo/projects/dpo-crystallm/.cursor/debug-25e703.log", "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
# #endregion

# ---- Defaults ----
NUM_SAMPLES=${NUM_SAMPLES:-10000}
TOP_K=${TOP_K:-10}
TEMPERATURE=${TEMPERATURE:-1.0}
SEED=${SEED:-42}
MAX_TOKENS=${MAX_TOKENS:-1024}
MAX_RETRIES=${MAX_RETRIES:-5}
GEN_BATCH_SIZE=${GEN_BATCH_SIZE:-16}
MATGL_FIX_LD_LIBRARY_PATH=${MATGL_FIX_LD_LIBRARY_PATH:-0}
export MATGL_FIX_LD_LIBRARY_PATH

# Quality gates
MIN_VALID_CIFS=${MIN_VALID_CIFS:-1000}
MIN_SCORED_CIFS=${MIN_SCORED_CIFS:-800}
MIN_PAIRS=${MIN_PAIRS:-500}

# Pair building
PAIR_STRATEGY=${PAIR_STRATEGY:-trimmed}
PAIR_GAP=${PAIR_GAP:-0.1}
PAIR_MIN_PER_PROMPT=${PAIR_MIN_PER_PROMPT:-1}
PAIR_MAX_PER_PROMPT=${PAIR_MAX_PER_PROMPT:-5000}
PAIR_TOP_PERCENT=${PAIR_TOP_PERCENT:-0.30}
PAIR_BOTTOM_PERCENT=${PAIR_BOTTOM_PERCENT:-0.30}
DPO_TOTAL_PAIRS=${DPO_TOTAL_PAIRS:-6000}

# Composite reward weights (Plan B)
REWARD_W_PROXY=${REWARD_W_PROXY:-0.45}
REWARD_W_GEOM=${REWARD_W_GEOM:-0.30}
REWARD_W_COMP=${REWARD_W_COMP:-0.20}
REWARD_W_NOVEL=${REWARD_W_NOVEL:-0.05}
REWARD_MIN_INTERATOMIC_DISTANCE=${REWARD_MIN_INTERATOMIC_DISTANCE:-0.6}
REWARD_ENABLE_DENSITY_GATE=${REWARD_ENABLE_DENSITY_GATE:-1}
REWARD_DENSITY_MIN=${REWARD_DENSITY_MIN:-0.1}
REWARD_DENSITY_MAX=${REWARD_DENSITY_MAX:-30.0}
REWARD_PROXY_BUFFER_SIZE=${REWARD_PROXY_BUFFER_SIZE:-50000}
REWARD_NOVELTY_WINDOW=${REWARD_NOVELTY_WINDOW:-2000}

# SFT (Stage 1)
SFT_STEPS=${SFT_STEPS:-6000}
SFT_LR=${SFT_LR:-5e-8}
SFT_GRAD_ACCUM=${SFT_GRAD_ACCUM:-8}
SFT_MAX_GRAD_NORM=${SFT_MAX_GRAD_NORM:-1.0}
SFT_SAVE_EVERY=${SFT_SAVE_EVERY:-1000}
SFT_WARMUP=${SFT_WARMUP:-200}
SFT_STRATEGY=${SFT_STRATEGY:-lora}
SFT_LORA_RANK=${SFT_LORA_RANK:-16}
SFT_WEIGHT_DECAY=${SFT_WEIGHT_DECAY:-0.01}
EHULL_THRESHOLD=${EHULL_THRESHOLD:-0.05}

# DPO (Stage 2)
DPO_STEPS=${DPO_STEPS:-4000}
DPO_BETA=${DPO_BETA:-2.5}
DPO_LR=${DPO_LR:-1e-7}
DPO_GRAD_ACCUM=${DPO_GRAD_ACCUM:-16}
DPO_MAX_GRAD_NORM=${DPO_MAX_GRAD_NORM:-1.0}
DPO_SAVE_EVERY=${DPO_SAVE_EVERY:-500}
DPO_WARMUP=${DPO_WARMUP:-200}
DPO_STRATEGY=${DPO_STRATEGY:-full}
DPO_LORA_RANK=${DPO_LORA_RANK:-16}
DPO_LOSS_TYPE=${DPO_LOSS_TYPE:-dpo}
DPO_LABEL_SMOOTHING=${DPO_LABEL_SMOOTHING:-0.1}
DPO_SIMPO_GAMMA=${DPO_SIMPO_GAMMA:-1.0}
DPO_REWARD_WEIGHTED=${DPO_REWARD_WEIGHTED:-1}
DPO_REWARD_ALPHA=${DPO_REWARD_ALPHA:-1.0}
DPO_WEIGHT_DECAY=${DPO_WEIGHT_DECAY:-0.01}

# Sampling diversity
TEMPERATURE_RANGE=${TEMPERATURE_RANGE:-}
TOP_K_RANGE=${TOP_K_RANGE:-}

# Scoring quality gate
#   off  -> only print stats
#   warn -> warn when failed-rate > SCORE_FAILED_RATE_FAIL
#   fail -> abort when failed-rate > SCORE_FAILED_RATE_FAIL
SCORE_FAILED_GATE_MODE=${SCORE_FAILED_GATE_MODE:-warn}
SCORE_FAILED_RATE_FAIL=${SCORE_FAILED_RATE_FAIL:-0.05}

# SFT ablation branches (empty = single default branch)
SFT_BRANCHES=${SFT_BRANCHES:-}

# Parse comma-separated targets
IFS=',' read -ra TARGET_LIST <<< "$TARGETS"

# Prompt Z map: e.g. "LiFePO4:4,NaCl:4,TiO2:4,BaTiO3:1"
declare -A PROMPT_Z_MAP_DICT
if [ -n "$PROMPT_Z_MAP" ]; then
    IFS=',' read -ra Z_ENTRIES <<< "$PROMPT_Z_MAP"
    for entry in "${Z_ENTRIES[@]}"; do
        IFS=':' read -ra KV <<< "$entry"
        PROMPT_Z_MAP_DICT["${KV[0]}"]="${KV[1]}"
    done
fi

# Experiment directories
EXP_DIR="outputs/$EXP_NAME"
REPORT_DIR="reports/$EXP_NAME"
LOG_DIR="$EXP_DIR/logs"
mkdir -p "$EXP_DIR" "$REPORT_DIR" "$LOG_DIR"

# Log files
LOG_FILE="$EXP_DIR/experiment.log"
ERROR_LOG="$LOG_DIR/errors.jsonl"
TIMING_LOG="$LOG_DIR/timing.jsonl"
CONFIG_SNAPSHOT="$LOG_DIR/config_snapshot.json"

# Initialize log files
touch "$ERROR_LOG"
touch "$TIMING_LOG"

# Function to log errors
log_error() {
    local phase="$1"
    local location="$2"
    local message="$3"
    local details="${4:-{}}"
    local timestamp=$(date -Iseconds)
    
    echo "{\"timestamp\": \"$timestamp\", \"phase\": \"$phase\", \"location\": \"$location\", \"message\": \"$message\", \"details\": $details}" >> "$ERROR_LOG"
}

# Function to record phase timing
record_timing() {
    local phase="$1"
    local status="$2"
    local timestamp=$(date +%s)
    local timestamp_iso=$(date -Iseconds)
    
    echo "{\"phase\": \"$phase\", \"status\": \"$status\", \"timestamp\": $timestamp, \"timestamp_iso\": \"$timestamp_iso\"}" >> "$TIMING_LOG"
}

# Save configuration snapshot
python3 - "$CONFIG_SNAPSHOT" << 'PYEOF'
import json
import sys
import os

snapshot_file = sys.argv[1]
config = {
    "experiment": os.environ.get("EXP_NAME", "unknown"),
    "timestamp": os.popen("date -Iseconds").read().strip(),
    "parameters": {
        "targets": os.environ.get("TARGETS", ""),
        "num_samples": int(os.environ.get("NUM_SAMPLES", 0)),
        "min_valid_cifs": int(os.environ.get("MIN_VALID_CIFS", 0)),
        "min_scored_cifs": int(os.environ.get("MIN_SCORED_CIFS", 0)),
        "min_pairs": int(os.environ.get("MIN_PAIRS", 0)),
        "dpo_total_pairs": int(os.environ.get("DPO_TOTAL_PAIRS", 0)),
        "sft_steps": int(os.environ.get("SFT_STEPS", 0)),
        "dpo_steps": int(os.environ.get("DPO_STEPS", 0))
    },
    "paths": {
        "exp_dir": f"outputs/{os.environ.get('EXP_NAME', '')}",
        "ckpt_dir": os.environ.get("CRYSTALLM_CKPT_DIR", "")
    }
}
with open(snapshot_file, 'w') as f:
    json.dump(config, f, indent=2)
print(f"[config] Snapshot saved to {snapshot_file}")
PYEOF

# Main log redirection
exec > >(tee -a "$LOG_FILE") 2>&1

# #region agent log (using shared pipeline_utils.py)
debug_log() {
    local run_id="$1"
    local hypothesis_id="$2"
    local location="$3"
    local message="$4"
    local data_json="$5"
    python3 "$SCRIPT_DIR/shared/pipeline_utils.py" debug_log \
        --log_dir "$PROJECT_ROOT/.cursor" \
        --run_id "$run_id" \
        --hypothesis_id "$hypothesis_id" \
        --location "$location" \
        --message "$message" \
        --data "$data_json"
}
# #endregion

echo "=========================================="
echo "SFT + RL Two-Stage Pipeline"
echo "Experiment: $EXP_NAME"
echo "Targets: ${TARGET_LIST[*]} (${#TARGET_LIST[@]} compositions)"
echo "SFT steps: $SFT_STEPS (LR=$SFT_LR, strategy=$SFT_STRATEGY)"
echo "DPO steps: $DPO_STEPS (LR=$DPO_LR, loss=$DPO_LOSS_TYPE)"
echo "Reward weights (Plan B): proxy=$REWARD_W_PROXY geom=$REWARD_W_GEOM comp=$REWARD_W_COMP novel=$REWARD_W_NOVEL"
echo "Started at: $(date)"
echo "=========================================="

# ============================================================================
# CONFIG DUMP: Print final resolved configuration
# ============================================================================
echo ""
echo "=== RESOLVED CONFIGURATION ==="
echo "--- Generation Parameters ---"
echo "  NUM_SAMPLES:           $NUM_SAMPLES (requested samples per target)"
echo "  MIN_VALID_CIFS:        $MIN_VALID_CIFS (min valid CIFs required)"
echo "  MIN_SCORED_CIFS:       $MIN_SCORED_CIFS (min scored CIFs required)"
echo "  GEN_BATCH_SIZE:        $GEN_BATCH_SIZE"
echo "  TEMPERATURE:           $TEMPERATURE"
echo "  TOP_K:                 $TOP_K"
echo ""
echo "--- Pair Building Parameters ---"
echo "  PAIR_STRATEGY:         $PAIR_STRATEGY"
echo "  PAIR_GAP:              $PAIR_GAP"
echo "  PAIR_TOP_PERCENT:      $PAIR_TOP_PERCENT"
echo "  PAIR_BOTTOM_PERCENT:   $PAIR_BOTTOM_PERCENT"
echo "  PAIR_MIN_PER_PROMPT:   $PAIR_MIN_PER_PROMPT"
echo "  PAIR_MAX_PER_PROMPT:    $PAIR_MAX_PER_PROMPT"
echo "  MIN_PAIRS:             $MIN_PAIRS (min pairs per target required)"
echo ""
echo "--- DPO Training Parameters ---"
echo "  DPO_TOTAL_PAIRS:       $DPO_TOTAL_PAIRS (total pairs required for merge)"
echo "  DPO_BETA:              $DPO_BETA"
echo "  DPO_LR:                $DPO_LR"
echo "  DPO_STEPS:             $DPO_STEPS"
echo "  SCORE_FAILED_GATE_MODE:$SCORE_FAILED_GATE_MODE (threshold=$SCORE_FAILED_RATE_FAIL)"
echo ""
echo "--- Control Flags ---"
echo "  RESUME:                $RESUME"
echo "  CLEAN:                 $CLEAN"
echo ""
echo "=== END CONFIGURATION ==="
echo ""

# ---- Checkpoint / Resume support ----
CHECKPOINT_FILE="$EXP_DIR/.checkpoint"
RESUME=${RESUME:-0}
CLEAN=${CLEAN:-0}

mark_step_done() {
    local phase="$1"
    echo "$phase" > "$CHECKPOINT_FILE"
    echo "[checkpoint] Phase $phase done at $(date)"
    record_timing "$phase" "end"
}
last_done() { [ -f "$CHECKPOINT_FILE" ] && cat "$CHECKPOINT_FILE" || echo "0"; }

# cleanup_phase: force-delete phase output directories before rerun
cleanup_phase() {
    local phase="$1"
    if [ "$CLEAN" != "1" ]; then return; fi
    echo "[clean] Cleaning up Phase $phase artifacts..."
    case "$phase" in
        1)
            for t in "${TARGET_LIST[@]}"; do rm -rf "$EXP_DIR/$t/baseline"; done
            ;;
        2)
            rm -rf "$EXP_DIR/sft_shared"
            for b in "${BRANCH_LIST[@]}"; do rm -rf "$EXP_DIR/sft_$b/checkpoint"; done
            ;;
        3)
            for b in "${BRANCH_LIST[@]}"; do
                for t in "${TARGET_LIST[@]}"; do rm -rf "$EXP_DIR/$t/sft_$b"; done
            done
            ;;
        4)
            for b in "${BRANCH_LIST[@]}"; do rm -rf "$EXP_DIR/dpo_$b"; done
            ;;
        5)
            for b in "${BRANCH_LIST[@]}"; do
                rm -rf "$REPORT_DIR/three_way_$b"
                for t in "${TARGET_LIST[@]}"; do rm -rf "$EXP_DIR/$t/dpo_$b"; done
            done
            ;;
    esac
}

# ============================================================================
# Phase Validation Functions (Safe Resume)
# ============================================================================

# Phase 1: Baseline generation + scoring
is_phase1_done() {
    local target
    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        local scored_dir="$EXP_DIR/$target/baseline/scored"
        
        # Check required files exist
        if [ ! -f "$scored_dir/ehull_estimates.csv" ]; then
            echo "[validate] Phase 1: $target missing ehull_estimates.csv"
            return 1
        fi
        if [ ! -f "$scored_dir/composite_reward.csv" ]; then
            echo "[validate] Phase 1: $target missing composite_reward.csv"
            return 1
        fi
        
        # Quantitative check: scored CIF count
        local scored_count
        scored_count=$(count_scored_rows "$scored_dir/ehull_scores.csv")
        if [ "$scored_count" -lt "$MIN_SCORED_CIFS" ]; then
            echo "[validate] Phase 1: $target has $scored_count scored CIFs (required $MIN_SCORED_CIFS)"
            return 1
        fi
    done
    return 0
}

# Phase 2: SFT training
is_phase2_done() {
    local branch
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local sft_dir="$EXP_DIR/sft_$branch/checkpoint"
        
        # Check at least one checkpoint exists
        if [ ! -f "$sft_dir/ckpt.pt" ] && [ ! -f "$sft_dir/best_ckpt.pt" ]; then
            # Check for step checkpoints
            local step_ckpt
            step_ckpt=$(python3 -c "
from pathlib import Path
p = Path('$sft_dir')
cands = sorted(p.glob('step_*/ckpt.pt'))
print(str(cands[-1]) if cands else '')
" 2>/dev/null || true)
            if [ -z "$step_ckpt" ] || [ ! -f "$step_ckpt" ]; then
                echo "[validate] Phase 2: $branch missing SFT checkpoint"
                return 1
            fi
        fi
    done
    return 0
}

# Phase 3: SFT resample + pair building
is_phase3_done() {
    local total_pairs=0
    local branch target
    
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local branch_pairs=0
        
        for target in "${TARGET_LIST[@]}"; do
            target=$(echo "$target" | xargs)
            local pairs_file="$EXP_DIR/$target/sft_$branch/pairs/pairs.jsonl"
            
            if [ ! -f "$pairs_file" ]; then
                echo "[validate] Phase 3: $target [$branch] missing pairs.jsonl"
                return 1
            fi
            
            local count=$(wc -l < "$pairs_file")
            if [ "$count" -lt "$MIN_PAIRS" ]; then
                echo "[validate] Phase 3: $target [$branch] has $count pairs (required $MIN_PAIRS)"
                return 1
            fi
            
            branch_pairs=$((branch_pairs + count))
            total_pairs=$((total_pairs + count))
        done
        
        # Check total pairs per branch >= DPO_TOTAL_PAIRS
        if [ "$branch_pairs" -lt "$DPO_TOTAL_PAIRS" ]; then
            echo "[validate] Phase 3: branch $branch total pairs $branch_pairs < $DPO_TOTAL_PAIRS"
            return 1
        fi
    done
    
    echo "[validate] Phase 3: total available pairs=$total_pairs"
    return 0
}

# Phase 4: DPO training
is_phase4_done() {
    local branch
    local success_branches=0
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local dpo_dir="$EXP_DIR/dpo_$branch"
        local merged_file="$dpo_dir/merged_pairs.jsonl"
        local ckpt_dir="$dpo_dir/checkpoint"
        
        # Check merged pairs exists
        if [ ! -f "$merged_file" ]; then
            echo "[validate] Phase 4: $branch missing merged_pairs.jsonl"
            return 1
        fi
        
        # Check merged pairs count matches DPO_TOTAL_PAIRS
        local count=$(wc -l < "$merged_file")
        if [ "$count" -ne "$DPO_TOTAL_PAIRS" ]; then
            echo "[validate] Phase 4: $branch merged pairs $count != required $DPO_TOTAL_PAIRS"
            return 1
        fi
        
        # Require at least one usable checkpoint artifact.
        if [ -f "$ckpt_dir/ckpt.pt" ] || [ -f "$ckpt_dir/best_ckpt.pt" ]; then
            success_branches=$((success_branches + 1))
        else
            echo "[validate] Phase 4: $branch missing both ckpt.pt and best_ckpt.pt"
            return 1
        fi
    done
    if [ "$success_branches" -lt 1 ]; then
        echo "[validate] Phase 4: no branch has a usable DPO checkpoint"
        return 1
    fi
    return 0
}

# Phase 5: Final evaluation
is_phase5_done() {
    local branch target
    local success_branches=0
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local branch_three_way="$REPORT_DIR/three_way_$branch/three_way_summary.csv"
        if [ ! -f "$branch_three_way" ]; then
            echo "[validate] Phase 5: $branch missing three_way_summary.csv"
            continue
        fi
        success_branches=$((success_branches + 1))
        for target in "${TARGET_LIST[@]}"; do
            target=$(echo "$target" | xargs)
            local scored_dir="$EXP_DIR/$target/dpo_$branch/scored"
            
            # Check eval metrics exist
            if [ ! -f "$scored_dir/ehull_summary.json" ]; then
                echo "[validate] Phase 5: $target [$branch] missing ehull_summary.json"
                return 1
            fi
        done
    done
    if [ "$success_branches" -lt 1 ]; then
        echo "[validate] Phase 5: no branch has complete three-way outputs"
        return 1
    fi
    if [ ! -f "$REPORT_DIR/sft_rl_summary.md" ]; then
        echo "[validate] Phase 5: missing cross-branch summary sft_rl_summary.md"
        return 1
    fi
    return 0
}

# Main should_run function with safe resume
should_run() {
    local step="$1"; local last; last=$(last_done)
    
    # Handle CLEAN mode - force delete artifacts before running
    if [ "$CLEAN" = "1" ]; then
        cleanup_phase "$step"
        return 0
    fi
    
    if [ "$RESUME" = "1" ] && [ "$last" -ge "$step" ] 2>/dev/null; then
        # Validate phase-specific artifacts before skipping
        case "$step" in
            1)
                if ! is_phase1_done; then
                    echo "[resume] Phase 1 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            2)
                if ! is_phase2_done; then
                    echo "[resume] Phase 2 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            3)
                if ! is_phase3_done; then
                    echo "[resume] Phase 3 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            4)
                if ! is_phase4_done; then
                    echo "[resume] Phase 4 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            5)
                if ! is_phase5_done; then
                    echo "[resume] Phase 5 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
        esac
        
        echo "[resume] Skipping phase $step (already done, last=$last)"
        return 1
    fi
    return 0
}

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

# =====================================================================
# PHASE 1: Multi-composition baseline generation + scoring
# =====================================================================
if should_run 1; then
record_timing "1" "start"
echo ""
echo "=========================================="
echo "Phase 1: Multi-Composition Baseline Generation"
echo "=========================================="

for target in "${TARGET_LIST[@]}"; do
    target=$(echo "$target" | xargs)  # trim
    PROMPT_CIF=$(build_prompt "$target")
    TARGET_DIR="$EXP_DIR/$target/baseline"
    CIF_DIR="$TARGET_DIR/raw_cifs"
    SCORED_DIR="$TARGET_DIR/scored"
    VALID_DIR="$SCORED_DIR/valid_cifs"

    echo ""
    echo "---- Target: $target  Prompt: $PROMPT_CIF ----"
    mkdir -p "$CIF_DIR" "$SCORED_DIR" "$VALID_DIR"

    # Diversity args
    DIVERSITY_ARGS=""
    [ -n "$TEMPERATURE_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --temperature_range $TEMPERATURE_RANGE"
    [ -n "$TOP_K_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --top_k_range $TOP_K_RANGE"

    # Generate
    export MAX_RETRIES
    conda run -n myenv python "$SCRIPT_DIR/40_generate_cifs_crystallm.py" \
        --ckpt_dir "$CRYSTALLM_CKPT_DIR" \
        --pkg_dir "$CRYSTALLM_PKG_DIR" \
        --out_dir "$CIF_DIR" \
        --prompt "$PROMPT_CIF" \
        --n "$NUM_SAMPLES" \
        --max_tokens "$MAX_TOKENS" \
        --top_k "$TOP_K" \
        --temperature "$TEMPERATURE" \
        --seed "$SEED" \
        --batch_size "$GEN_BATCH_SIZE" \
        --device cuda \
        $DIVERSITY_ARGS

    # Validate
    conda run -n myenv python "$SCRIPT_DIR/11_validate_cifs.py" \
        --in_dir "$CIF_DIR" --out_dir "$SCORED_DIR"

    # Quality gate: valid CIF count
    N_VALID=$(count_cif_files "$VALID_DIR")
    echo "  Valid CIFs: $N_VALID (gate: $MIN_VALID_CIFS)"
    if [ "$N_VALID" -lt "$MIN_VALID_CIFS" ]; then
        echo "ERROR: Too few valid CIFs for $target ($N_VALID < $MIN_VALID_CIFS). Aborting."
        exit 1
    fi

    # Label
    conda run -n myenv python "$SCRIPT_DIR/12_label_cifs.py" \
        --in_dir "$CIF_DIR" --out_csv "$SCORED_DIR/labels.csv" --target "$target"

    # MatGL scoring
    conda run -n matgl_env bash -c "
        [ \"\$MATGL_FIX_LD_LIBRARY_PATH\" = '1' ] && export LD_LIBRARY_PATH=\"\$CONDA_PREFIX/lib:\$LD_LIBRARY_PATH\"
        python $SCRIPT_DIR/35_score_dir_matgl.py --in_dir $VALID_DIR --out_csv $SCORED_DIR/ehull_scores.csv
    "

    # Quality gate: scored CIF count (only rows with non-empty score_e_per_atom)
    N_SCORED=$(count_scored_rows "$SCORED_DIR/ehull_scores.csv")
    echo "  Scored CIFs: $N_SCORED (gate: $MIN_SCORED_CIFS)"
    if [ "$N_SCORED" -lt "$MIN_SCORED_CIFS" ]; then
        echo "ERROR: Too few scored CIFs for $target ($N_SCORED < $MIN_SCORED_CIFS). Aborting."
        exit 1
    fi
    if ! check_score_fail_rate "$SCORED_DIR" "baseline/$target"; then
        echo "ERROR: Score fail-rate gate failed for baseline/$target."
        exit 1
    fi

    merge_eval_csv "$SCORED_DIR"

    # Ehull estimation
    conda run -n myenv python "$SCRIPT_DIR/36_estimate_ehull.py" \
        --scores_csv "$SCORED_DIR/ehull_scores.csv" \
        --out_csv "$SCORED_DIR/ehull_estimates.csv" \
        || echo "WARNING: Ehull failed for $target"

    # Composite reward
    echo "Computing composite reward for $target ..."
    conda run -n myenv python "$SCRIPT_DIR/48_compute_composite_reward.py" \
        --scores_csv "$SCORED_DIR/ehull_scores.csv" \
        --cif_dir "$CIF_DIR" \
        --target "$target" \
        --out_csv "$SCORED_DIR/composite_reward.csv" \
        --w_proxy "$REWARD_W_PROXY" \
        --w_geom "$REWARD_W_GEOM" \
        --w_comp "$REWARD_W_COMP" \
        --w_novel "$REWARD_W_NOVEL" \
        --min_interatomic_distance "$REWARD_MIN_INTERATOMIC_DISTANCE" \
        --proxy_buffer_size "$REWARD_PROXY_BUFFER_SIZE" \
        --novelty_window "$REWARD_NOVELTY_WINDOW" \
        --rolling_buffer_dir "$EXP_DIR/reward_buffers" \
        $( [ "$REWARD_ENABLE_DENSITY_GATE" = "1" ] && echo "--enable_density_gate" ) \
        --density_min "$REWARD_DENSITY_MIN" \
        --density_max "$REWARD_DENSITY_MAX" \
        || echo "WARNING: Composite reward failed for $target"

    check_reward_spread "$SCORED_DIR" "baseline/$target"

    echo "---- $target baseline done ----"
done

mark_step_done 1
fi

# =====================================================================
# PHASE 2: SFT on stable structures — one per ablation branch
# =====================================================================

if should_run 2; then
record_timing "2" "start"
echo ""
echo "=========================================="
echo "Phase 2: Multi-Composition SFT Training"
echo "=========================================="

# Prepare shared SFT training data (once)
SFT_DATA_DIR="$EXP_DIR/sft_shared"
mkdir -p "$SFT_DATA_DIR"

EHULL_CSVS=""
CIF_DIRS=""
MISSING_EHULL_INPUTS=()
for target in "${TARGET_LIST[@]}"; do
    target=$(echo "$target" | xargs)
    EHULL_CSV="$EXP_DIR/$target/baseline/scored/ehull_estimates.csv"
    if [ ! -f "$EHULL_CSV" ]; then
        MISSING_EHULL_INPUTS+=("$target:$EHULL_CSV")
    fi
    EHULL_CSVS="${EHULL_CSVS:+$EHULL_CSVS,}$EHULL_CSV"
    CIF_DIRS="${CIF_DIRS:+$CIF_DIRS,}$EXP_DIR/$target/baseline/raw_cifs"
done

if [ "${#MISSING_EHULL_INPUTS[@]}" -gt 0 ]; then
    echo "ERROR: Missing Phase 2 input files (ehull_estimates.csv):"
    for miss in "${MISSING_EHULL_INPUTS[@]}"; do
        echo "  - $miss"
    done
    echo "ERROR: Cannot prepare shared SFT data until all baseline scored inputs exist."
    exit 1
fi

SFT_JSONL="$SFT_DATA_DIR/sft_data.jsonl"
if [ ! -f "$SFT_JSONL" ] || [ ! -s "$SFT_JSONL" ]; then
    echo "Preparing multi-composition SFT data ..."
    conda run -n myenv python "$SCRIPT_DIR/47_prepare_sft_data.py" \
        --ehull_csv "$EHULL_CSVS" \
        --cif_dir "$CIF_DIRS" \
        --pkg_dir "$CRYSTALLM_PKG_DIR" \
        --out_jsonl "$SFT_JSONL" \
        --ehull_threshold "$EHULL_THRESHOLD" \
        --max_tokens "$MAX_TOKENS"
fi

SFT_DATA_COUNT=$(wc -l < "$SFT_JSONL" 2>/dev/null || echo 0)
echo "SFT training data: $SFT_DATA_COUNT samples"

if [ "$SFT_DATA_COUNT" -lt 10 ]; then
    echo "ERROR: Too few SFT samples ($SFT_DATA_COUNT). Aborting."
    exit 1
fi

# Train each branch
for branch in "${BRANCH_LIST[@]}"; do
    branch=$(echo "$branch" | xargs)
    B_STRATEGY=$(branch_var "$branch" STRATEGY "${SFT_STRATEGY:-lora}")
    B_LR=$(branch_var "$branch" LR "${SFT_LR:-5e-8}")
    B_STEPS=$(branch_var "$branch" STEPS "${SFT_STEPS:-6000}")
    B_GRAD_ACCUM=$(branch_var "$branch" GRAD_ACCUM "${SFT_GRAD_ACCUM:-8}")
    B_WARMUP=$(branch_var "$branch" WARMUP "${SFT_WARMUP:-200}")
    B_LORA_RANK=$(branch_var "$branch" LORA_RANK "${SFT_LORA_RANK:-16}")
    B_LORA_TARGETS=$(branch_var "$branch" LORA_TARGETS "c_attn")
    B_WEIGHT_DECAY=$(branch_var "$branch" WEIGHT_DECAY "${SFT_WEIGHT_DECAY:-0.01}")
    B_MAX_GRAD_NORM=$(branch_var "$branch" MAX_GRAD_NORM "${SFT_MAX_GRAD_NORM:-1.0}")
    B_SAVE_EVERY=$(branch_var "$branch" SAVE_EVERY "${SFT_SAVE_EVERY:-1000}")

    SFT_BRANCH_DIR="$EXP_DIR/sft_$branch"
    SFT_BRANCH_CKPT="$SFT_BRANCH_DIR/checkpoint"
    mkdir -p "$SFT_BRANCH_CKPT"

    echo ""
    echo "---- SFT branch: $branch (strategy=$B_STRATEGY, lr=$B_LR, steps=$B_STEPS, wd=$B_WEIGHT_DECAY) ----"

    LORA_ARGS=""
    if [ "$B_STRATEGY" = "lora" ]; then
        LORA_ARGS="--lora_rank $B_LORA_RANK"
        [ -n "$B_LORA_TARGETS" ] && LORA_ARGS="$LORA_ARGS --lora_target_names $B_LORA_TARGETS"
    fi

    if ! conda run -n dpo_crystallm python "$SCRIPT_DIR/33_train_sft_crystallm.py" \
        --data_jsonl "$SFT_JSONL" \
        --ckpt_dir "$CRYSTALLM_CKPT_DIR" \
        --pkg_dir "$CRYSTALLM_PKG_DIR" \
        --out_dir "$SFT_BRANCH_CKPT" \
        --steps "$B_STEPS" \
        --lr "$B_LR" \
        --grad_accum_steps "$B_GRAD_ACCUM" \
        --max_grad_norm "$B_MAX_GRAD_NORM" \
        --save_every "$B_SAVE_EVERY" \
        --warmup_steps "$B_WARMUP" \
        --weight_decay "$B_WEIGHT_DECAY" \
        --strategy "$B_STRATEGY" \
        --device cuda \
        --seed "$SEED" \
        $LORA_ARGS; then
        log_error "2" "run_sft_rl_pipeline.sh:SFT_TRAIN" "SFT training failed for branch" "{\"branch\":\"$branch\",\"strategy\":\"$B_STRATEGY\",\"steps\":$B_STEPS}"
        echo "ERROR: SFT training failed for branch=$branch"
        continue
    fi

    echo "SFT [$branch] complete. Checkpoint: $SFT_BRANCH_CKPT/ckpt.pt"
done

mark_step_done 2
fi

# =====================================================================
# PHASE 3: SFT model resample + scoring + pair building (per branch)
# =====================================================================
if should_run 3; then
record_timing "3" "start"
echo ""
echo "=========================================="
echo "Phase 3: SFT Model Resample + Scoring"
echo "=========================================="

PHASE3_SUCCESS_BRANCHES=0
for branch in "${BRANCH_LIST[@]}"; do
    branch=$(echo "$branch" | xargs)
    BRANCH_QUALIFIED_TARGETS=0
    SFT_BEST_CKPT="$EXP_DIR/sft_$branch/checkpoint/best_ckpt.pt"
    SFT_CKPT_FILE="$EXP_DIR/sft_$branch/checkpoint/ckpt.pt"
    if [ -f "$SFT_BEST_CKPT" ]; then
        SFT_CKPT_FILE="$SFT_BEST_CKPT"
        echo "Using best SFT checkpoint for branch=$branch: $SFT_CKPT_FILE"
    elif [ ! -f "$SFT_CKPT_FILE" ]; then
        echo "ERROR: SFT checkpoint not found for branch=$branch at $SFT_CKPT_FILE"
        exit 1
    fi

    echo ""
    echo "==== Branch: $branch ===="

    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        PROMPT_CIF=$(build_prompt "$target")
        TARGET_DIR="$EXP_DIR/$target/sft_$branch"
        CIF_DIR="$TARGET_DIR/raw_cifs"
        SCORED_DIR="$TARGET_DIR/scored"
        VALID_DIR="$SCORED_DIR/valid_cifs"

        echo ""
        echo "---- SFT[$branch] resample: $target  Prompt: $PROMPT_CIF ----"
        mkdir -p "$CIF_DIR" "$SCORED_DIR" "$VALID_DIR"

        DIVERSITY_ARGS=""
        [ -n "$TEMPERATURE_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --temperature_range $TEMPERATURE_RANGE"
        [ -n "$TOP_K_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --top_k_range $TOP_K_RANGE"

        conda run -n myenv python "$SCRIPT_DIR/40_generate_cifs_crystallm.py" \
            --ckpt_dir "$SFT_CKPT_FILE" \
            --pkg_dir "$CRYSTALLM_PKG_DIR" \
            --out_dir "$CIF_DIR" \
            --prompt "$PROMPT_CIF" \
            --n "$NUM_SAMPLES" \
            --max_tokens "$MAX_TOKENS" \
            --top_k "$TOP_K" \
            --temperature "$TEMPERATURE" \
            --seed "$SEED" \
            --batch_size "$GEN_BATCH_SIZE" \
            --device cuda \
            $DIVERSITY_ARGS

        conda run -n myenv python "$SCRIPT_DIR/11_validate_cifs.py" \
            --in_dir "$CIF_DIR" --out_dir "$SCORED_DIR"

        # Validity gate
        TOTAL_GEN=$(count_cif_files "$CIF_DIR")
        TOTAL_VALID=$(count_cif_files "$VALID_DIR")
        if [ "$TOTAL_GEN" -gt 0 ]; then
            VALIDITY_CHECK=$(python3 -c "valid=$TOTAL_VALID; total=$TOTAL_GEN; pct=100*valid/total if total else 0.0; print(f'{pct:.1f} {1 if pct < 50 else 0}')")
            read -r VALID_PCT VALID_LT50 <<< "$VALIDITY_CHECK"
            echo "  Validity: $TOTAL_VALID / $TOTAL_GEN ($VALID_PCT%)"
            if [ "$VALID_LT50" = "1" ]; then
                echo "  WARNING: SFT[$branch] $target validity=$VALID_PCT% < 50% — model may be overfitting"
            fi
        fi
        if [ "$TOTAL_VALID" -lt "$MIN_VALID_CIFS" ]; then
            echo "ERROR: Too few valid CIFs for SFT[$branch] $target ($TOTAL_VALID < $MIN_VALID_CIFS). Aborting."
            exit 1
        fi

        conda run -n myenv python "$SCRIPT_DIR/12_label_cifs.py" \
            --in_dir "$CIF_DIR" --out_csv "$SCORED_DIR/labels.csv" --target "$target"
        conda run -n matgl_env bash -c "
            [ \"\$MATGL_FIX_LD_LIBRARY_PATH\" = '1' ] && export LD_LIBRARY_PATH=\"\$CONDA_PREFIX/lib:\$LD_LIBRARY_PATH\"
            python $SCRIPT_DIR/35_score_dir_matgl.py --in_dir $VALID_DIR --out_csv $SCORED_DIR/ehull_scores.csv
        "

        # Quality gate: scored CIF count (only rows with non-empty score_e_per_atom)
        N_SCORED=$(count_scored_rows "$SCORED_DIR/ehull_scores.csv")
        echo "  Scored CIFs: $N_SCORED (gate: $MIN_SCORED_CIFS)"
        if [ "$N_SCORED" -lt "$MIN_SCORED_CIFS" ]; then
            echo "ERROR: Too few scored CIFs for SFT[$branch] $target ($N_SCORED < $MIN_SCORED_CIFS). Aborting."
            exit 1
        fi
        if ! check_score_fail_rate "$SCORED_DIR" "SFT[$branch]/$target"; then
            echo "ERROR: Score fail-rate gate failed for SFT[$branch]/$target."
            exit 1
        fi

        merge_eval_csv "$SCORED_DIR"

        conda run -n myenv python "$SCRIPT_DIR/36_estimate_ehull.py" \
            --scores_csv "$SCORED_DIR/ehull_scores.csv" \
            --out_csv "$SCORED_DIR/ehull_estimates.csv" \
            || echo "WARNING: Ehull failed for $target (SFT[$branch])"

        conda run -n myenv python "$SCRIPT_DIR/48_compute_composite_reward.py" \
            --scores_csv "$SCORED_DIR/ehull_scores.csv" \
            --cif_dir "$CIF_DIR" \
            --target "$target" \
            --out_csv "$SCORED_DIR/composite_reward.csv" \
            --w_proxy "$REWARD_W_PROXY" \
            --w_geom "$REWARD_W_GEOM" \
            --w_comp "$REWARD_W_COMP" \
            --w_novel "$REWARD_W_NOVEL" \
            --min_interatomic_distance "$REWARD_MIN_INTERATOMIC_DISTANCE" \
            --proxy_buffer_size "$REWARD_PROXY_BUFFER_SIZE" \
            --novelty_window "$REWARD_NOVELTY_WINDOW" \
            --rolling_buffer_dir "$EXP_DIR/reward_buffers" \
            $( [ "$REWARD_ENABLE_DENSITY_GATE" = "1" ] && echo "--enable_density_gate" ) \
            --density_min "$REWARD_DENSITY_MIN" \
            --density_max "$REWARD_DENSITY_MAX" \
            || echo "WARNING: Composite reward failed for $target (SFT[$branch])"

        check_reward_spread "$SCORED_DIR" "SFT[$branch]/$target"

        PAIRS_DIR="$TARGET_DIR/pairs"
        mkdir -p "$PAIRS_DIR"
        if conda run -n myenv python "$SCRIPT_DIR/41_build_pairs_with_token_filter.py" \
            --labels_csv "$SCORED_DIR/labels.csv" \
            --scores_csv "$SCORED_DIR/ehull_scores.csv" \
            --reward_csv "$SCORED_DIR/composite_reward.csv" \
            --cif_dir "$CIF_DIR" \
            --pkg_dir "$CRYSTALLM_PKG_DIR" \
            --out_jsonl "$PAIRS_DIR/pairs.jsonl" \
            --target "$target" \
            --strategy "$PAIR_STRATEGY" \
            --max_tokens "$MAX_TOKENS" \
            --gap "$PAIR_GAP" \
            --seed "$SEED" \
            --top_percent "$PAIR_TOP_PERCENT" \
            --bottom_percent "$PAIR_BOTTOM_PERCENT" \
            --pair_min_per_prompt "$PAIR_MIN_PER_PROMPT" \
            --pair_max_per_prompt "$PAIR_MAX_PER_PROMPT" \
            --prompt_cif "$(build_prompt "$target")"; then
            N_PAIRS=$(wc -l < "$PAIRS_DIR/pairs.jsonl" 2>/dev/null || echo 0)
            echo "  Pairs: $N_PAIRS (gate: $MIN_PAIRS)"
            # #region agent log
            debug_log "pre-fix-1" "H2" "run_sft_rl_pipeline.sh:PHASE3_PAIRS" "Pair construction result per target" "{\"branch\":\"$branch\",\"target\":\"$target\",\"pairs\":$N_PAIRS,\"min_pairs\":$MIN_PAIRS,\"pair_max_per_prompt\":$PAIR_MAX_PER_PROMPT,\"pair_strategy\":\"$PAIR_STRATEGY\",\"pair_top_percent\":$PAIR_TOP_PERCENT,\"pair_bottom_percent\":$PAIR_BOTTOM_PERCENT}"
            # #endregion
            # FAIL-FAST: Abort if pairs are insufficient
            if [ "$N_PAIRS" -lt "$MIN_PAIRS" ]; then
                echo "ERROR: Too few pairs for $target [$branch] ($N_PAIRS < $MIN_PAIRS). Aborting pipeline."
                echo "       Check generation settings or reduce MIN_PAIRS in config."
                exit 1
            else
                BRANCH_QUALIFIED_TARGETS=$((BRANCH_QUALIFIED_TARGETS + 1))
                echo "---- $target SFT[$branch] resample done ----"
            fi
        else
            echo "WARNING: Pair building failed for $target [$branch]. Skipping."
        fi
    done

    if [ "$BRANCH_QUALIFIED_TARGETS" -gt 0 ]; then
        PHASE3_SUCCESS_BRANCHES=$((PHASE3_SUCCESS_BRANCHES + 1))
        echo "Branch $branch qualified targets: $BRANCH_QUALIFIED_TARGETS"
    else
        echo "WARNING: Branch $branch produced no targets passing MIN_PAIRS=$MIN_PAIRS."
    fi
done

if [ "$PHASE3_SUCCESS_BRANCHES" -gt 0 ]; then
    mark_step_done 3
else
    echo "ERROR: Phase 3 failed — no branch produced targets passing MIN_PAIRS=$MIN_PAIRS."
    exit 1
fi
fi

# =====================================================================
# PHASE 4: DPO training — one per ablation branch
# =====================================================================

if should_run 4; then
record_timing "4" "start"
echo ""
echo "=========================================="
echo "Phase 4: DPO Training"
echo "=========================================="

PHASE4_SUCCESS_BRANCHES=0
for branch in "${BRANCH_LIST[@]}"; do
    branch=$(echo "$branch" | xargs)
    DPO_DIR="$EXP_DIR/dpo_$branch"
    DPO_CKPT_DIR="$DPO_DIR/checkpoint"
    mkdir -p "$DPO_DIR" "$DPO_CKPT_DIR"

    echo ""
    echo "==== DPO for branch: $branch ===="

    PAIR_DIRS=""
    ACTIVE_TARGETS=()
    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        PAIR_FILE="$EXP_DIR/$target/sft_$branch/pairs/pairs.jsonl"
        PAIR_COUNT=$(wc -l < "$PAIR_FILE" 2>/dev/null || echo 0)
        # #region agent log
        debug_log "pre-fix-1" "H1" "run_sft_rl_pipeline.sh:PHASE4_TARGET_FILTER" "Phase4 pair count before MIN_PAIRS filter" "{\"branch\":\"$branch\",\"target\":\"$target\",\"pair_count\":$PAIR_COUNT,\"min_pairs\":$MIN_PAIRS,\"dpo_total_pairs\":$DPO_TOTAL_PAIRS}"
        # #endregion
        if [ "$PAIR_COUNT" -ge "$MIN_PAIRS" ]; then
            PAIR_DIRS="${PAIR_DIRS:+$PAIR_DIRS,}$EXP_DIR/$target/sft_$branch"
            ACTIVE_TARGETS+=("$target")
            echo "  $target [$branch]: pairs=$PAIR_COUNT (>= $MIN_PAIRS)"
        elif [ -f "$PAIR_FILE" ] && [ -s "$PAIR_FILE" ]; then
            echo "WARNING: Skipping $target [$branch] (pairs=$PAIR_COUNT < MIN_PAIRS=$MIN_PAIRS)"
        else
            echo "WARNING: Skipping $target [$branch] (no pairs.jsonl or empty)"
        fi
    done

    if [ -z "$PAIR_DIRS" ]; then
        echo "ERROR: No targets produced valid pairs for branch=$branch. Skipping branch."
        continue
    fi
    echo "Active targets for DPO[$branch]: ${ACTIVE_TARGETS[*]} (${#ACTIVE_TARGETS[@]}/${#TARGET_LIST[@]})"

    # ============================================================================
    # GUARD: Check if available pairs >= DPO_TOTAL_PAIRS before training
    # ============================================================================
    echo ""
    echo "--- Pre-Merge Availability Check for branch=$branch ---"
    TOTAL_AVAILABLE_PAIRS=0
    for target in "${ACTIVE_TARGETS[@]}"; do
        target=$(echo "$target" | xargs)
        PAIR_FILE="$EXP_DIR/$target/sft_$branch/pairs/pairs.jsonl"
        PAIR_COUNT=$(wc -l < "$PAIR_FILE" 2>/dev/null || echo 0)
        TOTAL_AVAILABLE_PAIRS=$((TOTAL_AVAILABLE_PAIRS + PAIR_COUNT))
        echo "  $target: $PAIR_COUNT pairs"
    done
    echo "  Total available: $TOTAL_AVAILABLE_PAIRS pairs"
    echo "  Required (DPO_TOTAL_PAIRS): $DPO_TOTAL_PAIRS pairs"
    
    if [ "$TOTAL_AVAILABLE_PAIRS" -lt "$DPO_TOTAL_PAIRS" ]; then
        echo ""
        echo "╔══════════════════════════════════════════════════════════════════════════════╗"
        echo "║  ERROR: INSUFFICIENT PAIRS FOR DPO TRAINING                                ║"
        echo "╠══════════════════════════════════════════════════════════════════════════════╣"
        echo "║  Available pairs:  $TOTAL_AVAILABLE_PAIRS                                   ║"
        echo "║  Required pairs:    $DPO_TOTAL_PAIRS                                        ║"
        echo "║  Shortfall:         $((DPO_TOTAL_PAIRS - TOTAL_AVAILABLE_PAIRS))                                         ║"
        echo "╠══════════════════════════════════════════════════════════════════════════════╣"
        echo "║  RECOMMENDATIONS:                                                            ║"
        echo "║  1. Increase NUM_SAMPLES (currently $NUM_SAMPLES) to generate more samples   ║"
        echo "║  2. Decrease DPO_TOTAL_PAIRS (currently $DPO_TOTAL_PAIRS) to match available ║"
        echo "║  3. Decrease MIN_PAIRS (currently $MIN_PAIRS) to accept fewer pairs/target   ║"
        echo "║  4. Check PAIR_STRATEGY='$PAIR_STRATEGY' is appropriate for your data        ║"
        echo "╚══════════════════════════════════════════════════════════════════════════════╝"
        echo ""
        echo "ERROR: Cannot proceed with DPO training - insufficient pairs. Aborting."
        exit 1
    fi
    echo "  ✓ Sufficient pairs available for merge ($TOTAL_AVAILABLE_PAIRS >= $DPO_TOTAL_PAIRS)"
    echo ""

    # Dynamic per-target allocation to exact DPO_TOTAL_PAIRS (no cross-target pairing).
    TARGETS_CSV=$(IFS=','; echo "${ACTIVE_TARGETS[*]}")
    # #region agent log
    debug_log "pre-fix-1" "H1" "run_sft_rl_pipeline.sh:PHASE4_ACTIVE_TARGETS" "Active targets selected for DPO merge" "{\"branch\":\"$branch\",\"active_targets\":\"$TARGETS_CSV\",\"active_count\":${#ACTIVE_TARGETS[@]},\"total_targets\":${#TARGET_LIST[@]},\"dpo_total_pairs\":$DPO_TOTAL_PAIRS}"
    # #endregion
    # Use shared pair_merge.py module for pair merging
    if ! conda run -n myenv python "$SCRIPT_DIR/shared/pair_merge.py" \
            --exp_dir "$EXP_DIR" \
            --targets "$TARGETS_CSV" \
            --branch "$branch" \
            --target_total "$DPO_TOTAL_PAIRS" \
            --seed "$SEED" \
            --out "$DPO_DIR/merged_pairs.jsonl" \
            --log_path "$PROJECT_ROOT/.cursor/debug-25e703.log" \
            --run_id "pre-fix-1"; then
        echo "ERROR: Pair merge failed for branch=$branch. Skipping branch."
        continue
    fi

    # NOTE: Pair merge is performed by pair_merge.py module above.
    # (Reference implementation removed to avoid bash syntax issues with embedded Python.)

    MERGED_PAIRS=$(wc -l < "$DPO_DIR/merged_pairs.jsonl" 2>/dev/null || echo 0)
    echo "Total merged pairs [$branch]: $MERGED_PAIRS"

    # FAIL-FAST: Abort if merged pairs don't match exactly
    if [ "$MERGED_PAIRS" -ne "$DPO_TOTAL_PAIRS" ]; then
        echo "ERROR: Merged pairs mismatch for $branch ($MERGED_PAIRS != $DPO_TOTAL_PAIRS). Aborting pipeline."
        echo "       Check Phase 3 pair generation or adjust DPO_TOTAL_PAIRS."
        exit 1
    fi

    SFT_BEST_CKPT="$EXP_DIR/sft_$branch/checkpoint/best_ckpt.pt"
    SFT_FINAL_CKPT="$EXP_DIR/sft_$branch/checkpoint/ckpt.pt"
    SFT_CKPT_FILE=""
    if [ -f "$SFT_BEST_CKPT" ]; then
        SFT_CKPT_FILE="$SFT_BEST_CKPT"
        echo "Using best SFT checkpoint for DPO[$branch]: $SFT_CKPT_FILE"
    elif [ -f "$SFT_FINAL_CKPT" ]; then
        SFT_CKPT_FILE="$SFT_FINAL_CKPT"
        echo "Using final SFT checkpoint for DPO[$branch]: $SFT_CKPT_FILE"
    else
        echo "ERROR: SFT checkpoint missing for DPO[$branch]."
        echo "  Candidate paths:"
        echo "    - $SFT_BEST_CKPT"
        echo "    - $SFT_FINAL_CKPT"
        echo "Skipping DPO[$branch] due to missing SFT checkpoint."
        continue
    fi
    REWARD_ARGS=""
    if [ "$DPO_REWARD_WEIGHTED" = "1" ]; then
        REWARD_ARGS="--reward_weighted --reward_alpha $DPO_REWARD_ALPHA"
    fi

    echo "Training DPO[$branch] on SFT checkpoint ..."
    conda run -n dpo_crystallm python "$SCRIPT_DIR/32_train_dpo_crystallm.py" \
        --pairs "$DPO_DIR/merged_pairs.jsonl" \
        --ckpt_dir "$SFT_CKPT_FILE" \
        --pkg_dir "$CRYSTALLM_PKG_DIR" \
        --out_dir "$DPO_CKPT_DIR" \
        --steps "$DPO_STEPS" \
        --beta "$DPO_BETA" \
        --lr "$DPO_LR" \
        --grad_accum_steps "$DPO_GRAD_ACCUM" \
        --max_grad_norm "$DPO_MAX_GRAD_NORM" \
        --save_every "$DPO_SAVE_EVERY" \
        --strategy "$DPO_STRATEGY" \
        --lora_rank "$DPO_LORA_RANK" \
        --warmup_steps "$DPO_WARMUP" \
        --loss_type "$DPO_LOSS_TYPE" \
        --label_smoothing "$DPO_LABEL_SMOOTHING" \
        --simpo_gamma "$DPO_SIMPO_GAMMA" \
        --weight_decay "$DPO_WEIGHT_DECAY" \
        --device cuda \
        --seed "$SEED" \
        $REWARD_ARGS

    echo "DPO[$branch] training complete. Checkpoint: $DPO_CKPT_DIR/ckpt.pt"
    if [ -f "$DPO_CKPT_DIR/ckpt.pt" ] || [ -f "$DPO_CKPT_DIR/best_ckpt.pt" ]; then
        PHASE4_SUCCESS_BRANCHES=$((PHASE4_SUCCESS_BRANCHES + 1))
    else
        echo "WARNING: DPO[$branch] finished without checkpoint artifact."
    fi
done

if [ "$PHASE4_SUCCESS_BRANCHES" -gt 0 ]; then
    mark_step_done 4
else
    echo "ERROR: Phase 4 failed — no branch completed DPO training."
    exit 1
fi
fi

# =====================================================================
# PHASE 5: Final Evaluation + Cross-Branch Comparison
# =====================================================================
if should_run 5; then
record_timing "5" "start"
echo ""
echo "=========================================="
echo "Phase 5: Final Evaluation + Comparison"
echo "=========================================="

PHASE5_SUCCESS_BRANCHES=0
for branch in "${BRANCH_LIST[@]}"; do
    branch=$(echo "$branch" | xargs)
    BRANCH_EVAL_OK=0
    DPO_BEST_CKPT="$EXP_DIR/dpo_$branch/checkpoint/best_ckpt.pt"
    DPO_FINAL_CKPT="$EXP_DIR/dpo_$branch/checkpoint/ckpt.pt"
    if [ -f "$DPO_BEST_CKPT" ]; then
        DPO_FINAL_CKPT="$DPO_BEST_CKPT"
        echo "Using best checkpoint for branch=$branch: $DPO_FINAL_CKPT"
    elif [ ! -f "$DPO_FINAL_CKPT" ]; then
        echo "WARNING: DPO checkpoint not found for branch=$branch. Skipping eval."
        continue
    fi

    EVAL_TARGETS=()
    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        PAIR_FILE="$EXP_DIR/$target/sft_$branch/pairs/pairs.jsonl"
        PAIR_COUNT=$(wc -l < "$PAIR_FILE" 2>/dev/null || echo 0)
        if [ "$PAIR_COUNT" -ge "$MIN_PAIRS" ]; then
            EVAL_TARGETS+=("$target")
            echo "  $target eval [$branch]: pairs=$PAIR_COUNT (>= $MIN_PAIRS)"
        elif [ -f "$PAIR_FILE" ] && [ -s "$PAIR_FILE" ]; then
            echo "WARNING: Skipping $target evaluation [$branch] (pairs=$PAIR_COUNT < MIN_PAIRS=$MIN_PAIRS)"
        else
            echo "WARNING: Skipping $target evaluation [$branch] (no pairs)"
        fi
    done
    if [ "${#EVAL_TARGETS[@]}" -eq 0 ]; then
        echo "WARNING: No valid evaluation targets for branch=$branch. Skipping eval."
        continue
    fi
    echo "Evaluating branch=$branch targets: ${EVAL_TARGETS[*]}"

    for target in "${EVAL_TARGETS[@]}"; do
        target=$(echo "$target" | xargs)
        PROMPT_CIF=$(build_prompt "$target")

        echo ""
        echo "---- Final eval [$branch]: $target ----"

        FINAL_DIR="$EXP_DIR/$target/dpo_$branch"
        CIF_DIR="$FINAL_DIR/raw_cifs"
        SCORED_DIR="$FINAL_DIR/scored"
        VALID_DIR="$SCORED_DIR/valid_cifs"
        mkdir -p "$CIF_DIR" "$SCORED_DIR" "$VALID_DIR"

        DIVERSITY_ARGS=""
        [ -n "$TEMPERATURE_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --temperature_range $TEMPERATURE_RANGE"
        [ -n "$TOP_K_RANGE" ] && DIVERSITY_ARGS="$DIVERSITY_ARGS --top_k_range $TOP_K_RANGE"

        if ! conda run -n myenv python "$SCRIPT_DIR/40_generate_cifs_crystallm.py" \
            --ckpt_dir "$DPO_FINAL_CKPT" \
            --pkg_dir "$CRYSTALLM_PKG_DIR" \
            --out_dir "$CIF_DIR" \
            --prompt "$PROMPT_CIF" \
            --n "$NUM_SAMPLES" \
            --max_tokens "$MAX_TOKENS" \
            --top_k "$TOP_K" \
            --temperature "$TEMPERATURE" \
            --seed "$SEED" \
            --batch_size "$GEN_BATCH_SIZE" \
            --device cuda \
            $DIVERSITY_ARGS; then
            echo "ERROR: CIF generation failed for $target (DPO[$branch]). Skipping target."
            continue
        fi

        if ! conda run -n myenv python "$SCRIPT_DIR/11_validate_cifs.py" \
            --in_dir "$CIF_DIR" --out_dir "$SCORED_DIR"; then
            echo "WARNING: CIF validation failed for $target (DPO[$branch]). Continuing with empty validation."
        fi
        if ! conda run -n myenv python "$SCRIPT_DIR/12_label_cifs.py" \
            --in_dir "$CIF_DIR" --out_csv "$SCORED_DIR/labels.csv" --target "$target"; then
            echo "ERROR: CIF labeling failed for $target (DPO[$branch]). Skipping target."
            continue
        fi
        if ! conda run -n matgl_env bash -c "
            [ \"\$MATGL_FIX_LD_LIBRARY_PATH\" = '1' ] && export LD_LIBRARY_PATH=\"\$CONDA_PREFIX/lib:\$LD_LIBRARY_PATH\"
            python $SCRIPT_DIR/35_score_dir_matgl.py --in_dir $VALID_DIR --out_csv $SCORED_DIR/ehull_scores.csv
        "; then
            echo "ERROR: MatGL scoring failed for $target (DPO[$branch]). Skipping target."
            continue
        fi

        N_SCORED=$(count_scored_rows "$SCORED_DIR/ehull_scores.csv")
        echo "  Scored CIFs: $N_SCORED (gate: $MIN_SCORED_CIFS)"
        if [ "$N_SCORED" -lt "$MIN_SCORED_CIFS" ]; then
            echo "ERROR: Too few scored CIFs for DPO[$branch] $target ($N_SCORED < $MIN_SCORED_CIFS). Aborting."
            exit 1
        fi
        if ! check_score_fail_rate "$SCORED_DIR" "DPO[$branch]/$target"; then
            echo "ERROR: Score fail-rate gate failed for DPO[$branch]/$target. Skipping target."
            continue
        fi

        if ! merge_eval_csv "$SCORED_DIR"; then
            echo "WARNING: eval.csv merge failed for $target (DPO[$branch]). Continuing."
        fi

        conda run -n myenv python "$SCRIPT_DIR/36_estimate_ehull.py" \
            --scores_csv "$SCORED_DIR/ehull_scores.csv" \
            --out_csv "$SCORED_DIR/ehull_estimates.csv" \
            || echo "WARNING: Ehull failed for $target (DPO[$branch])"

        conda run -n myenv python "$SCRIPT_DIR/48_compute_composite_reward.py" \
            --scores_csv "$SCORED_DIR/ehull_scores.csv" \
            --cif_dir "$CIF_DIR" \
            --target "$target" \
            --out_csv "$SCORED_DIR/composite_reward.csv" \
            --w_proxy "$REWARD_W_PROXY" \
            --w_geom "$REWARD_W_GEOM" \
            --w_comp "$REWARD_W_COMP" \
            --w_novel "$REWARD_W_NOVEL" \
            --min_interatomic_distance "$REWARD_MIN_INTERATOMIC_DISTANCE" \
            --proxy_buffer_size "$REWARD_PROXY_BUFFER_SIZE" \
            --novelty_window "$REWARD_NOVELTY_WINDOW" \
            --rolling_buffer_dir "$EXP_DIR/reward_buffers" \
            $( [ "$REWARD_ENABLE_DENSITY_GATE" = "1" ] && echo "--enable_density_gate" ) \
            --density_min "$REWARD_DENSITY_MIN" \
            --density_max "$REWARD_DENSITY_MAX" \
            || echo "WARNING: Composite reward failed for $target (DPO[$branch])"

        check_reward_spread "$SCORED_DIR" "DPO[$branch]/$target" || true

        echo "---- $target [$branch] evaluation done ----"
    done

    # Three-way evaluation per branch: Baseline vs SFT vs SFT+DPO
    echo "Running three-way evaluation for branch=$branch ..."
    BASE_SCORED_LIST=""
    SFT_SCORED_LIST=""
    DPO_SCORED_LIST=""
    TARGET_LIST_STR=""
    for target in "${EVAL_TARGETS[@]}"; do
        target=$(echo "$target" | xargs)
        BASE_SCORED_LIST="${BASE_SCORED_LIST:+$BASE_SCORED_LIST,}$EXP_DIR/$target/baseline/scored"
        SFT_SCORED_LIST="${SFT_SCORED_LIST:+$SFT_SCORED_LIST,}$EXP_DIR/$target/sft_$branch/scored"
        DPO_SCORED_LIST="${DPO_SCORED_LIST:+$DPO_SCORED_LIST,}$EXP_DIR/$target/dpo_$branch/scored"
        TARGET_LIST_STR="${TARGET_LIST_STR:+$TARGET_LIST_STR,}$target"
    done

    if conda run -n myenv python "$SCRIPT_DIR/50_evaluate_three_way.py" \
        --baseline_dir "$BASE_SCORED_LIST" \
        --sft_dir "$SFT_SCORED_LIST" \
        --dpo_dir "$DPO_SCORED_LIST" \
        --target "$TARGET_LIST_STR" \
        --out_dir "$REPORT_DIR/three_way_$branch"; then
        BRANCH_EVAL_OK=1
    else
        echo "WARNING: Three-way evaluation failed for branch=$branch"
    fi
    if [ "$BRANCH_EVAL_OK" -eq 1 ]; then
        PHASE5_SUCCESS_BRANCHES=$((PHASE5_SUCCESS_BRANCHES + 1))
    fi
done

# Cross-branch summary
echo "Generating cross-branch summary ..."
SUMMARY_FILE="$REPORT_DIR/sft_rl_summary.md"
cat > "$SUMMARY_FILE" <<HEADER
# SFT + RL (DPO) Pipeline — $EXP_NAME Ablation Results

## Experiment Configuration

HEADER

cat >> "$SUMMARY_FILE" <<EOFCFG
- **Experiment**: $EXP_NAME
- **Targets**: ${TARGET_LIST[*]}
- **Samples per target**: $NUM_SAMPLES
- **SFT Branches**: ${BRANCH_LIST[*]}
- **DPO**: steps=$DPO_STEPS, lr=$DPO_LR, loss=$DPO_LOSS_TYPE, beta=$DPO_BETA
- **Reward weights (Plan B)**: proxy=$REWARD_W_PROXY, geom=$REWARD_W_GEOM, comp=$REWARD_W_COMP, novel=$REWARD_W_NOVEL
- **Reward-weighted DPO**: $DPO_REWARD_WEIGHTED (alpha=$DPO_REWARD_ALPHA)
- **Ehull reference**: $( [ -n "$MP_API_KEY" ] && echo "MP API (live refs)" || echo "Fallback-only (MP_API_KEY not set)" )

## Per-Branch Per-Target Results

| Target | Branch | Baseline Stability | SFT Stability | DPO Stability |
|--------|--------|-------------------|---------------|---------------|
EOFCFG

for branch in "${BRANCH_LIST[@]}"; do
    branch=$(echo "$branch" | xargs)
    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        BASE_RATE=$(python3 -c "
import json
try:
    with open('$EXP_DIR/$target/baseline/scored/ehull_summary.json') as f:
        d = json.load(f); print(f'{d[\"stability_rate\"]:.4f}')
except: print('N/A')
" 2>/dev/null)
        SFT_RATE=$(python3 -c "
import json
try:
    with open('$EXP_DIR/$target/sft_$branch/scored/ehull_summary.json') as f:
        d = json.load(f); print(f'{d[\"stability_rate\"]:.4f}')
except: print('N/A')
" 2>/dev/null)
        DPO_RATE=$(python3 -c "
import json
try:
    with open('$EXP_DIR/$target/dpo_$branch/scored/ehull_summary.json') as f:
        d = json.load(f); print(f'{d[\"stability_rate\"]:.4f}')
except: print('N/A')
" 2>/dev/null)
        echo "| $target | $branch | $BASE_RATE | $SFT_RATE | $DPO_RATE |" >> "$SUMMARY_FILE"
    done
done

echo "" >> "$SUMMARY_FILE"
echo "Generated at: $(date)" >> "$SUMMARY_FILE"
echo "Summary report: $SUMMARY_FILE"

if [ "$PHASE5_SUCCESS_BRANCHES" -gt 0 ]; then
    mark_step_done 5
else
    echo "ERROR: Phase 5 failed — no branch completed three-way evaluation."
    exit 1
fi
fi

# =====================================================================
# PHASE 6: Crystal Structure Visualisation (VESTA / ASE)
# =====================================================================
if should_run 6; then
record_timing "6" "start"
echo ""
echo "=========================================="
echo "Phase 6: Structure Visualisation"
echo "=========================================="

BRANCH_STR=$(IFS=','; echo "${BRANCH_LIST[*]}")
TARGET_STR=$(IFS=','; echo "${TARGET_LIST[*]}")

VIZ_BACKEND="ase"
VESTA_BIN="${HOME}/tools/VESTA/VESTA"
if [ -x "$VESTA_BIN" ]; then
    VIZ_BACKEND="vesta"
fi

conda run -n myenv python "$SCRIPT_DIR/51_visualize_structures.py" \
    --exp_dir "$EXP_DIR" \
    --targets "$TARGET_STR" \
    --branches "$BRANCH_STR" \
    --top_n 10 \
    --out_dir "$REPORT_DIR/visualizations" \
    --export_cifs \
    || echo "WARNING: CIF export failed (non-fatal)"

warn_if_no_visualizations "$REPORT_DIR/visualizations"

mark_step_done 6
fi

echo ""
echo "=========================================="
echo "SFT + RL Pipeline Complete!"
echo "Report directory: $REPORT_DIR"
echo "Finished at: $(date)"
echo "=========================================="

# Generate final summary report
echo ""
echo "=== Generating Final Summary Report ==="
python3 - "$EXP_DIR" "$TIMING_LOG" "$ERROR_LOG" << 'PYEOF'
import json
import sys
from pathlib import Path
from datetime import datetime

exp_dir = Path(sys.argv[1])
timing_log = Path(sys.argv[2])
error_log = Path(sys.argv[3])

summary = {
    "experiment": exp_dir.name,
    "completed_at": datetime.now().isoformat(),
    "phases": {},
    "timing": {},
    "errors": [],
    "artifacts": {}
}

# Parse timing log
if timing_log.exists():
    phase_times = {}
    with open(timing_log) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                phase = entry['phase']
                status = entry['status']
                ts = entry['timestamp']
                if phase not in phase_times:
                    phase_times[phase] = {}
                phase_times[phase][status] = ts
    
    for phase, times in phase_times.items():
        if 'start' in times and 'end' in times:
            duration = times['end'] - times['start']
            summary['timing'][f"phase_{phase}"] = {
                "duration_seconds": duration,
                "duration_minutes": round(duration / 60, 1)
            }

# Parse error entries
error_entries = exp_dir / "logs" / "error_entries.jsonl"
if error_entries.exists():
    with open(error_entries) as f:
        summary['errors'] = [json.loads(line) for line in f if line.strip()]

# Check artifacts
for branch in ["lora64", "full_ft"]:
    ckpt_path = exp_dir / f"sft_{branch}" / "checkpoint" / "ckpt.pt"
    best_ckpt_path = exp_dir / f"sft_{branch}" / "checkpoint" / "best_ckpt.pt"
    summary['artifacts'][f'sft_{branch}'] = {
        'checkpoint_exists': ckpt_path.exists() or best_ckpt_path.exists(),
        'size_mb': round((best_ckpt_path if best_ckpt_path.exists() else ckpt_path).stat().st_size / 1024 / 1024, 1) if (ckpt_path.exists() or best_ckpt_path.exists()) else 0
    }

# Save summary
summary_file = exp_dir / "logs" / "pipeline_summary.json"
with open(summary_file, 'w') as f:
    json.dump(summary, f, indent=2)

print(f"[summary] Pipeline summary saved to {summary_file}")
print(f"[summary] Total phases completed: {len(summary['timing'])}")
print(f"[summary] Total errors logged: {len(summary['errors'])}")
if summary['timing']:
    total_time = sum(t['duration_seconds'] for t in summary['timing'].values())
    print(f"[summary] Total execution time: {total_time/60:.1f} minutes")
PYEOF

# =============================================================================
# USAGE GUIDE: How to Run the Pipeline
# =============================================================================
#
# 1. FRESH RUN (default)
#    Clears any previous checkpoint and runs all phases from start.
#    
#    source experiments/exp_sft_rl_v5/config.sh
#    rm -f outputs/$EXP_NAME/.checkpoint
#    bash scripts/run_sft_rl_pipeline.sh
#
# -----------------------------------------------------------------------------
#
# 2. RESUME AFTER FAILURE (RESUME=1)
#    Safely resumes from the last completed phase. Validates that artifacts
#    exist AND meet quantitative requirements (counts, file sizes).
#    If validation fails, the phase is automatically rerun.
#    
#    source experiments/exp_sft_rl_v5/config.sh
#    RESUME=1 bash scripts/run_sft_rl_pipeline.sh
#
#    Resume behavior by phase:
#    - Phase 1: Checks scored CIFs >= MIN_SCORED_CIFS per target
#    - Phase 2: Checks SFT checkpoints exist (ckpt.pt OR best_ckpt.pt)
#    - Phase 3: Checks pairs.jsonl exists AND pairs >= MIN_PAIRS per target
#               AND total pairs >= DPO_TOTAL_PAIRS per branch
#    - Phase 4: Checks merged_pairs.jsonl has EXACTLY DPO_TOTAL_PAIRS rows
#               AND at least one of ckpt.pt / best_ckpt.pt exists
#    - Phase 5: Checks per-target ehull summaries + three-way summary + cross-branch summary
#
# -----------------------------------------------------------------------------
#
# 3. FORCE CLEAN RERUN (CLEAN=1)
#    Deletes phase artifacts before running. Use when you want to force
#    regeneration of data even if checkpoint says phase is done.
#    
#    source experiments/exp_sft_rl_v5/config.sh
#    CLEAN=1 bash scripts/run_sft_rl_pipeline.sh
#
#    CLEAN removes different directories depending on phase:
#    - Phase 1: outputs/$EXP_NAME/$target/baseline/ for all targets
#    - Phase 2: outputs/$EXP_NAME/sft_shared/ and sft_$branch/checkpoint/
#    - Phase 3: outputs/$EXP_NAME/$target/sft_$branch/ for all targets/branches
#    - Phase 4: outputs/$EXP_NAME/dpo_$branch/ for all branches
#    - Phase 5: reports/$EXP_NAME/three_way_$branch/ and eval directories
#
# -----------------------------------------------------------------------------
#
# 4. DEBUG RUN THEN FULL RUN (Safe Resume Demo)
#    Demonstrates safe resume detecting insufficient artifacts and rerunning:
#    
#    # Step 1: Debug run with small samples
#    source experiments/exp_sft_rl_v5/config.sh
#    NUM_SAMPLES=200 MIN_PAIRS=10 DPO_TOTAL_PAIRS=100 bash scripts/run_sft_rl_pipeline.sh
#    
#    # Step 2: Full run with RESUME=1 - Phase 1-3 will rerun due to insufficient artifacts
#    source experiments/exp_sft_rl_v5/config.sh
#    NUM_SAMPLES=2000 MIN_PAIRS=100 DPO_TOTAL_PAIRS=450 RESUME=1 bash scripts/run_sft_rl_pipeline.sh
#    
#    Expected output:
#    [validate] Phase 1: LiFePO4 has 150 scored CIFs (required 800)
#    [resume] Phase 1 marker exists (last=3) but artifacts invalid; rerunning.
#
# -----------------------------------------------------------------------------
#
# 5. FORCE RESTART FROM SPECIFIC PHASE
#    To force rerun from Phase 3 onwards:
#    
#    source experiments/exp_sft_rl_v5/config.sh
#    echo "2" > outputs/$EXP_NAME/.checkpoint  # Pretend only up to Phase 2 is done
#    RESUME=1 bash scripts/run_sft_rl_pipeline.sh
#
# -----------------------------------------------------------------------------
#
# FAIL-FAST ASSERTIONS (always active):
# - Phase 3: If pairs.jsonl has < MIN_PAIRS rows → immediate abort with error
# - Phase 4: If merged_pairs.jsonl != DPO_TOTAL_PAIRS rows → immediate abort
#
# These prevent partial/incomplete data from silently propagating downstream.
# =============================================================================
