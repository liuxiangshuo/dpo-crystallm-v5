# Phase 3: SFT resample + pair building
is_phase3_done() {
    local total_pairs=0
    local branch target
    
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local branch_pairs=0
        
        for target in "${TARGET_LIST[@]}"; do
            target=$(echo "$target" | xargs)
            local pairs_file="$EXP_DIR/$target/sft_$branch/pairs/pairs.jsonl"
            
            if [ ! -f "$pairs_file" ]; then
                echo "[validate] Phase 3: $target [$branch] missing pairs.jsonl"
                return 1
            fi
            
            local count=$(wc -l < "$pairs_file")
            if [ "$count" -lt "$MIN_PAIRS" ]; then
                echo "[validate] Phase 3: $target [$branch] has $count pairs (required $MIN_PAIRS)"
                return 1
            fi
            
            branch_pairs=$((branch_pairs + count))
            total_pairs=$((total_pairs + count))
        done
        
        # Check total pairs per branch >= DPO_TOTAL_PAIRS
        if [ "$branch_pairs" -lt "$DPO_TOTAL_PAIRS" ]; then
            echo "[validate] Phase 3: branch $branch total pairs $branch_pairs < $DPO_TOTAL_PAIRS"
            return 1
        fi
    done
    
    echo "[validate] Phase 3: total available pairs=$total_pairs"
    return 0
}

