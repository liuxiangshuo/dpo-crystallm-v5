#!/bin/bash
# =============================================================================
# Run exp_sft_rl_v5 in tmux with detailed logging
# =============================================================================

set -e

# Configuration
SESSION_NAME="${SESSION_NAME:-exp_sft_rl_v5}"
EXPERIMENT_NAME="exp_sft_rl_v5"
LOG_DIR="$HOME/projects/dpo-crystallm/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create log directory
mkdir -p "$LOG_DIR"

# Log file paths
MAIN_LOG="$LOG_DIR/${EXPERIMENT_NAME}_${TIMESTAMP}.log"
ERROR_LOG="$LOG_DIR/${EXPERIMENT_NAME}_${TIMESTAMP}.err"
DEBUG_LOG="$LOG_DIR/${EXPERIMENT_NAME}_${TIMESTAMP}.debug.log"

# Check if tmux is installed
if ! command -v tmux &> /dev/null; then
    echo "ERROR: tmux is not installed. Please install tmux first."
    exit 1
fi

# Check if session already exists
if tmux has-session -t "$SESSION_NAME" 2>/dev/null; then
    echo "WARNING: tmux session '$SESSION_NAME' already exists."
    echo "Options:"
    echo "  1. Attach to existing session: tmux attach -t $SESSION_NAME"
    echo "  2. Kill existing session: tmux kill-session -t $SESSION_NAME"
    echo "  3. Create new session with different name: SESSION_NAME=${SESSION_NAME}_2 bash $0"
    exit 1
fi

echo "=========================================="
echo "Starting exp_sft_rl_v5 in tmux session"
echo "=========================================="
echo "Session name: $SESSION_NAME"
echo "Main log: $MAIN_LOG"
echo "Error log: $ERROR_LOG"
echo "Debug log: $DEBUG_LOG"
echo ""

# Create the tmux session with initial window
tmux new-session -d -s "$SESSION_NAME" -n "main"

# Build the command to run in tmux
# This captures both stdout and stderr, and also writes to separate log files
CMD="
#!/bin/bash
echo '=========================================='
echo 'Experiment: $EXPERIMENT_NAME'
echo 'Started at: \$(date)'
echo 'PID: \$$'
echo 'Log file: $MAIN_LOG'
echo '=========================================='
echo ''

# Change to project directory
cd '$HOME/projects/dpo-crystallm'

# Source the experiment configuration
echo '[SETUP] Loading configuration...'
source 'experiments/exp_sft_rl_v5/config.sh'

# Print configuration summary for debugging
echo '[SETUP] Configuration Summary:'
echo '  - EXP_NAME: \$EXP_NAME'
echo '  - TARGETS: \$TARGETS'
echo '  - NUM_SAMPLES: \$NUM_SAMPLES'
echo '  - SFT_BRANCHES: \$SFT_BRANCHES'
echo '  - DPO_TOTAL_PAIRS: \$DPO_TOTAL_PAIRS'
echo ''

# Run the experiment with full logging
echo '[RUN] Starting pipeline...'
bash 'scripts/run_sft_rl_pipeline.sh' 2>&1 | tee -a '$MAIN_LOG'

# Capture exit code
EXIT_CODE=\${PIPESTATUS[0]}

# Final summary
echo ''
echo '=========================================='
echo 'Experiment completed'
echo 'Finished at: \$(date)'
echo 'Exit code: \$EXIT_CODE'
echo 'Log files:'
echo '  - Main log: $MAIN_LOG'
echo '  - Output dir: outputs/$EXPERIMENT_NAME/'
echo '  - Report dir: reports/$EXPERIMENT_NAME/'
echo '=========================================='

# Keep session alive if there was an error
if [ \$EXIT_CODE -ne 0 ]; then
    echo ''
    echo 'ERROR: Pipeline failed with exit code '\$EXIT_CODE
    echo 'Check the logs for details.'
    echo ''
    echo 'Press Enter to close this window...'
    read
fi

exit \$EXIT_CODE
"

# Send the command to tmux
tmux send-keys -t "$SESSION_NAME:main" "$CMD" C-m

# Create additional windows for monitoring

# Window 2: Live log monitoring
tmux new-window -t "$SESSION_NAME" -n "logs"
tmux send-keys -t "$SESSION_NAME:logs" "
cd '$HOME/projects/dpo-crystallm'
echo 'Monitoring experiment logs...'
echo 'Main log will appear here once the experiment starts.'
echo ''
echo 'Commands you can use:'
echo '  tail -f $MAIN_LOG          # Follow main log'
echo '  tail -f outputs/$EXPERIMENT_NAME/experiment.log  # Follow experiment log'
echo '  ls -la outputs/$EXPERIMENT_NAME/                 # Check outputs'
echo ''
# Wait a bit then show the log
sleep 2
if [ -f '$MAIN_LOG' ]; then
    echo 'Showing main log:'
    tail -f '$MAIN_LOG'
else
    echo 'Log file not created yet. Check the main window for status.'
fi
" C-m

# Window 3: Resource monitoring
tmux new-window -t "$SESSION_NAME" -n "monitor"
tmux send-keys -t "$SESSION_NAME:monitor" "
echo 'System Resource Monitor'
echo '======================='
echo ''
echo 'Commands:'
echo '  nvidia-smi                    # GPU status'
echo '  htop                          # CPU/memory usage'
echo '  df -h                         # Disk space'
echo '  du -sh outputs/$EXPERIMENT_NAME/  # Check output size'
echo ''
echo 'Press q to exit monitoring tools'
echo ''
# Show initial system status
nvidia-smi
" C-m

# Window 4: Quick commands reference
tmux new-window -t "$SESSION_NAME" -n "help"
tmux send-keys -t "$SESSION_NAME:help" "
cat << 'HELP'
==========================================
TMUX Session Help - exp_sft_rl_v5
==========================================

WINDOWS:
  main      - Experiment execution (don't switch away while running)
  logs      - Live log monitoring
  monitor   - System resource monitoring
  help      - This help message

NAVIGATION:
  Ctrl+b n          - Next window
  Ctrl+b p          - Previous window
  Ctrl+b 0-3        - Switch to window by number
  Ctrl+b w          - List windows
  Ctrl+b c          - Create new window
  Ctrl+b &          - Close current window

DETACH/ATTACH:
  Ctrl+b d          - Detach from session (experiment continues running)
  tmux attach -t $SESSION_NAME  - Reattach to session
  tmux ls           - List all sessions

LOG FILES:
  Main log: $MAIN_LOG
  Experiment log: outputs/$EXPERIMENT_NAME/experiment.log
  Debug logs: .cursor/debug-*.log

USEFUL COMMANDS:
  # Check experiment status
  ls -la outputs/$EXPERIMENT_NAME/.checkpoint
  
  # View logs
  tail -f $MAIN_LOG
  tail -f outputs/$EXPERIMENT_NAME/experiment.log
  
  # Check GPU usage
  watch -n 1 nvidia-smi
  
  # Resume experiment (if needed)
  cd $HOME/projects/dpo-crystallm
  source experiments/exp_sft_rl_v5/config.sh
  RESUME=1 bash scripts/run_sft_rl_pipeline.sh

CLEANUP:
  tmux kill-session -t $SESSION_NAME  # Kill entire session

==========================================
HELP
" C-m

# Go back to main window
tmux select-window -t "$SESSION_NAME:main"

echo "Tmux session created successfully!"
echo ""
echo "To attach to the session:"
echo "  tmux attach -t $SESSION_NAME"
echo ""
echo "To detach (experiment continues running):"
echo "  Press Ctrl+b, then d"
echo ""
echo "Log files:"
echo "  Main log: $MAIN_LOG"
echo "  Error log: $ERROR_LOG"
echo "  Debug log: $DEBUG_LOG"
echo ""

# Attach to the session
read -p "Press Enter to attach to the tmux session (or Ctrl+C to stay detached)..."
tmux attach -t "$SESSION_NAME"
