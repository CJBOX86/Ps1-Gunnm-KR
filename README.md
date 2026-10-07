# 총몽 -화성의 기억- 한글패치

PlayStation 『銃夢 -火星の記憶-』(Gunnm: Kasei no Kioku, SLPS-01408, 1998 BANPRESTO)의 비공식 한글패치 프로젝트입니다.

- 한글화: **리샤오랑**
- 범위: 본편 대사 전체(13,399줄), 메뉴·시스템 문구(446개), 그림 속 글자(타이틀 로고, 보너스 메뉴 제목, 월드맵 지명)
- 상태: 1차 번역 완료, 검수 중 (베타)
- 표기 기준: 국내 정발판 『총몽』(서울문화사)

> 이 저장소에는 게임 원본, 원본에서 추출한 데이터, **일본어 원문 대사**가 들어 있지 않습니다.
> 빌드와 원문 대조에는 직접 가진 원본 디스크 이미지가 필요합니다.

## 패치만 쓰려면

[Releases](../../releases)에서 xdelta 패치를 받아 원본에 적용하세요. 필요한 원본(Redump 덤프)과 적용 방법은 [RELEASE_README.md](RELEASE_README.md)에 있습니다.

## 직접 빌드하기

필요한 것: Python 3.11 이상 + `pip install pillow`, xdelta3, Redump 원본(`SLPS-01408`, 해시는 [config/source.json](config/source.json))

1. `config/local.example.json`을 `config/local.json`으로 복사하고 원본 `.bin`·xdelta3 경로를 적습니다.
2. 원본 확인: `python tools/DISC/verify_source.py`
3. 빌드: `python tools/BUILD/build_patch.py` (약 1~2분)
   → `work/out/gunnm-kr-dev.{bin,cue,xdelta}`와 보고서 `gunnm-kr-dev.report.json`

빌드는 원본에서 원문을 추출해 번역과 맞춘 뒤, 한글 글리프를 폰트에 넣고 대사·메뉴·그림을 교체해 디스크 이미지와 xdelta를 만듭니다. 원본에 xdelta를 다시 적용해 결과가 같은지까지 검사합니다.

## 번역 고치기

번역은 `assets/translation/`에 있습니다.

| 위치 | 내용 |
|---|---|
| `segments/*.json` | 대사. 블록(장면)별 줄 `id`, 번역 `ko`, 상태 `status`, 메모 `note` |
| `menu/*.json` | 메뉴·시스템 문구. `slot`은 그 자리에 들어갈 수 있는 최대 byte(한글 1자 = 2byte) |
| `glossary.json` | 인물·지명·용어 표기 |
| [README.md](assets/translation/README.md) | 표기 규칙(제어 코드 `{…}`, 줄바꿈, 창 너비) |

원문은 저장소에 없으므로 대조 도구로 원본 디스크에서 읽어 봅니다.

```bash
python tools/TRANSLATE/tr_view.py M3/O/MP801_0
```

```bash
python tools/TRANSLATE/tr_view.py --find 이드
```

```bash
python tools/TRANSLATE/tr_view.py --find-src イド
```

- 고칠 줄의 `ko`를 수정하고 `status`를 `review`(검수 필요) 또는 `done`(완료)으로 바꾼 뒤 다시 빌드합니다.
- 인물 이름 일괄 변경: `python tools/TRANSLATE/rename_term.py 옛이름 새이름` (미리보기) → `--apply`. 받침에 맞춰 조사도 고칩니다. 단어 일부가 같이 바뀌지 않았는지 미리보기를 확인하세요.
- 장(章) 단위로 묶어 번역할 때: `python tools/TRANSLATE/tr_batch.py` (원문 포함 작업 파일을 `work/tr/`에 만들고, 검사 후 반영)
- 한 줄이 창 너비를 넘으면 빌드가 경고합니다. 메뉴 문구는 `slot`을 넘으면 빌드가 실패합니다.

그림 속 글자는 [config/graphics.json](config/graphics.json)(보너스 제목, 월드맵 지명, 타이틀 로고·크레딧)에서 문구·위치·크기를 바꿉니다.

## 구성

| 위치 | 내용 |
|---|---|
| `tools/` | 원본 확인, 디스크 읽기·쓰기, 대사·메뉴 추출, 빌드, 그림 글자 교체 |
| `assets/translation/` | 번역 (원문 제외) |
| `assets/fonts/` | 한글 글꼴(모두 SIL OFL 1.1)과 출처·해시 |
| `config/` | 지원 원본, 빌드 정책, 기계어 패치(띄어쓰기 반각), 그림 교체 설정 |
| `research/` | 분석 기록 (대사 경로, 폰트 구조, 디스크 재배치 등) |
| `docs/` | 현재 상태와 결정 기록 |

작업 방법은 [create-retro-game-kr-patch](https://github.com/mcpads/create-retro-game-kr-patch)와 [create-kr-patch-template](https://github.com/mcpads/create-kr-patch-template)을 참고했습니다.

## 라이선스

[LICENSE](LICENSE)를 보세요. 요약:

- **도구 코드**: MIT
- **글꼴**: 각 글꼴의 SIL Open Font License 1.1 (`assets/fonts/sources/*/OFL.txt`)
- **번역문**(`assets/translation/`): 리샤오랑의 비영리 팬 번역. CC BY-NC-SA 4.0 — 출처 표시, 비영리, 같은 조건으로만 공유
- 원작 게임과 그 내용의 권리는 각 권리자에게 있습니다. 이 프로젝트는 원작사와 관계없는 비공식 팬 작업입니다.

『銃夢』 © 木城ゆきと / YUKITO PRODUCTS INC. © 集英社 / ヤングジャンプコミックス刊 © Ea © BANPRESTO 1998
