#!/usr/bin/env bash
# Финальный рендер шотов эпизода (PNG-секвенции с докачкой: повторный запуск продолжит с места остановки;
# 0-байтные плейсхолдеры прерванного кадра удаляются в spacekit.render.render_sequence).
#   bash tools/render_episode.sh episodes/<ep>/shots_9x16.py v1 v2 ...
# Пока идёт рендер, существует out/RENDER.lock (pid, время, эпизод, шоты) — другим сессиям: только текстовая работа.
# Код выхода: 0 — все шоты без ошибок, 1 — были ошибки (подробности в out/logs/<ep>/render_<шот>.log).
set -u
SCRIPT="$(realpath "${1:?usage: render_episode.sh <shots.py> <shot>...}")"; shift
cd "$(dirname "$0")/.."
B="${BLENDER:-/d/Blender/blender.exe}"
EP_DIR="$(dirname "$SCRIPT")"
LOG_DIR="out/logs/$(basename "$EP_DIR")"
mkdir -p "$LOG_DIR"
if [ -f out/RENDER.lock ]; then
  echo "ОШИБКА: уже идёт рендер (out/RENDER.lock): $(cat out/RENDER.lock)"; exit 2
fi
echo "$$ $(date +%F_%T) $SCRIPT $*" > out/RENDER.lock
trap 'rm -f out/RENDER.lock' EXIT
export PYTHONUNBUFFERED=1
rc_all=0
for s in "$@"; do
  log="$LOG_DIR/render_$s.log"
  echo "=== $(date +%F_%T) start $s" >> "$log"
  echo "[$(date +%H:%M:%S)] render $s"
  "$B" -b --factory-startup --python-exit-code 1 -P "$(cygpath -w "$SCRIPT")" -- "$s" final >> "$log" 2>&1
  rc=$?
  if [ $rc -ne 0 ] || tail -n 200 "$log" | grep -qE "Traceback|Error:|CUDA error|OPTIX_ERROR|out of memory"; then
    echo "[$(date +%H:%M:%S)] ERROR in $s (rc=$rc) — см. $log"; rc_all=1; continue
  fi
  echo "[$(date +%H:%M:%S)] done $s"
done
echo "[$(date +%H:%M:%S)] all done (rc=$rc_all)"
exit $rc_all
