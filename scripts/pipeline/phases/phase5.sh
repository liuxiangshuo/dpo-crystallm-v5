# =====================================================================
# PHASE 5: Final Evaluation + Comparison
# =====================================================================
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

