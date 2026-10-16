---
name: target
description: "내 프로필과 단계별 공고 통계로 어떤 단계의 회사가 맞는지 근거와 함께 추천한다."
---
# /target

1. `me/profile.md`, `me/skills.md`, `data/stats/overall.json`의 by_stage와 각 stage JSON을 읽는다.
2. 단계별로 적합도를 0~100점으로 매긴다.
   - 내 스킬과 top_skills의 겹침
   - min_years_dist와 내 연차
   - 코테 비율과 현재 코테 준비도
   - profile의 희망 조건
3. 상위 2~3개 단계를 추천한다. 각 단계에 근거와, 그 단계에 맞춰 이력서에서 강조할 점을 쓴다.
4. 해당 단계의 페르소나(`personas/`)를 안내하고 `/resume-review <stage>`를 다음 행동으로 제안한다.
