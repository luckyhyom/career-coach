---
name: job-fit
description: "공고 1건(uid 또는 url)과 내 이력의 적합도, 부족한 점, 이력서에서 강조할 점을 낸다. 사용: /job-fit <uid|url>"
---
# /job-fit

1. uid면 `sqlite3 data/jobs.sqlite "select company,title,experience,qualifications,preferred,description,skills,coding_test,assignment from jobs where uid='<uid>'"`로 조회한다.
2. url이면 WebFetch로 가져와 요건, 우대, 스택, 전형을 구조화한다. 원티드처럼 크롤러가 막힌 사이트는 사용자가 붙여넣은 텍스트를 쓴다.
3. 회사 단계는 `crawler/companies.yaml`에서 찾는다. 없으면 unknown으로 두고 추정 단계를 "의견"으로 제시한다.
4. 출력
   - 매칭 점수 (필수 요건 충족률, 우대 충족률)
   - 부족한 점과 대응 액션
   - 이력서에서 이 공고에 맞게 앞세울 bullet 3개 (`me/resume.md`에서 인용)
   - 예상 질문 5개
5. 저장 요청이 있으면 `jobs/YYYYMMDD-회사-포지션.md`로 저장한다.
