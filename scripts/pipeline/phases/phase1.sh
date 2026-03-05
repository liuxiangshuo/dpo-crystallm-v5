# =====================================================================
# PHASE 1: Multi-composition baseline generation + scoring
# =====================================================================
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

