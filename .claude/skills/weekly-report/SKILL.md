---
name: weekly-report
description: "주간 리포트 생성(자동 실행용). crawler 통계 + 지난주 로그 → reports/YYYY-Www.md"
---
# /weekly-report

토큰 절약을 위해 다음 파일만 읽는다: `data/stats/summary.md`, `data/stats/overall.json`, 지난주 리포트(있으면), 최근 `me/log/*.md` 1개, `me/skills.md`, `me/todo-backlog.md`(제목만).
`reports/YYYY-Www.md`(이번 주 ISO 주차)를 아래 구조로 작성한다.
1. **지난주 실행** — 로그 기준으로 한 것과 안 한 것. 로그가 없으면 "기록 없음"이라고 쓰고 기록을 권한다.
2. **시장** — 공고 수, 출처별, 단계별 분포. 지난주 리포트 대비 증감과 새로 뜬 키워드.
3. **갭 상위 3개** — /gap 방식, 표 하나.
4. **이번 주 트랙 2~3개** — 근거와 완료 기준 포함.
5. **분류 필요 회사** — overall.json의 unclassified_companies 상위 10개. `crawler/companies.yaml`에 추가할 것을 제안한다.
6. **멘토 원칙 리마인드 1개** — mentors/ 카드에서 이번 주 트랙과 관련된 것.
7. **크롤러 상태** — `sqlite3 data/jobs.sqlite "select site,requests,new_jobs,status from runs order by started_at desc limit 8"`. 차단이나 실패가 있으면 표시한다.
분량은 A4 1장 이내로 한다. 작성 후 `git add reports && git commit -m "weekly report YYYY-Www"`를 실행한다.
