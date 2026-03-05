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

