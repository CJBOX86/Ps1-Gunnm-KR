# 작업 안내

『銃夢 -火星の記憶-』(PS1) 한글패치 프로젝트. 사용자와는 한국어로 대화한다.

- 현재 상태: [docs/status.md](docs/status.md), 결정 기록: [docs/decisions.md](docs/decisions.md), 분석 기록: [research/](research/)
- 빌드: `python tools/BUILD/build_patch.py` → `work/out/gunnm-kr-dev.{bin,cue,xdelta}` (원본 경로는 `config/local.json`)
- 번역: `assets/translation/` — 원문(일본어)은 저장소에 두지 않는다. 도구가 원본 디스크에서 읽는다(`tools/TEXT/srctext.py`). 대조는 `python tools/TRANSLATE/tr_view.py`
- 원본 디스크 이미지, 추출물, 빌드 출력(`work/`)은 저장소에 넣지 않는다
- 그림 속 글자: `config/graphics.json` (`tools/GRAPHICS/gfx_text.py`, 타이틀 로고는 `tools/GRAPHICS/title_logo.py`)
