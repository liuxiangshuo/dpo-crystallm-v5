# ============================================================================
# Phase Validation Functions (Safe Resume)
# ============================================================================

# Phase 1: Baseline generation + scoring
is_phase1_done() {
    local target
    for target in "${TARGET_LIST[@]}"; do
        target=$(echo "$target" | xargs)
        local scored_dir="$EXP_DIR/$target/baseline/scored"
        
        # Check required files exist
        if [ ! -f "$scored_dir/ehull_estimates.csv" ]; then
            echo "[validate] Phase 1: $target missing ehull_estimates.csv"
            return 1
        fi
        if [ ! -f "$scored_dir/composite_reward.csv" ]; then
            echo "[validate] Phase 1: $target missing composite_reward.csv"
            return 1
        fi
        
        # Quantitative check: scored CIF count
        local scored_count
        scored_count=$(count_scored_rows "$scored_dir/ehull_scores.csv")
        if [ "$scored_count" -lt "$MIN_SCORED_CIFS" ]; then
            echo "[validate] Phase 1: $target has $scored_count scored CIFs (required $MIN_SCORED_CIFS)"
            return 1
        fi
    done
    return 0
}

