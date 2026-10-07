# 번역 자산 형식

## 대사 (segments/)

- 색인: [index.json](index.json) — 지원 원본, 범위(본편 대사 블록, 조사 미완료), 모집단(블록·줄 수와 `id`+원문 해시), 조각 목록, 릴리스 승인(없음)
- 조각: `segments/<폴더>.json` (예: `M3-O.json`) — 블록(장면) 단위로 묶는다
  - 블록: `id`(첫 파일 경로), `files`(같은 내용의 모든 사본), `font_candidates`(이 블록을 그릴 수 있는 K 폰트)
  - 줄: `id`(`블록ID#번호`), `flags`, `ko`(번역, 없으면 null), `status`, `note`
  - **원문(`src`)은 저장소에 두지 않는다** (2026-10-07, 공개 저장소용). 도구가 원본 디스크에서 추출해 `work/src/`에 캐시하고 줄 ID로 붙인다 — [tools/TEXT/srctext.py](../../tools/TEXT/srctext.py). 원문 대조는 `python tools/TRANSLATE/tr_view.py <블록ID>`
  - `ref`가 있는 줄은 원문이 같은 다른 줄을 가리킨다. 그 줄만 번역하면 따라간다. 따로 번역하려면 `ref`를 지우고 `ko`를 쓴다
- 상태: `untranslated` 미번역 / `draft` 작업 중 / `review` 교차 검토 필요 / `decision` 사람 판단 필요 / `done` 완료
- 표기:
  - 실제 줄바꿈 = 게임 줄바꿈, `{page}` = 페이지 넘김
  - `{WS2503}`, `{b3}`, `{br}` 등 중괄호 코드는 원문과 **같은 순서로** 남긴다 (줄바꿈·페이지는 자유)
  - `{b2}`/`{b3}`은 글자색, `{br}`은 색 해제(줄바꿈 아님). `{WSwwhh}`는 창 크기(너비 ww칸 × hh줄), 기본 너비 25칸
  - 한 줄이 창 너비를 넘으면 게임이 글자 단위로 잘라 넘긴다 → 빌드가 경고. 이름(`이드：`)도 칸에 포함
  - 띄어쓰기는 반각 폭으로 그려지지만 줄 길이 계산에서는 1칸으로 센다. `,`는 `、`로, `･`·`…`는 `・`로 자동 변환
- 원본에서 다시 추출: `python tools/TEXT/extract_dialog.py` (기존 번역·상태 보존, 원문이 바뀐 줄은 `decision`)
- 검사만: `python tools/TEXT/extract_dialog.py --check`
- 개발 빌드: `python tools/BUILD/build_patch.py` — 정책은 [config/build.json](../../config/build.json) (draft 이상을 비배포 개발 빌드에 사용)

### 메뉴 문자열 (2026-10-07 추가)

- 위치: `menu/<파일>.json` — `python tools/TEXT/extract_menu.py`로 추출·갱신 (`--check`로 검사만). 대상 파일은 스크립트의 `MENU_FILES`
- 항목: `id`(`파일@오프셋`), `offset`, `slot`(쓸 수 있는 최대 byte, 한글·전각 1글자 = 2byte, 제어 코드는 글자 수만큼), `ko`, `status`, `note`
- 제자리 교체라 번역문이 `slot`을 넘으면 빌드 실패. 띄어쓰기는 전각 공백으로 들어간다(메뉴 렌더러는 반각 공백 코드 미지원 — 화면 확인)
- 정렬은 앞에 전각 공백(`　`)을 넣어 맞춘다. `{WS..}{BL..}` 창 코드는 원문 순서 유지, `{g5}`·`{g8}` 같은 g코드(간격 조정)는 자유
- `status: keep` = 번역하지 않음(숫자 표, 시간 서식, 메모리 카드 파일 제목처럼 본체 BIOS가 표시하는 것)
