# =====================================================================
# PIPELINE COMPLETION & FINAL REPORT
# =====================================================================

echo ""
echo "=========================================="
echo "SFT + RL Pipeline Complete!"
echo "Report directory: $REPORT_DIR"
echo "Finished at: $(date)"
echo "=========================================="

# Generate final summary report
echo ""
echo "=== Generating Final Summary Report ==="
python3 - "$EXP_DIR" "$TIMING_LOG" "$ERROR_LOG" << 'PYEOF'
import json
import sys
from pathlib import Path
from datetime import datetime

exp_dir = Path(sys.argv[1])
timing_log = Path(sys.argv[2])
error_log = Path(sys.argv[3])

summary = {
    "experiment": exp_dir.name,
    "completed_at": datetime.now().isoformat(),
    "phases": {},
    "timing": {},
    "errors": [],
    "artifacts": {}
}

# Parse timing log
if timing_log.exists():
    phase_times = {}
    with open(timing_log) as f:
        for line in f:
            if line.strip():
                entry = json.loads(line)
                phase = entry['phase']
                status = entry['status']
                ts = entry['timestamp']
                if phase not in phase_times:
                    phase_times[phase] = {}
                phase_times[phase][status] = ts
    
    for phase, times in phase_times.items():
        if 'start' in times and 'end' in times:
            duration = times['end'] - times['start']
            summary['timing'][f"phase_{phase}"] = {
                "duration_seconds": duration,
                "duration_minutes": round(duration / 60, 1)
            }

# Parse error entries
error_entries = exp_dir / "logs" / "error_entries.jsonl"
if error_entries.exists():
    with open(error_entries) as f:
        summary['errors'] = [json.loads(line) for line in f if line.strip()]

# Check artifacts
for branch in ["lora64", "full_ft"]:
    ckpt_path = exp_dir / f"sft_{branch}" / "checkpoint" / "ckpt.pt"
    best_ckpt_path = exp_dir / f"sft_{branch}" / "checkpoint" / "best_ckpt.pt"
    summary['artifacts'][f'sft_{branch}'] = {
        'checkpoint_exists': ckpt_path.exists() or best_ckpt_path.exists(),
        'size_mb': round((best_ckpt_path if best_ckpt_path.exists() else ckpt_path).stat().st_size / 1024 / 1024, 1) if (ckpt_path.exists() or best_ckpt_path.exists()) else 0
    }

# Save summary
summary_file = exp_dir / "logs" / "pipeline_summary.json"
with open(summary_file, 'w') as f:
    json.dump(summary, f, indent=2)

print(f"[summary] Pipeline summary saved to {summary_file}")
print(f"[summary] Total phases completed: {len(summary['timing'])}")
print(f"[summary] Total errors logged: {len(summary['errors'])}")
if summary['timing']:
    total_time = sum(t['duration_seconds'] for t in summary['timing'].values())
    print(f"[summary] Total execution time: {total_time/60:.1f} minutes")
PYEOF
