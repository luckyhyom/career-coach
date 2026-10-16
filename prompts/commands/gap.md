---
name: gap
description: "공고 통계와 내 스킬 매트릭스를 비교해 단계별 갭과 우선순위를 낸다. 사용: /gap [stage]"
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /gap

1. `data/stats/summary.md`와 `data/stats/<stage>.json`(없으면 overall.json)을 읽는다. 공고 원문은 읽지 않는다.
2. `{PROFILE}/skills.md`를 읽고 top_skills의 각 skill과 이름을 매칭한다.
3. 갭 점수 = 공고 비율(pct) × (3 − 내 수준) / 3. 상위 10개로 표를 만든다.
   - 열: skill | 공고 비율 | 내 수준 | 갭 점수 | 실무/보상/흥미 메모
4. 코딩테스트·과제 비율을 보고 준비 비중(코테 vs 과제 vs 포트폴리오)을 제안한다.
5. 상위 3개 갭마다 `{PROFILE}/todo-backlog.md`에서 대응 항목을 찾아 연결한다. 없으면 새 항목을 제안한다.
6. 결과를 화면에 출력한다. 요청이 있으면 `{PROFILE}/reports/gap-YYYYMMDD.md`로 저장한다.
