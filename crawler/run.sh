#!/bin/bash
# 주간 실행: crawl → extract → stats (LLM 없음) → claude -p 로 리포트 1회 생성
set -u
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
LOG=data/weekly.log
echo "=== $(date '+%F %T') start" >> "$LOG"
.venv/bin/python -m crawler.run all >> "$LOG" 2>&1
git add data/stats >/dev/null 2>&1 && git commit -qm "stats $(date +%F)" >/dev/null 2>&1
if command -v claude >/dev/null 2>&1; then
  claude -p "/weekly-report" --allowedTools "Read,Write,Edit,Glob,Grep,Bash(sqlite3:*),Bash(git add:*),Bash(git commit:*)" >> "$LOG" 2>&1 \
    || echo "claude -p failed" >> "$LOG"
else
  echo "claude CLI not found; stats only" >> "$LOG"
fi
echo "=== $(date '+%F %T') done" >> "$LOG"
