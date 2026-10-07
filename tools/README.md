# 도구

기능별로 폴더를 나눴다. 모든 명령은 저장소 최상위(`gunnm-kr-patch/`)에서 실행한다.

| 폴더 | 하는 일 | 주로 쓰는 명령 |
|---|---|---|
| `BUILD/` | 한글패치 빌드: 번역·글꼴·그림을 넣어 디스크 이미지와 xdelta를 만든다 | `python tools/BUILD/build_patch.py` |
| `TRANSLATE/` | 번역 작업 보조: 원문 대조, 이름 일괄 변경, 장 단위 번역 묶음 | `python tools/TRANSLATE/tr_view.py <블록ID>` / `rename_term.py 옛이름 새이름` |
| `TEXT/` | 게임 대사·메뉴 문자열 추출과 형식 처리 (대사 블록 코덱, 원문 캐시) | `python tools/TEXT/extract_dialog.py` / `extract_menu.py` |
| `GRAPHICS/` | 그림 속 글자 교체(보너스 제목·지명·타이틀 로고), 텍스처 추출 | `python tools/GRAPHICS/gfx_text.py` (미리보기) |
| `DISC/` | 원본 확인, 디스크(ISO 9660) 읽기, 파일 교체·재배치, EDC/ECC, xdelta | `python tools/DISC/verify_source.py` |
| `EMULATOR/` | DuckStation으로 원본 또는 패치 이미지 실행 | `./tools/EMULATOR/run_emulator.ps1 [cue]` |

## 파일

| 파일 | 설명 |
|---|---|
| `BUILD/build_patch.py` | 전체 빌드 (원본 확인 → 원문 추출 → 폰트 재구성 → 대사·메뉴·그림 교체 → 이미지·xdelta·보고서) |
| `TRANSLATE/tr_view.py` | 원문·번역 나란히 보기, 검색 |
| `TRANSLATE/rename_term.py` | 인물·용어 이름 일괄 변경 (조사 자동 수정) |
| `TRANSLATE/tr_batch.py` | 장(폰트) 단위 번역 작업 파일 내보내기·검사·반영 |
| `TEXT/extract_dialog.py` | 대사 블록 추출 → `assets/translation/segments/` |
| `TEXT/extract_menu.py` | 메뉴·시스템 문자열 추출 → `assets/translation/menu/` |
| `TEXT/srctext.py` | 원문(일본어)을 원본에서 읽어 번역 자산에 붙이고 떼기 (저장소에는 원문 없음) |
| `TEXT/ldp.py` | 대사 블록(LDP) 읽기·다시 만들기 |
| `TEXT/dialog_text.py` | 대사 표기 ↔ 게임 바이트 변환, 제어 코드 검사 |
| `TEXT/dialog_scan.py` | 맵 파일에서 대사 블록 찾기 (조사용) |
| `GRAPHICS/gfx_text.py` | 4bpp 그림에 한글 다시 그리기 (`config/graphics.json`) |
| `GRAPHICS/title_logo.py` | 타이틀 로고 「총몽 -화성의 기억-」·크레딧 그리기 |
| `GRAPHICS/extract_textures.py` | 디스크의 이미지를 PNG로 추출 (HD 리텍스처 참고용) |
| `DISC/verify_source.py` | 원본 이미지 크기·해시 확인 |
| `DISC/psxdisc.py` | 디스크 파일 목록·추출 |
| `DISC/build_disc.py` | 파일 교체·재배치, 이미지·xdelta 생성과 왕복 검증 |
| `DISC/cdsector.py` | CD 섹터 EDC/ECC 계산 |
| `EMULATOR/run_emulator.ps1` | DuckStation 실행 |
