---
name: mentor-add
description: "멘토 자료(url 또는 메모)를 원칙 카드로 요약해 mentors/에 추가한다. 사용: /mentor-add <url|메모>"
inputs: "{PROFILE} = 지원자 프로필 폴더 (기본 profiles/me, 환경변수 COACH_PROFILE)"
---
# /mentor-add

1. url이면 WebFetch로 내용을 가져온다. 영상이라 내용을 얻을 수 없으면 사용자에게 요약 메모를 요청한다.
2. 원칙 3~7개를 추가한다. **공개 자료**는 `mentors/principles.yaml`, **직접 받은 조언·유료 자료·개인 메모**는 `{PROFILE}/mentors/principles.yaml`(git 제외)에 넣는다.
   - 필드: id, source, source_type(direct_advice|published), evidence(링크·타임스탬프·위치), axis(AXES 또는 resume_format/job_search), criterion, applies_when{stages,roles,years}, good_example, bad_example, check.
   - 좋은 예와 나쁜 예는 원문에 근거가 있을 때만 쓴다. 없으면 빈 문자열로 둔다.
3. 원문에 없는 내용은 만들지 않는다. 그 사람이 직접 말한 것처럼 말투를 흉내 내지 않는다.
4. 같은 source의 기존 원칙과 중복되면 병합한다. `mentors/_index.md` 목록을 갱신한다. 사람이 읽는 md 카드는 선택이고, **principles.yaml이 정본**이다.
