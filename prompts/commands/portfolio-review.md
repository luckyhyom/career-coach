---
name: portfolio-review
description: "포트폴리오/GitHub 저장소(경로 또는 url)를 리뷰한다: README, 패키지 구조, 커밋, 설계 설명."
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /portfolio-review

1. 로컬 경로면 트리(`find -maxdepth 3`), README, 패키지 매니페스트, 최근 커밋 30개(`git log --oneline`)를 본다. GitHub url이면 `gh` CLI나 WebFetch로 같은 정보를 본다.
2. 관점
   - 패키지 구조가 설계 의도를 드러내는가 [멘토: saenggak-deungdae#원칙5]
   - README: 문제, 아키텍처 그림, 실행 방법, 기술적 의사결정과 트레이드오프, 성과 수치
   - 테스트 존재 여부와 CI 배지
   - 커밋 메시지 규칙
3. series-b-c-techlead와 unicorn-senior 관점 점수를 덧붙인다.
4. `{PROFILE}/reviews/YYYYMMDD-portfolio-<name>.md`로 저장한다.
- 저장 전에 review-critic으로 검수한다. FAIL 지적은 수정하거나 버리고, 결과 끝에 pass_rate를 적는다. 모든 지적은 `prompts/rubric.md`의 4요소를 따른다.
