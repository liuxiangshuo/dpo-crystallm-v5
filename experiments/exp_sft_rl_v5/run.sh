#!/bin/bash
# Launch exp_sft_rl_v5 pipeline
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DEBUG_LOG_DIR="$PROJECT_ROOT/.cursor"
mkdir -p "$DEBUG_LOG_DIR" 2>/dev/null || true
export DEBUG_LOG_DIR

# #region agent log
agent_log_ad14af() {
    local run_id="$1"
    local hypothesis_id="$2"
    local location="$3"
    local message="$4"
    local data_json="$5"
    python3 - "$run_id" "$hypothesis_id" "$location" "$message" "$data_json" <<'PY' || true
import json
import os
import sys
import time

run_id, hypothesis_id, location, message, data_json = sys.argv[1:]
try:
    data = json.loads(data_json) if data_json else {}
except Exception:
    data = {"raw": data_json}
entry = {
    "sessionId": "ad14af",
    "runId": run_id,
    "hypothesisId": hypothesis_id,
    "location": location,
    "message": message,
    "data": data,
    "timestamp": int(time.time() * 1000),
}
log_dir = os.environ.get("DEBUG_LOG_DIR", ".cursor")
with open(os.path.join(log_dir, "debug-ad14af.log"), "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
}
# #endregion

# #region agent log
python3 - <<'PY' || true
import json
import os
import time

entry = {
    "sessionId": "25e703",
    "runId": "pre-fix-1",
    "hypothesisId": "H5",
    "location": "experiments/exp_sft_rl_v5/run.sh:startup",
    "message": "exp_sft_rl_v5 run.sh invoked",
    "data": {},
    "timestamp": int(time.time() * 1000),
}
log_dir = os.environ.get("DEBUG_LOG_DIR", ".cursor")
with open(os.path.join(log_dir, "debug-25e703.log"), "a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
PY
# #endregion

agent_log_ad14af "precheck-1" "H1" "experiments/exp_sft_rl_v5/run.sh:pre_source" "v5 wrapper startup paths resolved" "{\"script_dir\":\"$SCRIPT_DIR\",\"project_root\":\"$PROJECT_ROOT\"}"
source "$SCRIPT_DIR/config.sh"
agent_log_ad14af "precheck-1" "H2" "experiments/exp_sft_rl_v5/run.sh:post_source" "v5 config loaded in wrapper" "{\"exp_name\":\"$EXP_NAME\",\"targets\":\"$TARGETS\",\"sft_branches\":\"$SFT_BRANCHES\"}"
agent_log_ad14af "precheck-1" "H1" "experiments/exp_sft_rl_v5/run.sh:pre_exec" "handoff to main pipeline script" "{\"pipeline_script\":\"$PROJECT_ROOT/scripts/run_sft_rl_pipeline.sh\"}"
bash "$PROJECT_ROOT/scripts/run_sft_rl_pipeline.sh" "$@" || {
    exit_code=$?
    agent_log_ad14af "precheck-1" "H_ERROR" "experiments/exp_sft_rl_v5/run.sh:pipeline_failed" "Pipeline execution failed" "{\"exit_code\":$exit_code}"
    echo "[ERROR] Pipeline failed with exit code $exit_code"
    exit $exit_code
}
