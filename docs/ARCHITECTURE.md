# 아키텍처

## 목적
실제 채용공고와 멘토 원칙을 근거로 **이력서 피드백**과 **취업 준비 방향**을 제시한다. 지금은 개인용 MVP로 운영하고, 이후 이력서 피드백 서비스로 확장하는 것을 전제로 설계했다.

## 설계 원칙
1. **결정적 작업은 코드, 해석만 LLM**
   - 수집, 정제, 중복 제거, 변경 감지, 통계는 스크립트로 처리한다.
   - LLM은 세 지점에서만 쓴다: 공고 해석(공고당 1회), 페르소나 작성(단계당 1회), 리뷰(요청당 1회).
2. **캐시와 증분 처리**
   - 공고 해석은 본문 해시가 바뀔 때만 다시 한다.
   - 페르소나 카드는 입력 해시(데이터, 프롬프트, 모델, 버전)가 바뀔 때만 다시 만든다.
   - 이력서 프로필은 이력서 해시당 1회만 만든다.
3. **근거 우선**
   - 모든 판단에 출처 유형을 붙인다: 공고, 통계, 멘토, 단계추정, 의견.
   - LLM 출력은 결정적 검증기를 통과한 것만 남긴다.
4. **엔진과 개인 데이터 분리**
   - 엔진은 이력서 한 장만으로 동작한다.
   - 개인 데이터는 `profiles/<id>/`에 둔다(엔진 git과 분리).
5. **교체 가능성**
   - 모델: `coach/models.yaml`의 routes로 바꾼다.
   - 에이전트: `prompts/`를 쓰고, Claude와 Codex는 각자 래퍼만 둔다.
   - 수집 사이트: 어댑터를 추가하면 된다.

## 데이터 흐름
```
[수집 crawler/run.py] ── 사이트 어댑터(rallit, ats: greenhouse/lever/greeting, saramin_api, remember)
   │  fetch.py: 도메인당 ~0.3 req/s + 지터, robots.txt, 429/503 백오프, 403 즉시 중단, 조건부 GET 캐시(data/raw)
   │  변경 감지: 본문 해시(content_hash) / 상세 재확인(recheck_days=14) / 목록에서 사라지면 status=closed
   │            (대량 소멸 안전장치: 빈 목록 또는 4건 이상 보드의 절반 초과 소멸은 종료 처리 거부)
   ▼
[jobs.sqlite: jobs]  원문 텍스트(정제) + 메타 + 상태
   │
   ├─ extract.py (규칙, LLM 없음)  기술 키워드·최소 경력·코테/과제 → jobs 컬럼
   ├─ stats.py (규칙)              공통 모집단(population.py) 기준 단계별 통계 → data/stats/*.json, summary.md
   └─ insight.py (LLM 1회/공고)    팀 문제·필수/업무/우대 항목(축 분류+원문 인용)·경계 신호·전형·단계 단서
         │  인용 전문 대조 검증, 실패 항목 폐기 → jobs.sqlite: job_insights
         ▼
      persona_build.py (결정적)   회사 균형 가중 × 축소추정 → 단계·직무별 축 가중치/lift/인용/전형 → data/personas/*.json
         ▼
      persona_write.py (LLM 1회/단계, 해시 캐시)  카드 작성 → 존재+지지 검사 → personas/stage-*.md

[리뷰 coach/cli.py]
   resume ─ redact.py(PII 제거) ─ candidate.py(LLM, 해시 캐시: 축별 근거 수준 0~3, 인용 검증)
          ─ target.py(결정적: 단계 적합도) ─ context_pack.py(필요한 근거만 ~1.5~3K 토큰)
          ─ review.py(LLM 1회 + 결정적 검증) ─ report.py(고정 형식 리포트 md+json)
```

## 공통 모집단 (`crawler/population.py`)
통계, 공고 해석 대상, 페르소나가 모두 **같은 정의**를 쓴다. 정의는 모든 산출물에 기록된다.
- **게시일 티어**
  - `recent`: 최근 30일 안에 게시
  - `open_older`: 오래전에 게시됐지만 모집 중
  - `unknown_date`: 게시일 미상
- **뷰**
  - `open`: 현재 모집 중. 마지막 수집 기준 14일 안에 확인되고 status가 open인 공고. 페르소나의 기본값이다.
  - `recent`: open 중에서 recent 티어인 공고. 최근 신규 채용 동향을 볼 때 쓴다.
- **공통 필터**: 국내 근무, 프론트엔드 단독 직무 제외, 요구 최소 경력 7년 이하
- **회사 단계 판정**: `companies.yaml`(출처 기록) → 공고 안의 단계 단서(인용으로 검증된 것) → unknown 순으로 정한다(`resolve_stage`).

## 평가 축 (12개, 모든 단계 공통)
| 축 | 보는 것 |
|---|---|
| ownership | 제품 오너십 |
| scale_performance | 대규모 트래픽, 성능 |
| consistency_reliability | 정합성, 장애 대응 |
| code_quality_testing | 코드 품질, 테스트 |
| infra_ops | 인프라, 운영 |
| integration_legacy | 외부 연동, 레거시 개선 |
| cs_fundamentals | CS 기본기 |
| domain | 도메인 지식 |
| ai_leverage | AI 활용과 검증 |
| adaptability | 스택 무관, 빠른 학습 |
| language_framework | 특정 언어·프레임워크 숙련 |
| collaboration | 협업, 문서화, 리더십 |

축이 고정돼 있어서 단계끼리, 이력서끼리, 시점끼리 비교할 수 있다. 페르소나 방법은 `docs/PERSONAS.md`에 있다.

## 품질 장치
| 단계 | 장치 | 위치 |
|---|---|---|
| 수집 | robots, 요청 간격, 차단 시 중단, 대량 종료 안전장치, 제목 변경 시 같은 공고로 갱신 | fetch.py, db.py |
| 추출 | 키워드 사전 + 조사 경계 처리 + 공통 안내문 줄 제거. F1 0.969는 **예비 수치** | extract.py, data/eval |
| 해석 | 스키마 고정 출력, 인용 전문 대조 | insight.py |
| 페르소나 | 회사 균형 가중, 축소추정, 유사도 0.95 초과 시 병합 후보, 근거 회사 3개 미만이면 대체 카드, 인용의 존재 검사와 지지 검사 | persona_build.py, persona_write.py |
| 리뷰 | 루브릭(앵커, 지적 4요소, 아첨 방지, 출처 표시) + 결정적 검증(인용 실재, 공고 인용 실재, 멘토 id, 단위 붙은 수치 날조, 과장 표현) | prompts/rubric.md, coach/review.py |
| 에이전트 리뷰 | review-critic 검수 (최대 2회 수정) | prompts/reviewers/review-critic.md |
| 평가 | 모델 비교 (정확성, 문제 발견, 실용성, 직무 적합성, 일관성, 비용, 시간) + 사람 채점 시트 | eval/review_eval.py |
| 보정 | 지원 결과로 기준 보정 | prompts/commands/calibrate.md |

## 비용 (실측, 2026-10-16)
| 항목 | 비용 |
|---|---|
| 공고 해석 | 약 $0.0035/건 (Haiku). 290건 누적 약 $1 |
| 페르소나 카드 | 약 $0.1/단계 (Sonnet). 입력이 같으면 $0 |
| 리뷰 1회 | Haiku 약 $0.006~0.011, Sonnet 약 $0.057 (가상 이력서 기준) |
| 수집·추출·통계 | $0 |

## 알려진 한계
- 원티드, 리멤버, 로켓펀치, 점핏은 봇 차단이 걸려 있어 우회하지 않는다. 그래서 수집 출처가 치우쳐 있다. 사람인 API 키가 있으면 보강할 수 있다.
- 회사 단계를 판정하지 못한 공고가 약 45%다. 성장기, 후기, 대기업 단계는 6~7개사 수준이라 신뢰도가 medium이다.
- 정확도 지표는 모두 예비 수치다. Claude가 붙인 라벨이고, 멘토 라벨로 아직 검증하지 않았다.
