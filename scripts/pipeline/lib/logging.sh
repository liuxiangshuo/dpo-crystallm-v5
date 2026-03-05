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

