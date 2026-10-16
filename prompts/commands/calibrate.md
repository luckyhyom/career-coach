---
name: calibrate
description: "지원 결과({PROFILE}/applications.md)와 당시 리뷰 점수를 대조해 페르소나 기준·가중치가 실제 결과와 맞는지 점검한다. 결과 10건 이상일 때 사용."
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /calibrate
1. `{PROFILE}/applications.md`를 파싱한다. result가 '대기'·'지원취소'인 행은 제외한다. 남은 행이 10건 미만이면 "표본 부족"이라고 알리고 멈춘다.
2. 각 행의 review 파일을 읽고 페르소나별·기준별 점수를 뽑는다.
3. 서류 통과(서류합격 이상)와 탈락 그룹으로 나눠 기준별 평균 점수 차이를 표로 만든다. 단계(stage)별로도 나눈다.
4. 해석
   - 결과와 차이가 큰 기준 → 가중치를 올린다.
   - 차이가 없는 기준 → 가중치를 내리거나 앵커를 재정의한다.
   - 점수는 높은데 탈락한 사례 → 리뷰가 놓친 요인 가설을 세운다(회사 feedback 칸 참고).
5. `personas/*.md`의 평가 기준 수정안을 diff 형태로 제안한다. **바로 수정하지 않고 사용자 승인 후 반영한다.**
6. 결과를 `{PROFILE}/reviews/calibration-YYYYMMDD.md`로 저장한다. 표본 수와 한계(작은 표본, 회사 차이)를 반드시 적는다.
