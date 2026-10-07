"""번역 자산과 원문(일본어 대사) 분리.

저장소의 번역 파일(assets/translation/segments, menu)에는 원문(src)을 두지 않는다 — 원작 대본 전체를
공개 저장소에 올리지 않기 위해서다. 원문은 사용자의 원본 디스크에서 추출해 work/src/(저장소 제외)에
캐시하고, 도구가 읽을 때 줄 ID로 붙인다(attach). 저장할 때는 다시 뗀다(strip).
"""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = os.path.join(ROOT, "work", "src")


def _src_bin():
    import verify_source
    local = verify_source.local_config()
    path = os.path.join(ROOT, local["source_bin"])
    if verify_source.main(["", path]) != 0:
        raise SystemExit("원본 불일치 — config/local.json의 source_bin 확인")
    return path


def _load(name, build):
    fn = os.path.join(CACHE, name)
    if os.path.exists(fn):
        with open(fn, encoding="utf-8") as f:
            return json.load(f)
    data = build(_src_bin())
    save_cache(name, data)
    return data


def save_cache(name, data):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def dialog_map(blocks):
    return {x["id"]: x["src"] for b in blocks for x in b["lines"]}


def menu_map(fresh):
    return {x["id"]: x["src"] for items in fresh.values() for x in items}


def dialog_src():
    import extract_dialog
    return _load("dialog.json", lambda p: dialog_map(extract_dialog.extract(p)))


def menu_src():
    import extract_menu
    return _load("menu.json", lambda p: menu_map(extract_menu.extract(p)))


def attach_lines(lines, src):
    for x in lines:
        if "src" not in x:
            if x["id"] not in src:
                raise SystemExit(f"{x['id']}: 원본 추출 결과에 없는 줄 ID")
            x["src"] = src[x["id"]]


def attach_blocks(blocks, src=None):
    src = src if src is not None else dialog_src()
    for b in blocks:
        attach_lines(b["lines"], src)
    return blocks


def strip(obj):
    """저장용 사본: 줄·문자열의 src 제거"""
    o = copy.deepcopy(obj)
    for b in o.get("blocks", []):
        for x in b["lines"]:
            x.pop("src", None)
    for x in o.get("strings", []):
        x.pop("src", None)
    return o
