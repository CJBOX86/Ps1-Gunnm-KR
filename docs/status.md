# 현재 상태

마지막 확인: 2026-10-06

## 대상과 원본

- 대상: 『銃夢 火星の記憶』 PlayStation, 일본판
- 지원 원본: `slps-01408-redump` — [config/source.json](../config/source.json). `tools/DISC/verify_source.py`로 로컬 이미지 일치 확인함
- 선언한 제품 범위·품질: **미정** ([D-001](decisions.md#d-001-한글화-범위) 대기)

## 빌드

- 디스크 반영 PoC 빌드: `tools/DISC/build_disc.py <manifest.json> <out_dir>` — 파일 교체(커지면 디스크 끝으로 재배치·ISO 디렉터리/PVD 갱신), Form 1 EDC/ECC 재계산, 계획 밖 변경 검사, 출력 재판독 검증, xdelta3 패치 생성·왕복 검증 — [PoC 기록](../research/poc/2026-10-06-disc-xdelta-poc.md)
- 대사 블록 코덱: `tools/TEXT/ldp.py` — 원본 767개 블록 byte 단위 재구성 확인
- 번역 개발 빌드: `tools/TEXT/extract_dialog.py`(원본 → 번역 자산) + `tools/BUILD/build_patch.py`(자산 → 폰트·대사 재구성 → 이미지·xdelta·보고서) — [형식](../assets/translation/README.md#이-프로젝트의-형식-2026-10-06-채택), [기록](../research/analysis/2026-10-06-translation-format.md)
- 제품 빌드: 개발 빌드만 있음. 배포 글꼴·폰트 매핑·메뉴 범위가 정해지면 제품 빌드로 확정
- 템플릿 Rust 참고 구현: 이 환경에 `cargo`가 없어 검증 명령을 **실행하지 않음**

## 확보한 근거

- [초기 조사](../research/survey/2026-10-06-initial-survey.md): 단일 MODE2 트랙, ISO 9660, 파일 1,688개. 메뉴 문자열은 실행 파일·`/NOR/*.E`에 평문 SJIS
- [타이틀 폰트 VRAM PoC](../research/poc/2026-10-06-title-font-vram.md): 적재 폰트 K00, VRAM 글리프 교체로 한글 표시
- [대사 경로 (Q1)](../research/analysis/2026-10-06-dialogue-path.md): 대사는 맵 스크립트 파일의 블록에 SJIS XOR 0x8C. 레코드 19,226개(고유 13,399), 복호화 `0x80034C3C`
- [폰트 용량 (Q2)](../research/analysis/2026-10-06-font-capacity.md): KNJ는 정렬된 SJIS 목록을 이진 탐색(`0x80027A8C`) → 한글을 임의 코드에 배정 가능. 코드 수정 없는 상한 1,444 슬롯(한글 약 1,350)/폰트
- [LDP 구조·길이 변경](../research/analysis/2026-10-06-ldp-structure.md): 대사는 LDP 마지막 섹션, sector 단위 스트리밍. 커진 파일을 디스크 끝으로 옮긴 이미지에서 대사 4줄(둘째 sector 포함) 정상 표시, 이후 장면 진행 확인
- [반각 띄어쓰기](../research/analysis/2026-10-06-halfwidth-space.md): 대사 렌더러 기계어 수정(`config/patches/halfwidth-space.json`)으로 한국어 띄어쓰기 폭 절반, 화면 확인
- [디스크 반영 PoC](../research/poc/2026-10-06-disc-xdelta-poc.md): 패치 이미지에서 타이틀 "누르세요", 프롤로그 첫 대사 "남자：응？" 표시 확인. xdelta 3,971 byte

## 완성을 좌우하는 미해결 조건

1. **장면↔폰트 매핑 나머지** — 폰트 번호는 상태+0x20(세이브 데이터), K04는 미사용 확인. 블록 464/726은 폰트 확정, 262개는 후보 여러 개(장별 관측 필요, 번역 블록 260개는 첫 후보 폰트 기준으로 빌드). 후보가 없던 2블록은 원문 1글자만 빠진 폰트(K07 「派」, K08 「縛」)로 배정. 폰트당 상한은 검증된 1,368자 — [기록](../research/analysis/2026-10-06-font-loading.md)
2. 번역 진행 — **전 장 초벌 번역(draft) 완료** (2026-10-07, 13,399줄 전부, 개발 빌드에 17,798줄 사용·되돌림 0, 12개 폰트 모두 1,368자 안). 남은 것: 사람 검수(review), 3장 이후 화면 확인. 이름 변경은 `tools/TRANSLATE/rename_term.py`
4. 대사 외 텍스트 — **완료(초벌)** (2026-10-07): 메뉴·시스템 문자열 446개(NOR/*.E 11개 파일 + 실행 파일, `assets/translation/menu/`, 기호·영문 26개는 keep), 그래픽 텍스트 8개(おまけ 제목, 월드맵 지명 라벨 7개 — `config/graphics.json`, `tools/GRAPHICS/gfx_text.py`, 글꼴 Pretendard Black OFL). 그림 전수 조사: 메뉴 텍스처(SAVE/LOAD·SHOP 등)·MBTEXT·S.S는 영어 또는 글자 없음. 타이틀 로고 銃夢·-火星の記憶- → 총몽·-화성의 기억-(tools/GRAPHICS/title_logo.py, Black Han Sans·나눔명조 OFL), 저작권 표기는 원본 유지. 남은 것: 게임 안 메뉴(아이템·상점·전과 등) 화면 확인, 영상(STR) 자막 여부 미조사

- 한글 글꼴: **Galmuri11 12px 채택** (OFL 1.1, [D-004](decisions.md#d-004-배포용-한글-글꼴)) — 저장소 안 `assets/fonts/sources/galmuri11/`, 빌드가 해시 검증

## 대기 중인 사람 결정과 병행 가능한 작업

- D-001 한글화 범위
- 결정 없이 진행 가능: 창 버퍼 크기 장면별 확인, 메뉴 문자열 조사
- 사람 도움이 있으면 빠른 것: 장별 세이브 파일(장면↔폰트 확정용)
