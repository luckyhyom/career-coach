# profiles/ — 지원자별 데이터 (엔진과 분리)

- 엔진(크롤러, 통계, 페르소나, 리뷰 코드)은 저장소 루트에 있고, **사람마다 다른 데이터는 `profiles/<id>/`**에 있습니다.
- 각 프로필 폴더는 엔진 git에서 제외됩니다(`.gitignore`). 필요하면 폴더 안에 자체 git을 둡니다(예: 프로필 폴더 안에서 `git init`).
- 새 지원자는 `cp -R profiles/_template profiles/<id>`로 시작합니다.
- **이력서만 있어도 리뷰가 됩니다**: `resume.md`만 채우면 `python -m coach.cli review --profile profiles/<id>`가 동작합니다. 나머지 파일은 정확도를 높이는 선택 항목입니다.

| 파일 | 필수 | 용도 |
|---|---|---|
| resume.md | ✅ | 리뷰 대상 |
| experience.md | 선택 | 경험 재료 창고(E1…), 축 태그 → 공고 매칭 정확도 ↑ |
| skills.md | 선택 | 스킬 매트릭스 → /gap |
| profile.md | 선택 | 목표·희망 조건 → /target |
| applications.md | 선택 | 지원 결과 → /calibrate (품질 보정) |
| log/ | 선택 | 주간 실행 기록 → /plan-week, /weekly-report |
| reviews/ reports/ jobs/ | 자동 | 산출물 저장 위치 |
