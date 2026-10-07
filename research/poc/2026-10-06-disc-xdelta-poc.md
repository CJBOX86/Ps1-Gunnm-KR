# 디스크 반영·xdelta 패치 PoC — 2026-10-06

## 도구
- `tools/DISC/cdsector.py`: Mode 2 Form 1 EDC/ECC 재계산. 원본 Form 1 sector 42개에서 재계산 결과가 원본과 일치
- `tools/DISC/build_disc.py <manifest.json> <out_dir>`: 같은 크기 파일 교체 → 패치 bin/cue → `xdelta3 -e -9` → `xdelta3 -d`로 되돌려 SHA-256 대조
  - 검사: 원본 식별, 인터리브 제외, 크기 불변, 원본 sector EDC/ECC 자가 검증, sector 단일 소유, 계획 밖 변경 없음, xdelta 왕복 일치
  - xdelta3 경로는 `config/local.json`의 `xdelta3` (xdelta3 3.2.0 사용)
- `work/make_poc_inputs.py`: PoC 입력 생성 (Gulim 12px로 한글 렌더링)

## PoC 내용
- K00.TIM: 프롤로그·메뉴에서 쓰지 않는 한자 슬롯 7개(哀扱鋭炎黄丸輝)에 누·르·세·요·남·자·응
- NOR/TITLE.E 0x2000: "スタートボタンを押してください" → "スタートボタンを" + 누르세요 코드
- M3/O/MP801_0.LDP 0x2E02C: "男：ん？" → "남자：응？" (레코드 길이 유지)

## 결과
- 변경 sector 5개, xdelta 3,971 byte, 왕복 검증 일치. 출력 SHA-256 `60233bc9…2f64`
- emucap으로 패치 이미지 부팅: 타이틀 "누르세요", 프롤로그 첫 대사 "남자：응？" 표시 확인 (`work/poc_disc_title_zoom.png`, `work/poc_disc_dlg_zoom.png`). 메뉴 가나는 그대로 정상

## 한계
- 파일 크기 변경 미지원 (대사 길이가 늘면 필요). ISO 디렉터리 레코드·LBA 재배치 또는 파일 내부 여유 공간 활용을 설계해야 함
- 템플릿의 Expected Write 형식 대신 Python 내부 쓰기 계획을 쓴다. 제품 빌드로 올릴 때 정식화 필요
- Gulim은 Microsoft 글꼴이라 배포용 글리프 원천으로는 라이선스 확인 필요 (PoC 전용)
