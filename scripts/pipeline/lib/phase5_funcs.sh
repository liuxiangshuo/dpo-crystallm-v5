# Phase 5: Final evaluation
is_phase5_done() {
    local branch target
    local success_branches=0
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local branch_three_way="$REPORT_DIR/three_way_$branch/three_way_summary.csv"
        if [ ! -f "$branch_three_way" ]; then
            echo "[validate] Phase 5: $branch missing three_way_summary.csv"
            continue
        fi
        success_branches=$((success_branches + 1))
        for target in "${TARGET_LIST[@]}"; do
            target=$(echo "$target" | xargs)
            local scored_dir="$EXP_DIR/$target/dpo_$branch/scored"
            
            # Check eval metrics exist
            if [ ! -f "$scored_dir/ehull_summary.json" ]; then
                echo "[validate] Phase 5: $target [$branch] missing ehull_summary.json"
                return 1
            fi
        done
    done
    if [ "$success_branches" -lt 1 ]; then
        echo "[validate] Phase 5: no branch has complete three-way outputs"
        return 1
    fi
    if [ ! -f "$REPORT_DIR/sft_rl_summary.md" ]; then
        echo "[validate] Phase 5: missing cross-branch summary sft_rl_summary.md"
        return 1
    fi
    return 0
}

# Main should_run function with safe resume
should_run() {
    local step="$1"; local last; last=$(last_done)
    
    # Handle CLEAN mode - force delete artifacts before running
    if [ "$CLEAN" = "1" ]; then
        cleanup_phase "$step"
        return 0
    fi
    
    if [ "$RESUME" = "1" ] && [ "$last" -ge "$step" ] 2>/dev/null; then
        # Validate phase-specific artifacts before skipping
        case "$step" in
            1)
                if ! is_phase1_done; then
                    echo "[resume] Phase 1 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            2)
                if ! is_phase2_done; then
                    echo "[resume] Phase 2 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            3)
                if ! is_phase3_done; then
                    echo "[resume] Phase 3 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            4)
                if ! is_phase4_done; then
                    echo "[resume] Phase 4 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
            5)
                if ! is_phase5_done; then
                    echo "[resume] Phase 5 marker exists (last=$last) but artifacts invalid; rerunning."
                    return 0
                fi
                ;;
        esac
        
        echo "[resume] Skipping phase $step (already done, last=$last)"
        return 1
    fi
    return 0
}
