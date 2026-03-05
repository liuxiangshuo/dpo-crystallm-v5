# =====================================================================
# PHASE 4: DPO training — one per ablation branch
# =====================================================================
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

