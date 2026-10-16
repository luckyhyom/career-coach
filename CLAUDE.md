# CLAUDE.md

이 저장소의 규칙과 구조는 **[AGENTS.md](AGENTS.md)**에 있습니다(모든 에이전트 공통). 먼저 그 파일을 읽으세요.

Claude Code 전용 사항만 적습니다.
- `/resume-review`, `/target`, `/job-fit`, `/gap`, `/plan-week`, `/mock-interview`, `/portfolio-review`, `/mentor-add`, `/weekly-report`, `/calibrate`, `/import-notes`는 `.claude/skills/`에 있는 래퍼입니다. 실제 지시문은 `prompts/commands/*.md`입니다.
- 서브에이전트(`.claude/agents/*`)도 래퍼이고, 실제 지시문은 `prompts/reviewers/*.md`입니다.
- `{PROFILE}`은 `COACH_PROFILE` 값으로 바꿉니다(기본 `profiles/me`).
- 지시문을 고칠 때는 래퍼가 아니라 `prompts/`를 고칩니다.
