# AGENTS.md — 어떤 에이전트든 여기서 시작

이 저장소는 **채용공고 데이터 기반 이력서 피드백 엔진**이다. 이 파일은 Claude Code, Codex 등 어떤 에이전트로 작업하든 같은 규칙을 따르게 하는 진입점이다.
- 자세한 설계: `docs/ARCHITECTURE.md`
- 운영 방법: `docs/OPERATIONS.md`

## 0. 처음 clone했을 때 (에이전트가 이 순서로 진행)
공개 저장소에는 **코드, 프롬프트, 템플릿만** 있다. 공고 데이터와 개인 데이터는 없다. 단계마다 사용자에게 확인하고 진행한다.

1. **설치** (Python 3.9+)
   ```bash
   python3 -m venv .venv && .venv/bin/pip install PyYAML
   cp .env.example .env                       # COACH_CONTACT(본인 이메일)는 크롤링에 필수
   cp -r profiles/_template profiles/me
   .venv/bin/python -m unittest discover -s tests   # LLM 없이 통과해야 한다
   ```
2. **LLM 하나 준비**: 로그인된 `claude` CLI(기본) / Ollama / OpenAI 호환 키. `.env`의 `COACH_MODEL_*`와 `coach/models.yaml`.
3. **공고 데이터 만들기** — 사용자에게 시간과 비용을 먼저 알리고 동의를 받는다.
   ```bash
   .venv/bin/python -m crawler.run all          # 수집·추출·통계 [LLM 0, 요청 속도 제한 때문에 수 시간]
   .venv/bin/python -m crawler.insight run      # 공고 해석 [Haiku, 공고당 약 $0.0035 → 300건 약 $1]
   .venv/bin/python -m crawler.persona_build    # 단계별 페르소나 수치 [LLM 0]
   .venv/bin/python -m crawler.persona_write    # 페르소나 카드 [Sonnet, 단계당 약 $0.1]
   ```
   - 끝나면 `data/stats`, `data/personas`, `personas/stage-*.md`가 생긴다(git 제외). 이게 없으면 `review`·`panel`은 안내 메시지를 내고 멈춘다.
   - 차단(403, 챌린지)은 우회하지 않는다. 막힌 사이트는 건너뛴다.
4. **본인 메모를 활용할지 묻는다** (선택): "Notion, Obsidian, Apple 메모·미리 알림 같은 자료에 이력서에 안 쓴 경험이나 할 일이 있나요? 읽기 전용으로 정리해 드릴까요?"
   - 원하면 `prompts/commands/import-notes.md`를 따른다. 결과는 `profiles/me/`의 experience, skills, todo-backlog, mentors에 들어간다.
   - 원하지 않으면 건너뛴다. 이력서만으로도 리뷰는 된다.
5. **이력서**: 지원자가 `profiles/me/resume.md`를 **직접** 쓴다. 에이전트는 대신 쓰지 않는다.
6. **실행**: `coach.cli panel --profile profiles/me`, `coach.cli review --profile profiles/me`
   - 공고 데이터가 오늘 것이 아니면 실행 전에 자동으로 다시 모은다(보통 수 분). 급하면 `--no-refresh`.

## 1. 구조 한 장 요약
```
crawler/   수집·추출·통계·공고 정밀분석·페르소나 생성 (스크립트 우선, LLM은 공고당 1회·단계당 1회)
coach/     리뷰 엔진: 근거 묶음 → 리뷰 → 결정적 검증 → 리포트 (이력서만 있으면 누구에게나 동작)
prompts/   에이전트 무관 지시문 (commands/*.md = 명령, reviewers/*.md = 평가자 관점, rubric.md = 채점 규칙)
personas/  단계별 면접관 카드 (자동 생성: stage-*.md) + 단계 무관 렌즈 (hr, headhunter, culture, domain)
mentors/   멘토 원칙 DB (principles.yaml 정본)
profiles/  지원자별 데이터 (엔진 git에서 제외, _template만 추적)
data/      sqlite DB, 통계, 페르소나 수치, 평가셋 (원문 캐시·DB는 git 제외)
eval/      모델 비교 평가, 테스트 픽스처
tests/     단위 테스트 (stdlib unittest)
```

## 2. 명령 실행법 (에이전트별)
| 하고 싶은 일 | 스크립트 (에이전트 불필요) | 에이전트에게 |
|---|---|---|
| 이력서 리뷰 | `.venv/bin/python -m coach.cli review --profile profiles/<id>` 또는 `--resume <file>` | `prompts/commands/resume-review.md` |
| 채용담당자 패널 판정 | `.venv/bin/python -m coach.cli panel --profile profiles/<id>` 또는 `--resume <file>` | docs/OUTPUT.md (패널 리포트) |
| 맞는 단계 찾기 | `.venv/bin/python -m coach.cli target --resume <file>` | `prompts/commands/target.md` |
| 공고 1건 적합도 | `coach.cli review --job <uid>` | `prompts/commands/job-fit.md` |
| 갭·주간계획·모의면접·포트폴리오·멘토추가·주간리포트·보정 | — | `prompts/commands/{gap,plan-week,mock-interview,portfolio-review,mentor-add,weekly-report,calibrate}.md` |
| 본인 메모에서 경험·할 일 정리 | — | `prompts/commands/import-notes.md` |
| 데이터 갱신 | `.venv/bin/python -m crawler.run all` → `crawler.insight run` → `crawler.persona_build` → `crawler.persona_write` | — |
| 테스트 | `.venv/bin/python -m unittest discover -s tests` | — |

- 프롬프트의 `{PROFILE}`은 환경변수 `COACH_PROFILE`의 값으로 바꾼다. 기본값은 `profiles/me`이다.
- Claude Code의 `.claude/skills/*`와 `.claude/agents/*`는 위 `prompts/` 파일을 가리키는 얇은 래퍼일 뿐이다. 지시문을 고칠 때는 **`prompts/`를 고친다.**

## 3. 반드시 지킬 규칙
1. **근거 출처 표시**
   - 모든 판단에 `[공고]`, `[통계]`, `[멘토]`, `[단계추정]`, `[의견]` 중 하나를 붙인다. 자세한 규칙은 `prompts/rubric.md`에 있다.
   - `[단계추정]`과 `[의견]`은 단정하지 않는다.
2. **날조 금지**: 이력서에 없는 경험이나 수치를 쓰지 않는다. 모르는 값은 `[측정값]`으로 둔다.
3. **사칭 금지**: 페르소나는 "이 단계 회사 면접관의 일반적 관점"이다. 실존 회사나 인물을 흉내 내지 않는다.
4. **개인 데이터**
   - `profiles/<id>/` 밖으로 개인 정보를 복사하지 않는다.
   - 외부 LLM에 보낼 때는 `coach/redact.py`를 거친다.
   - 이력서(`resume.md`)는 사용자가 직접 쓴다. 에이전트는 제안만 하고 수정하지 않는다.
5. **크롤링**
   - `crawler/`의 스크립트만 쓴다(LLM 사용 금지). robots.txt와 요청 간격을 지킨다.
   - 403이나 봇 확인 화면이 나오면 우회하지 않고 중단한다.
6. **토큰 절약**
   - 공고 원문 전체를 읽지 않는다. `data/stats`, `data/personas`의 집계와 `job_insights`를 쓴다.
   - 원문은 필요한 uid만 sqlite로 조회한다.
7. **모델 교체**
   - 모델 이름을 코드에 박지 않는다. `coach/models.yaml`의 `routes`를 쓴다.
   - 환경변수로 덮어쓸 수 있다: `COACH_MODEL_<TASK>=name`.
8. **비밀값**: `.env`와 사용자 노트 안의 토큰·비밀번호를 출력하거나 커밋하지 않는다.
