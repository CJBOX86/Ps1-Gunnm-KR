"""메뉴·시스템 문자열(NOR/*.E 등 평문 SJIS)을 번역 자산으로 추출하거나 갱신한다.

사용법:
  python tools/TEXT/extract_menu.py [--check]

출력: assets/translation/menu/<파일>.json (대상 파일 목록은 MENU_FILES)
  - 항목: id = "파일@오프셋(16진)", src(자산 표기, 수정 금지), ko, status, note,
          slot = 그 자리에 쓸 수 있는 최대 byte 수(원문 종료 0 뒤 4byte 경계까지 - 종료 0 한 개)
  - 문자열은 제자리 교체한다: 번역문 인코딩 길이가 slot 이하여야 하고 나머지는 0으로 채운다
  - 기존 자산의 ko/status/note는 보존한다. 원문이 바뀐 항목은 status를 decision으로 바꾼다
"""
import json
import os
import re
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import dialog_text as dt  # noqa: E402
import psxdisc  # noqa: E402
import srctext  # noqa: E402
import verify_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MDIR = os.path.join(ROOT, "assets", "translation", "menu")
MENU_FILES = ["/NOR/TITLE.E;1", "/NOR/LOADSAVE.E;1", "/NOR/GAMEOVER.E;1", "/NOR/SHOP.E;1", "/NOR/CYBNE.E;1",
              "/NOR/KANKINZ.E;1", "/NOR/SENKA.E;1", "/NOR/ELIST.E;1", "/NOR/GM02.E;1", "/NOR/OMAKE.E;1",
              "/NOR/WORLD00.E;1", "/SLPS_014.08;1"]
# MBALL·MPO*·SHOT.E는 문자열이 아닌 바이트가 한자 쌍으로 읽히는 것뿐이라 제외
STRING = re.compile(rb"(?:[\x20-\x7e]|[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc])+\x00")


def scan(data):
    """(오프셋, 자산 표기, slot). 가나가 있거나 한자·전각 2글자 이상이고 제어 코드 외 ASCII가 없는 것만."""
    out = []
    for m in STRING.finditer(data):
        raw = m.group()[:-1]
        try:
            asset = dt.to_asset(raw.decode("cp932"))
        except (UnicodeDecodeError, ValueError):
            continue
        text = "".join(v for k, v in dt.split(asset) if k == "text").replace("\n", "")
        if not (re.search(r"[぀-ヿ]", text) and len(text) >= 2 or re.fullmatch(r"[一-鿿　-〿＀-￯]{2,}", text)):
            continue
        # 뒤따르는 0이 다음 데이터의 일부일 수 있어, 원래 종료 0을 포함한 4byte 경계까지만 쓴다
        end = min(m.end() + (-m.end() % 4), len(data))
        while end > m.end() and any(data[m.end():end]):  # 그 사이에 0이 아닌 byte가 있으면 거기서 멈춤
            end -= 1
        out.append((m.start(), asset, end - m.start() - 1))
    return out


def file_key(path):
    return path.strip("/").split(";")[0].replace("/", "_")


def extract(src_bin):
    disc = psxdisc.Disc(src_bin)
    ents = {e["path"]: e for e in disc.walk()}
    res = {}
    for p in MENU_FILES:
        data = disc.read_file(ents[p])
        res[p] = [{"id": f"{p.strip('/').split(';')[0]}@{o:04X}", "offset": o, "slot": s, "src": a}
                  for o, a, s in scan(data)]
    return res


def main(argv):
    check = "--check" in argv
    local = verify_source.local_config()
    src_bin = os.path.join(ROOT, local["source_bin"])
    fresh = extract(src_bin)
    srctext.save_cache("menu.json", srctext.menu_map(fresh))
    bad = 0
    for p, items in fresh.items():
        fn = os.path.join(MDIR, file_key(p) + ".json")
        old = {}
        if os.path.exists(fn):
            with open(fn, encoding="utf-8") as f:
                old = {x["id"]: x for x in json.load(f)["strings"]}
        out = []
        for x in items:
            y = dict(x, ko=None, status="untranslated", note="")
            if x["id"] in old:
                o = old[x["id"]]
                y.update(ko=o.get("ko"), status=o.get("status", "untranslated"), note=o.get("note", ""))
                if "src" in o and o["src"] != x["src"]:
                    bad += 1
                    y["status"] = "decision"
                    y["note"] = (y["note"] + f" [원문 변경: 이전 {o['src']!r}]").strip()
            out.append(y)
        missing = set(old) - {x["id"] for x in items}
        bad += len(missing)
        if check:
            if missing or any(old.get(x["id"], {}).get("src", x["src"]) != x["src"] or x["id"] not in old for x in items):
                print(f"{p}: 자산이 원본 추출과 다름")
            continue
        os.makedirs(MDIR, exist_ok=True)
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(srctext.strip({"file": p, "strings": out}), f, ensure_ascii=False, indent=1)
        print(f"{p}: {len(out)}개 -> {os.path.relpath(fn, ROOT)}")
    return 1 if check and bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
