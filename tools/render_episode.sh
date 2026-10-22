#!/usr/bin/env bash
# Вход в постоянную очередь; собственный цикл Blender больше не запускается.
# bash tools/render_episode.sh episodes/<ep>/shots_9x16.py v1 v2 --approved 'ок из чата, дата'
set -eu
script="${1:?usage: render_episode.sh <shots.py> <shot>... --approved <запись одобрения>}"
shift
episode="$(dirname "$script")/episode.json"
shots=""
approved=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --approved) approved="${2:?нужна запись одобрения}"; shift 2 ;;
    *) shots="${shots:+$shots,}$1"; shift ;;
  esac
done
args=(submit frames "$episode" --approved "$approved")
if [ -n "$shots" ]; then args+=(--shots "$shots"); fi
"${PYTHON:-python}" "$(dirname "$0")/render_queue.py" "${args[@]}"
