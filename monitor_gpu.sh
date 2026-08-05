#!/bin/bash
# Logs GPU utilization/power/memory to gpu_stats.log every 5s in the
# background, and shows a live nvidia-smi dmon view in the foreground.
# Ctrl+C stops both.

LOG_FILE="gpu_stats.log"
INTERVAL=5

cleanup() {
    echo "Stopping GPU logger (pid $LOGGER_PID)..."
    kill "$LOGGER_PID" 2>/dev/null
    exit 0
}
trap cleanup INT TERM

while true; do
    echo "$(date +%s),$(nvidia-smi --query-gpu=utilization.gpu,power.draw,memory.used,memory.total --format=csv,noheader,nounits)" >> "$LOG_FILE"
    sleep "$INTERVAL"
done &
LOGGER_PID=$!

echo "Logging GPU stats to $LOG_FILE every ${INTERVAL}s (pid $LOGGER_PID)"
echo "Live view below — Ctrl+C stops both the live view and the logger."
nvidia-smi dmon -s pu -d 1

cleanup
