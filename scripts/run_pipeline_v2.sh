#!/bin/bash
# =============================================================================
# SFT + RL (DPO) Two-Stage Pipeline Driver (Modular Version)
#
# Usage:
#   source experiments/exp_sft_rl/config.sh
#   bash scripts/run_pipeline_v2.sh              # Fresh run
#   RESUME=1 bash scripts/run_pipeline_v2.sh     # Resume from checkpoint
#   CLEAN=1 bash scripts/run_pipeline_v2.sh      # Force clean rerun
# =============================================================================
set -e

# Determine script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PIPELINE_DIR="$SCRIPT_DIR/pipeline"

cd "$PROJECT_ROOT"

# ============================================================================
# Load Configuration and Common Libraries
# ============================================================================

# Source header (configuration, conda init, directory setup)
source "$PIPELINE_DIR/header.sh"

# Source library functions
source "$PIPELINE_DIR/lib/logging.sh"
source "$PIPELINE_DIR/lib/validation.sh"
source "$PIPELINE_DIR/lib/helpers.sh"
source "$PIPELINE_DIR/lib/phase1_funcs.sh"
source "$PIPELINE_DIR/lib/phase2_funcs.sh"
source "$PIPELINE_DIR/lib/phase3_funcs.sh"
source "$PIPELINE_DIR/lib/phase4_funcs.sh"
source "$PIPELINE_DIR/lib/phase5_funcs.sh"

# ============================================================================
# Resume/Clean Logic
# ============================================================================

CHECKPOINT_FILE="$EXP_DIR/.checkpoint"

if [ "${CLEAN:-0}" -eq 1 ]; then
    echo "[init] CLEAN=1: removing $EXP_DIR and resetting checkpoint"
    rm -rf "$EXP_DIR"
    mkdir -p "$EXP_DIR" "$REPORT_DIR" "$LOG_DIR"
    rm -f "$CHECKPOINT_FILE"
fi

if [ "${RESUME:-0}" -eq 1 ] && [ -f "$CHECKPOINT_FILE" ]; then
    RESUME_PHASE=$(cat "$CHECKPOINT_FILE")
    echo "[init] Resuming from Phase $RESUME_PHASE (checkpoint file found)"
else
    RESUME_PHASE=1
    echo "[init] Starting fresh (no resume)"
fi

# ============================================================================
# Phase Execution
# ============================================================================

# Helper to check if phase should run
should_run() {
    local phase="$1"
    if [ "$RESUME_PHASE" -le "$phase" ]; then
        return 0
    else
        echo "[skip] Phase $phase (already completed in resumed run)"
        return 1
    fi
}

# Checkpoint helper
mark_step_done() {
    local phase="$1"
    echo "$phase" > "$CHECKPOINT_FILE"
    echo "[checkpoint] Phase $phase done at $(date)"
    record_timing "$phase" "end"
}

# Execute phases
if should_run 1; then
    source "$PIPELINE_DIR/phases/phase1.sh"
fi

if should_run 2; then
    source "$PIPELINE_DIR/phases/phase2.sh"
fi

if should_run 3; then
    source "$PIPELINE_DIR/phases/phase3.sh"
fi

if should_run 4; then
    source "$PIPELINE_DIR/phases/phase4.sh"
fi

if should_run 5; then
    source "$PIPELINE_DIR/phases/phase5.sh"
fi

if should_run 6; then
    source "$PIPELINE_DIR/phases/phase6.sh"
fi

# ============================================================================
# Final Report Generation
# ============================================================================

source "$PIPELINE_DIR/footer.sh"
