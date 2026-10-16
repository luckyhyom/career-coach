---
name: target
description: "내 경험 목록과 단계별 페르소나 데이터를 비교해 맞는 회사 단계·직무 유형과 지금 지원할 만한 공고 목록을 근거와 함께 추천한다."
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /target
1. 다음을 읽는다.
   - `{PROFILE}/experience.md`, `{PROFILE}/profile.md`
   - `data/personas/_matrix.md`
   - `data/personas/{early,growth,late,bigtech,mid}.json`의 axis_weight, distinctive_axes, red_flags, process_pct, min_years_median
   - `data/personas/role_*.json`
2. **경험 축 점수**: experience.md의 axes 태그와 증거 수준으로 내 축별 강도를 0~3으로 추정한다. 추정 근거로 E#을 단다.
3. **단계 적합도** = Σ(단계 축 가중치 × 내 축 강도)
   - 여기에 감점을 반영한다: 경계 신호 해당 여부, 연차 기준(min_years_median 대비), 전형 부담(코테 비율과 현재 준비도).
   - 결과를 단계별 점수표로 보여 준다.
4. **직무 유형 적합도**도 같은 방식으로 계산한다. 예: sdet_quality처럼 의외로 잘 맞는 유형을 드러낸다.
5. **지금 지원할 만한 공고 상위 10개**
   - `job_insights`에서 필수 항목 충족 추정치가 높은 공고를 고른다.
   - 각 공고에 uid, 회사, 한 줄 이유를 붙인다.
   - 이어서 `/job-fit <uid>`를 권한다.
6. **포지셔닝 한 문장**: "나는 ○○ 문제를 △△로 풀어 본 백엔드 개발자"를 데이터에 맞게 2개 제안한다.
7. confidence가 low인 단계는 결론을 약하게 쓴다. 이유도 함께 적는다(표본 수).
