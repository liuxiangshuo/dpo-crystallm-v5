# =====================================================================
# PHASE 3: SFT model resample + scoring + pair building (per branch)
# =====================================================================
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

