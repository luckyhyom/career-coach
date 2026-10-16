---
name: job-fit
description: "공고 1건(uid 또는 url)을 정밀 해석과 내 경험 목록으로 짝지어 적합도, 진짜 갭과 무시해도 될 갭, 앞세울 경험과 표현을 낸다. 사용: /job-fit <uid|url>"
---
# /job-fit
1. **공고 해석 불러오기**
   - uid면 `sqlite3 data/jobs.sqlite "select data from job_insights where uid='<uid>'"`로 가져온다(팀 문제, 필수·업무·우대 항목과 원문, 경계 신호, 전형).
   - 해석이 없으면 `.venv/bin/python -m crawler.insight run --uids <uid>`로 먼저 만든다.
   - url이면 WebFetch로 원문을 가져와 같은 형식으로 해석한다. 원티드처럼 막힌 사이트는 사용자가 붙여넣은 텍스트를 쓴다.
2. **회사 단계** = `crawler/companies.yaml`에서 찾는다. 없으면 해석의 stage_hint를 쓴다. 단계 페르소나는 `data/personas/<band>.json`이다.
3. **매칭**: `me/experience.md`의 경험(E1…)과 공고 항목을 짝짓는다. 항목마다 판정한다.
   - ✅ 충족: 경험 E#의 어떤 사실이 근거인지 쓴다.
   - ◐ 부분 충족: 어떤 증거를 보강하면 되는지 쓴다. `[?]` 칸이 있으면 그 칸을 지목한다.
   - ❌ 미충족
     - **필수(must)**이면 "진짜 갭". 지원 전에 대응할지, 지원은 하고 면접에서 설명할지 권고한다.
     - **우대(nice)**이면 "무시 가능"으로 분류한다.
4. **출력**
   - 한 줄 판정: 지원 권장 / 조건부 / 비권장. 근거는 필수 충족률과 경계 신호 해당 여부다.
   - 이 팀이 풀려는 문제(team_problem) → 내 경험 중 가장 가까운 이야기 1개와 그 이유.
   - 이력서 bullet 수정안 3개
     - 공고 원문 표현에 맞춰 `me/resume.md` 문장을 바꿔 쓴다. 전/후를 함께 보여 준다.
     - 모르는 수치는 `[측정값]`으로 둔다.
   - 예상 질문 5개와 꼬리질문. 공고의 work 항목과 단계 페르소나의 question_bank에서 가져온다.
   - 진짜 갭과 무시 가능한 갭 표.
5. 모든 판정에 근거를 붙인다: `[요건: "원문" (uid)]` / `[경험: E#]` / `[페르소나: <band> lift]`.
6. 저장 요청이 있으면 `jobs/YYYYMMDD-회사-포지션.md`로 저장한다. 지원하면 `me/applications.md`에 기록하도록 안내한다.
