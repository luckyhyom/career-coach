---
name: mock-interview
description: "단계별 면접관 페르소나로 이력서 기반 모의 면접(질문→꼬리질문→피드백). 사용: /mock-interview <stage> [주제]"
---
# /mock-interview

1. 단계 → 페르소나 매핑은 /resume-review와 같다. 해당 `personas/*.md`와 stage 통계를 읽고, 그 페르소나로 진행한다(실존 인물·회사 흉내는 금지).
2. `me/resume.md`에서 질문거리를 고른다. 주제 인자가 있으면 그 주제에 집중한다.
3. 한 번에 질문 1개를 던지고 사용자의 답을 기다린다. 답마다 꼬리질문을 1~2단계 던진다.
4. 5문항이 끝나면(또는 사용자가 종료하면) 피드백을 준다.
   - 문항별 점수(0~5), 좋았던 점, 빠진 핵심, 모범 답안의 뼈대
   - 다음 학습 항목 → `me/todo-backlog.md`에 추가할 것을 제안
5. 요약을 `reviews/YYYYMMDD-mock-<stage>.md`에 저장한다.
- 저장 전에 review-critic으로 검수한다. FAIL 지적은 수정하거나 버리고, 결과 끝에 pass_rate를 적는다. 모든 지적은 `personas/_rubric.md`의 4요소를 따른다.
