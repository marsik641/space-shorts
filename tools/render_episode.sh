#!/usr/bin/env bash
# Финальный рендер шотов эпизода (PNG-секвенции с докачкой: повторный запуск продолжит с места остановки).
#   bash tools/render_episode.sh episodes/ep001_psr_b1257/shots_9x16.py v1 v2 v3 v4 v5 v6
set -u
cd "$(dirname "$0")/.."
B="${BLENDER:-/d/Blender/blender.exe}"
SCRIPT="$1"; shift
EP_DIR="$(dirname "$SCRIPT")"
LOG_DIR="out/logs/$(basename "$EP_DIR")"
mkdir -p "$LOG_DIR"
for s in "$@"; do
  echo "[$(date +%H:%M:%S)] render $s"
  "$B" -b --factory-startup -P "$(cygpath -w "$SCRIPT")" -- "$s" final > "$LOG_DIR/render_$s.log" 2>&1
  if grep -qE "Traceback|Error:" "$LOG_DIR/render_$s.log"; then
    echo "[$(date +%H:%M:%S)] ERROR in $s — см. $LOG_DIR/render_$s.log"
  fi
  echo "[$(date +%H:%M:%S)] done $s"
done
echo "[$(date +%H:%M:%S)] all done"
