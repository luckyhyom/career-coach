# 운영 가이드

## 설치
```bash
python3 -m venv .venv && .venv/bin/pip install PyYAML
cp .env.example .env        # 선택: SARAMIN_ACCESS_KEY, DASHSCOPE_API_KEY, REDACT_NAMES
```

## 이력서 리뷰 (누구나)
```bash
.venv/bin/python -m coach.cli review --resume someone.md --name "지원자A"        # 단계 자동 선택 → out/
.venv/bin/python -m coach.cli review --profile profiles/<id>                        # 결과는 <id>/reviews/
.venv/bin/python -m coach.cli review --profile profiles/<id> --band growth --role product_backend
.venv/bin/python -m coach.cli review --profile profiles/<id> --job <공고 uid>        # 공고 매칭 섹션 포함
.venv/bin/python -m coach.cli target --resume someone.md                            # 단계 적합도만
.venv/bin/python -m coach.cli panel --profile profiles/<id>                         # 단계 페르소나 패널 판정 (docs/OUTPUT.md)
```
새 지원자는 `cp -R profiles/_template profiles/<id>`로 만들고 `resume.md`만 채우면 됩니다.

## 모델 바꾸기
- `coach/models.yaml`
  - `routes`: 용도별 모델 지정. 용도는 insight_extract, persona_write, candidate_parse, review, judge.
  - `models`: 프로바이더 정의. claude_cli, ollama, openai_compat 중 하나.
- 한 번만 바꿔서 실행: `COACH_MODEL_REVIEW=claude-sonnet .venv/bin/python -m coach.cli review ...`
- **로컬 모델 (Ollama)**: 아래를 실행한 뒤 `models.yaml`의 local-* 태그를 실제 태그로 맞춥니다. M1 8GB 기준으로 4B급 모델과 8K 컨텍스트부터 시험합니다.
  ```bash
  brew install ollama
  ollama pull <태그>
  ```
- **OpenAI 호환 API**: `.env`에 키를 넣고 `base_url`, `model`, `price_per_mtok`를 공식 문서 기준으로 채웁니다.
- **모델 비교**: `.venv/bin/python -m eval.review_eval --models claude-haiku,claude-sonnet,local-qwen-small --repeats 2`

## 데이터 갱신 (주 1회 권장)
```bash
.venv/bin/python -m crawler.run all          # 수집(재확인·종료 처리 포함) → 규칙 추출 → 통계      [LLM 0]
.venv/bin/python -m crawler.insight run      # 모집단 안의 신규·변경 공고만 해석                  [Haiku, 공고당 1회]
.venv/bin/python -m crawler.persona_build    # 페르소나 수치                                       [LLM 0]
.venv/bin/python -m crawler.persona_write    # 입력 해시가 바뀐 단계만 카드 재작성                 [Sonnet]
```
자동 실행은 `crawler/run.sh`와 `launchd/career-coach.plist.template`(매주 일요일 04:00)를 씁니다. 아직 **등록하지 않았고, 사용자 승인이 필요합니다.**

## 사이트, 회사, 멘토 추가
- **사이트**: `crawler/adapters/<site>.py`를 작성하고 `crawler/sites.yaml`에 등록합니다. 등록 전에 robots.txt를 확인하고 50건으로 시험합니다.
- **회사 채용 보드**: `.venv/bin/python -m crawler.probe_boards <slug…>`로 Greenhouse나 Greeting 주소를 찾은 뒤 `companies.yaml`에 `ats`와 `slug`를 넣습니다.
- **회사 단계**: `companies.yaml`에 `stage`, `verified`, `source`, `as_of`를 넣습니다. 미분류 목록은 `data/stats/summary.md`와 `data/personas/_matrix.json`의 unknown_companies에 있습니다.
- **멘토**: `prompts/commands/mentor-add.md` 절차를 따라 `mentors/principles.yaml`에 추가합니다.

## 품질 점검
```bash
.venv/bin/python -m unittest discover -s tests          # 단위 테스트 26개
.venv/bin/python -m crawler.eval_extract score           # 추출 정확도 (현재 예비: data/eval/README.md)
.venv/bin/python -m crawler.insight check                # 해석 인용 정확도, 분포, 비용
.venv/bin/python -m crawler.insight revalidate           # 검증 규칙을 바꾼 뒤 저장분 재검증 (LLM 0)
```

## 에이전트로 작업할 때
- `AGENTS.md`가 진입점입니다.
- Claude Code에서는 `/resume-review` 같은 명령이 `prompts/commands/*.md`를 실행합니다.
- Codex 등 다른 에이전트에는 "prompts/commands/<name>.md를 읽고 수행하라. {PROFILE}=profiles/<id>"라고 지시합니다.
