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

