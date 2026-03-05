# Phase 2: SFT training
is_phase2_done() {
    local branch
    for branch in "${BRANCH_LIST[@]}"; do
        branch=$(echo "$branch" | xargs)
        local sft_dir="$EXP_DIR/sft_$branch/checkpoint"
        
        # Check at least one checkpoint exists
        if [ ! -f "$sft_dir/ckpt.pt" ] && [ ! -f "$sft_dir/best_ckpt.pt" ]; then
            # Check for step checkpoints
            local step_ckpt
            step_ckpt=$(python3 -c "
from pathlib import Path
p = Path('$sft_dir')
cands = sorted(p.glob('step_*/ckpt.pt'))
print(str(cands[-1]) if cands else '')
" 2>/dev/null || true)
            if [ -z "$step_ckpt" ] || [ ! -f "$step_ckpt" ]; then
                echo "[validate] Phase 2: $branch missing SFT checkpoint"
                return 1
            fi
        fi
    done
    return 0
}

