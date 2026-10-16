---
name: resume-review
description: "이력서를 단계별 면접관 페르소나 + HR + 멘토 렌즈가 병렬로 리뷰한다. 사용: /resume-review [stage|uid]"
---
# /resume-review

1. `me/resume.md`를 읽는다. 비어 있거나 템플릿 그대로면 사용자에게 먼저 작성을 요청하고 멈춘다.
2. 리뷰어를 고른다.
   - stage 인자: 해당 단계 페르소나 + hr-recruiter + mentor-lens. stage→페르소나 매핑은 아래와 같다.
     - seed/series_a → seed-series-a-cto
     - series_b/series_c_plus → series-b-c-techlead
     - pre_ipo_unicorn → unicorn-senior
     - big_tech/enterprise → bigtech-interviewer
     - listed_mid → midsize-lead
     - si_agency → si-agency-pm
   - uid 인자: 공고의 회사 단계로 페르소나를 고르고, 공고 요건을 함께 전달한다.
   - 인자가 없으면 `/target` 상위 단계 1개를 쓴다.
3. 서브에이전트들을 **병렬로** 실행한다. 이력서 경로와 기준 데이터 경로만 넘긴다.
4. 결과를 합친다.
   - (a) 공통 지적 우선 정렬
   - (b) 라인별 수정안: 원문 → 제안, 근거
   - (c) 페르소나별 점수표
   - (d) 가장 큰 레버 3개
5. `reviews/YYYYMMDD-resume-<stage>.md`로 저장한다. 이전 리뷰 파일이 있으면 점수를 비교한다.
6. `me/resume.md`는 수정하지 않는다.
