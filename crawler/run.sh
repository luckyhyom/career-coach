#!/bin/bash
# 주간 실행: crawl → extract → stats (LLM 없음) → claude -p 로 리포트 1회 생성
set -u
cd "$(dirname "$0")/.."
[ -f .env ] && set -a && . ./.env && set +a
export COACH_PROFILE="${COACH_PROFILE:-profiles/me}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$PATH"
LOG=data/weekly.log
echo "=== $(date '+%F %T') start" >> "$LOG"
.venv/bin/python -m crawler.run all >> "$LOG" 2>&1
# 새 공고만 정밀 해석(haiku, 공고당 1회) → 페르소나 수치 재계산 → 페르소나 카드 재작성(sonnet, 단계당 1회)
.venv/bin/python -m crawler.insight run --workers 4 >> "$LOG" 2>&1
.venv/bin/python -m crawler.persona_build >> "$LOG" 2>&1
.venv/bin/python -m crawler.persona_write >> "$LOG" 2>&1
if command -v claude >/dev/null 2>&1; then
  claude -p "prompts/commands/weekly-report.md를 읽고 수행하라. {PROFILE}=$COACH_PROFILE" --allowedTools "Read,Write,Edit,Glob,Grep,Bash(sqlite3:*),Bash(git add:*),Bash(git commit:*),Bash(git -C:*)" >> "$LOG" 2>&1 \
    || echo "claude -p failed" >> "$LOG"
else
  echo "claude CLI not found; stats only" >> "$LOG"
fi
echo "=== $(date '+%F %T') done" >> "$LOG"
