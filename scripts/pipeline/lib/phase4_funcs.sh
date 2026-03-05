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

