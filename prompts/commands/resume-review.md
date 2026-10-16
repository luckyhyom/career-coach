---
name: resume-review
description: "이력서를 단계별 면접관 페르소나 + HR + 멘토 렌즈가 병렬로 리뷰한다. 사용: /resume-review [stage|uid]"
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /resume-review

1. `{PROFILE}/resume.md`를 읽는다. 비어 있거나 템플릿 그대로면 사용자에게 먼저 작성을 요청하고 멈춘다.
2. 리뷰어를 고른다.
   - stage 인자: 해당 단계 페르소나 + hr-recruiter + mentor-lens. stage→페르소나 매핑은 아래와 같다.
     - seed/series_a/early → stage-early
     - series_b/series_c_plus/growth → stage-growth
     - pre_ipo_unicorn/foreign/late → stage-late
     - big_tech/enterprise/bigtech → stage-bigtech
     - listed_mid/si_agency/mid → stage-mid
     - 선택: 직무 유형 인자(product_backend, sdet_quality 등)는 `data/personas/role_<type>.json` 보정으로 함께 전달한다.
   - uid 인자: 공고의 회사 단계로 페르소나를 고르고, 공고 요건을 함께 전달한다.
   - 인자가 없으면 `/target` 상위 단계 1개를 쓴다.
3. 서브에이전트들을 **병렬로** 실행한다. 이력서 경로와 기준 데이터 경로만 넘긴다.
4. **품질 게이트**: 합친 초안을 `{PROFILE}/reviews/.draft.md`에 쓰고 review-critic 서브에이전트로 검수한다.
   - FAIL 지적은 fix_hint를 반영해 해당 페르소나에게 다시 받거나 직접 고친다. 최대 2회 반복한다.
   - 두 번째에도 FAIL인 지적은 버린다.
   - 최종 리뷰 끝에 `품질: pass_rate N%, 버린 지적 M개`를 적는다.
5. 결과를 합친다.
   - (a) 공통 지적 우선 정렬
   - (b) 라인별 수정안: 원문 → 제안, 근거
   - (c) 페르소나별 점수표
   - (d) 가장 큰 레버 3개
6. `{PROFILE}/reviews/YYYYMMDD-resume-<stage>.md`로 저장한다. 맨 위에 메타데이터를 둔다: `resume_sha: <git hash-object {PROFILE}/resume.md 앞 8자>`, stage, 페르소나 목록, 총점.
   - 이전 리뷰 파일이 있으면 점수를 비교한다.
7. `{PROFILE}/applications.md`가 있으면, 이 리뷰를 근거로 지원할 경우 기록할 "리뷰 파일명 / resume_sha / 총점"을 안내한다.
8. `{PROFILE}/resume.md`는 수정하지 않는다.
