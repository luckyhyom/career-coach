# Bugs found

- `crawler.insight.strip_bilingual()` starts searching for the English heading
  200 characters after the bilingual marker. Input
  `English text will follow Korean\n백엔드 개발자를 모집합니다.\nCompany Introduction\nWe build reliable services.`
  is returned unchanged; the English section should be removed even when the
  Korean body is short. Covered by the expected failure
  `BilingualTests.test_english_removed_after_short_korean_body`.
- `crawler.db.close_missing()` uses `max(2, 0.5 * len(ids))` as its closure
  threshold. With three open jobs for source `test`, IDs `1`, `2`, `3`, and
  present IDs `[1]`, it closes two jobs and returns `2`. More than half would
  close, so the requested guard should leave them open and return `0`.
  Covered by the expected failure
  `DatabaseTests.test_two_of_three_missing_does_not_close_jobs`.

No source files were changed.

## 처리 결과 (Claude, 2026-10-16)
- strip_bilingual: 수정함. 한국어 본문 길이와 무관하게, 한국어가 나온 뒤의 첫 영문 헤딩부터 제거.
- close_missing: 규칙을 명확히 함 — 빈 목록이면 절대 닫지 않음, 모집 중 4건 이상 보드는 절반 초과 소멸 시 거부, 4건 미만 보드는 정상 종료(그렇지 않으면 작은 회사의 실제 마감을 영원히 기록 못 함). 테스트를 이 규칙으로 갱신.
