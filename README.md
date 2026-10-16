# career-coach

**채용공고 데이터로 만든 단계별 면접관 관점**으로 이력서를 피드백하는 엔진입니다. 지금은 개인용 MVP이고, 이력서 피드백 서비스로 확장할 것을 전제로 설계했습니다.

- 수집, 추출, 통계는 스크립트가 맡습니다(LLM 0). LLM은 공고 해석(1회/공고), 페르소나 작성(1회/단계), 리뷰(1회/요청)에만 씁니다.
- 모든 지적에 근거 출처가 붙습니다: `[공고]`, `[통계]`, `[멘토]`, `[단계추정]`, `[의견]`. 인용 실재 여부와 수치 날조는 코드로 검증합니다.
- **이력서 파일 하나만 있으면 누구에게나 동작합니다.** 모델은 설정으로 바꿉니다(Claude, Ollama, OpenAI 호환).

처음 쓰는 경우: 에이전트(Claude Code, Codex 등)에게 **"AGENTS.md 0절대로 셋업해 줘"**라고 하면 설치 → 공고 수집 → 페르소나 생성 → (선택) 본인 메모 정리 순서로 진행합니다. 공개 저장소에는 공고 데이터와 개인 데이터가 들어 있지 않습니다.

```bash
.venv/bin/python -m coach.cli review --resume someone.md       # 단계 자동 선택 → 리포트 (docs/OUTPUT.md)
.venv/bin/python -m coach.cli panel --resume someone.md        # 단계 페르소나 5명 독립 판정 (평균 없음)
```

| 문서 | 내용 |
|---|---|
| [AGENTS.md](AGENTS.md) | 에이전트(Claude, Codex) 공통 진입점과 규칙 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 구조, 데이터 흐름, 품질 장치, 비용, 한계 |
| [docs/PERSONAS.md](docs/PERSONAS.md) | 단계별 평가 기준이 어떻게 다르고 어떻게 계산되나 |
| [docs/OUTPUT.md](docs/OUTPUT.md) | 최종 산출물(피드백 리포트) 형식 |
| [docs/DATA.md](docs/DATA.md) | 원문과 가공본 저장 정책, 장단점, 개인 데이터 |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | 설치, 실행, 모델 교체, 데이터 갱신, 확장 |
| [docs/DECISIONS.md](docs/DECISIONS.md) | 주요 결정과 이유 |
| [data/eval/README.md](data/eval/README.md) | 지표 신뢰 수준 (현재 예비) |

## License
[MIT](LICENSE)
