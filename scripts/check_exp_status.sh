#!/bin/bash
# =============================================================================
# Check exp_sft_rl_v5 experiment status and view logs
# =============================================================================

SESSION_NAME="${SESSION_NAME:-exp_sft_rl_v5}"
EXPERIMENT_NAME="exp_sft_rl_v5"
PROJECT_ROOT="$HOME/projects/dpo-crystallm"
OUTPUT_DIR="$PROJECT_ROOT/outputs/$EXPERIMENT_NAME"
REPORT_DIR="$PROJECT_ROOT/reports/$EXPERIMENT_NAME"
LOG_DIR="$PROJECT_ROOT/logs"

echo "=========================================="
echo "Experiment Status Check: $EXPERIMENT_NAME"
echo "=========================================="
echo ""

# Check tmux session status
echo "--- TMUX Session Status ---"
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "✓ Session '$SESSION_NAME' is ACTIVE"
    echo "  To attach: tmux attach -t $SESSION_NAME"
    
    # List windows
    echo ""
    echo "  Windows in session:"
    tmux list-windows -t "$SESSION_NAME" -F '    - #I: #W (#F)'
else
    echo "✗ Session '$SESSION_NAME' is NOT RUNNING"
fi
echo ""

# Check checkpoint status
echo "--- Experiment Checkpoint ---"
if [ -f "$OUTPUT_DIR/.checkpoint" ]; then
    PHASE=$(cat "$OUTPUT_DIR/.checkpoint")
    echo "✓ Current phase: $PHASE"
    
    # Show phase description
    case "$PHASE" in
        1) echo "    (Phase 1: Multi-composition baseline generation)" ;;
        2) echo "    (Phase 2: SFT training)" ;;
        3) echo "    (Phase 3: SFT model resample + scoring)" ;;
        4) echo "    (Phase 4: DPO training)" ;;
        5) echo "    (Phase 5: Final evaluation)" ;;
        6) echo "    (Phase 6: Visualization) - COMPLETED" ;;
    esac
else
    echo "✗ No checkpoint file found"
    echo "    Experiment may not have started yet"
fi
echo ""

# Check output directories
echo "--- Output Directories ---"
if [ -d "$OUTPUT_DIR" ]; then
    echo "✓ Output directory exists: $OUTPUT_DIR"
    echo "  Size: $(du -sh "$OUTPUT_DIR" 2>/dev/null | cut -f1)"
    
    # List targets
    echo ""
    echo "  Target directories:"
    for target_dir in "$OUTPUT_DIR"/*/; do
        if [ -d "$target_dir" ]; then
            target=$(basename "$target_dir")
            echo "    - $target/"
            
            # Show phases for this target
            for phase in baseline sft_lora64 sft_full_ft dpo_lora64 dpo_full_ft; do
                if [ -d "$target_dir/$phase" ]; then
                    echo "      - $phase/"
                fi
            done
        fi
    done
else
    echo "✗ Output directory not found: $OUTPUT_DIR"
fi
echo ""

# Check log files
echo "--- Log Files ---"

# Main experiment log
if [ -f "$OUTPUT_DIR/experiment.log" ]; then
    echo "✓ Experiment log: $OUTPUT_DIR/experiment.log"
    echo "  Size: $(du -h "$OUTPUT_DIR/experiment.log" 2>/dev/null | cut -f1)"
    
    # Show last few lines
    echo ""
    echo "  Recent entries (last 5 lines):"
    echo "  ---"
    tail -n 5 "$OUTPUT_DIR/experiment.log" | while read line; do
        echo "    $line"
    done
    echo "  ---"
else
    echo "✗ Experiment log not found"
fi

# Session logs in log directory
echo ""
echo "--- Session Logs ---"
LATEST_LOG=$(ls -t "$LOG_DIR"/${EXPERIMENT_NAME}_*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    echo "✓ Latest session log: $LATEST_LOG"
    echo "  Size: $(du -h "$LATEST_LOG" 2>/dev/null | cut -f1)"
else
    echo "  No session logs found in $LOG_DIR"
fi

# Debug logs
echo ""
echo "--- Debug Logs ---"
DEBUG_LOG_DIR="$PROJECT_ROOT/.cursor"
if [ -d "$DEBUG_LOG_DIR" ]; then
    DEBUG_LOGS=$(ls -t "$DEBUG_LOG_DIR"/debug-*.log 2>/dev/null | head -3)
    if [ -n "$DEBUG_LOGS" ]; then
        echo "✓ Debug logs found:"
        for log in $DEBUG_LOGS; do
            echo "    - $(basename $log) ($(du -h $log 2>/dev/null | cut -f1))"
        done
    else
        echo "  No debug logs found"
    fi
else
    echo "  Debug log directory not found"
fi
echo ""

# Check for results/reports
echo "--- Results and Reports ---"
if [ -d "$REPORT_DIR" ]; then
    echo "✓ Report directory exists: $REPORT_DIR"
    
    # List report files
    REPORTS=$(find "$REPORT_DIR" -name "*.md" -o -name "*.csv" -o -name "*.json" 2>/dev/null | head -10)
    if [ -n "$REPORTS" ]; then
        echo ""
        echo "  Generated reports:"
        for report in $REPORTS; do
            echo "    - $(basename $report)"
        done
    else
        echo "  No reports generated yet"
    fi
else
    echo "✗ Report directory not found: $REPORT_DIR"
fi
echo ""

# Check GPU status if available
echo "--- GPU Status ---"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv,noheader 2>/dev/null | while read line; do
        echo "  GPU $line"
    done
else
    echo "  nvidia-smi not available"
fi
echo ""

# Summary and recommendations
echo "=========================================="
echo "Quick Commands"
echo "=========================================="
echo ""
echo "View full experiment log:"
echo "  tail -f $OUTPUT_DIR/experiment.log"
echo ""
echo "Attach to tmux session:"
echo "  tmux attach -t $SESSION_NAME"
echo ""
echo "Check GPU usage:"
echo "  watch -n 1 nvidia-smi"
echo ""
echo "Resume experiment (if interrupted):"
echo "  cd $PROJECT_ROOT"
echo "  source experiments/$EXPERIMENT_NAME/config.sh"
echo "  RESUME=1 bash scripts/run_sft_rl_pipeline.sh"
echo ""
echo "Force clean restart:"
echo "  cd $PROJECT_ROOT"
echo "  source experiments/$EXPERIMENT_NAME/config.sh"
echo "  CLEAN=1 bash scripts/run_sft_rl_pipeline.sh"
echo ""
