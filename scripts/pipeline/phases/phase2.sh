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

