#!/bin/bash
# CG-P1-11 (2026-04-28): restart helper for the local Celery worker.
#
# Why this exists: Celery workers import tasks ONCE at startup. When you
# add a new task, change `task_routes` in `config/celery.py`, or modify
# anything in `apps/courses/maic_tasks.py`, the running worker keeps the
# old registration table — the new task is `NotRegistered` from the
# worker's view even though Django runserver auto-reloads everything else.
#
# Symptom we hit on 2026-04-28: `fill_classroom_images` tasks queued
# successfully but failed with `celery.exceptions.NotRegistered`. The
# Celery results in Redis showed FAILURE for every recent task. Workers
# had been running since the previous day and missed the CG-P0-5 routing
# changes + later edits.
#
# Usage: ./scripts/restart-celery-worker.sh

set -euo pipefail

cd "$(dirname "$0")/../backend"

CONDA_PY="${CONDA_PY:-$HOME/.conda/envs/lms/bin}"
LOG_FILE="${LOG_FILE:-/tmp/lms-celery.log}"
QUEUES="${QUEUES:-default,video,notifications,tts}"
CONCURRENCY="${CONCURRENCY:-2}"

echo "Stopping current celery workers..."
pkill -TERM -f "celery -A config worker" || true
sleep 4

remaining=$(pgrep -f "celery -A config worker" | wc -l | tr -d ' ')
if [ "$remaining" != "0" ]; then
  echo "  $remaining workers still alive; sending SIGKILL..."
  pkill -KILL -f "celery -A config worker" || true
  sleep 2
fi

echo "Starting fresh worker (queues=$QUEUES, concurrency=$CONCURRENCY)..."
nohup "$CONDA_PY/celery" -A config worker \
  -l info \
  --concurrency="$CONCURRENCY" \
  -Q "$QUEUES" \
  --without-heartbeat \
  > "$LOG_FILE" 2>&1 &
disown

NEW_PID=$!
echo "  worker started, pid=$NEW_PID, log=$LOG_FILE"
sleep 5

echo "=== Verifying fill_classroom_images is registered ==="
if grep -qE "\\. apps\\.courses\\.maic_tasks\\.fill_classroom_images" "$LOG_FILE" 2>/dev/null; then
  echo "  ✓ fill_classroom_images registered"
else
  echo "  ✗ fill_classroom_images NOT seen in worker boot log — check $LOG_FILE"
  exit 1
fi

echo ""
echo "=== Worker ready ==="
echo "Tail:    tail -f $LOG_FILE"
echo "Stop:    pkill -TERM -f 'celery -A config worker'"
