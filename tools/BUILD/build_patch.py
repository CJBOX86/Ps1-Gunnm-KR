"""번역 자산으로 패치 이미지·xdelta를 만든다 (개발 빌드).

사용법:
  python tools/BUILD/build_patch.py [config/build.json]

순서:
  1. 원본 식별, 번역 자산 모집단을 원본 추출 결과와 대조 (tools/TEXT/extract_dialog.py)
  2. 줄마다 사용할 문장 선택: 번역문(ko)이 있고 상태가 정책(use_statuses)에 들면 번역문, 아니면 원문.
     ref 줄은 참조한 줄의 선택을 따른다
  3. 모든 번역문 검사: 구조 제어 코드 순서, 폰트에 없는 문자
  4. 한글 음절 -> SJIS 코드 배정: 어떤 KNJ에도 없는 JIS 한자 코드를 하나씩 받는다 (모든 폰트 공통)
  5. 블록이 쓸 수 있는 폰트(font_candidates)마다 KNJ에 한글 코드를 넣어 정렬하고 TIM을 다시 배치한다.
     1,444자를 넘으면 대사·메뉴(NOR/*.E, 실행 파일 SJIS 문자열)가 쓰지 않는 일본어 글자부터 뺀다.
     게임은 KNJ를 0000 종료까지 세고(0x80027C94) 이진 탐색한다. KNJ 버퍼 0x8013E000은 약 4KB
  6. 대사 블록을 다시 만들어 LDP를 교체
  6c. 그래픽 텍스트(config/graphics.json): 그림 속 일본어 TIM을 같은 크기·팔레트로 한글로 다시 그림
  6b. 메뉴 문자열(assets/translation/menu, tools/TEXT/extract_menu.py)을 제자리 교체. 메뉴는 어느 장에서나
      열릴 수 있어 메뉴 한글은 모든 폰트에 넣는다. 띄어쓰기는 전각 공백(메뉴 렌더러에 반각 패치 미확인)
  7. tools/DISC/build_disc.py로 이미지·xdelta 생성, work/out/<name>.report.json 기록
"""
import hashlib
import json
import os
import re
import struct
import sys

_TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
import build_disc  # noqa: E402
import dialog_text as dt  # noqa: E402
import extract_dialog  # noqa: E402
import gfx_text  # noqa: E402
import title_logo  # noqa: E402
import ldp  # noqa: E402
import srctext  # noqa: E402
import psxdisc  # noqa: E402
import verify_source  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CELL, PER_ROW = 13, 19


def load_assets():
    tdir = extract_dialog.TDIR
    with open(os.path.join(tdir, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    blocks = []
    for name in index["segments"]:
        with open(os.path.join(tdir, "segments", name + ".json"), encoding="utf-8") as f:
            blocks += json.load(f)["blocks"]
    return index, blocks


def choose_texts(blocks, use):
    lines = {x["id"]: x for b in blocks for x in b["lines"]}
    if len(lines) != sum(len(b["lines"]) for b in blocks):
        raise SystemExit("줄 ID 중복")
    errors, chosen = [], {}
    for lid, x in lines.items():
        if x.get("status", "untranslated") not in dict.fromkeys(("untranslated", "draft", "review", "decision", "done")):
            errors.append(f"{lid}: 알 수 없는 상태 {x.get('status')}")
        if x.get("ko") is not None:
            for e in dt.check_translation(x["src"], x["ko"]):
                errors.append(f"{lid}: {e}")
    for lid, x in lines.items():
        y = lines[x["ref"]] if "ref" in x else x
        if y.get("ko") is not None and y.get("status") in use:
            chosen[lid] = (dt.normalize_ko(y["ko"]), True)
        else:
            chosen[lid] = (x["src"], False)
    return chosen, errors


MENU_CODES = re.compile(r"\{(WS\d{4}|BL\d{4})\}")


def load_menu(use, menu_src=None):
    """메뉴 자산 -> [(항목, 사용할 자산 표기, 번역 여부)], 오류 목록.
    창 코드(WS·BL)만 원문과 같은 순서를 요구한다. g코드(글자 간격 조정)는 번역문에서 자유."""
    mdir = os.path.join(extract_dialog.TDIR, "menu")
    out, errors = [], []
    if not os.path.isdir(mdir):
        return out, errors
    for fn in sorted(os.listdir(mdir)):
        with open(os.path.join(mdir, fn), encoding="utf-8") as f:
            j = json.load(f)
        for x in j["strings"]:
            x = dict(x, file=j["file"])
            srctext.attach_lines([x], menu_src or srctext.menu_src())
            if x.get("ko") is not None and x.get("status") in use:
                ko = dt.normalize_ko(x["ko"])
                try:
                    dt.split(ko)
                except ValueError as e:
                    errors.append(f"{x['id']}: {e}")
                    continue
                if MENU_CODES.findall(ko) != MENU_CODES.findall(x["src"]):
                    errors.append(f"{x['id']}: 창 코드 불일치")
                out.append((x, ko, True))
            else:
                out.append((x, x["src"], False))
    return out, errors


def translated_any(chosen):
    return any(is_ko for _, is_ko in chosen.values())


def layout_warnings(chosen):
    """번역문 줄이 창 너비를 넘으면 게임이 글자 단위로 자동 줄바꿈해 단어가 잘린다 (사람 검토 대상)."""
    out = []
    for lid, (text, is_ko) in chosen.items():
        if not is_ko:
            continue
        w = dt.window_width(text)
        over = [n for n in dt.visual_lines(text) if n > w]
        if over:
            out.append(f"{lid}: 줄 길이 {max(over)}칸 > 창 너비 {w}칸")
    return out


def protected_chars(disc, ents):
    """대사 밖 문자열(메뉴 등)이 쓰는 글자 — 휴리스틱.
    NOR/*.E·실행 파일에서 0으로 끝나는 SJIS 연속열 중 가나가 섞였거나 3글자 이상인 것만 문자열로 본다
    (아무 바이트 쌍이나 한자로 읽히는 것을 줄이기 위해. 이전 기준 대비 K00에서 448 -> 371자)."""
    s = set()
    for p, e in ents.items():
        if not (p.startswith("/NOR/") or p.startswith("/SLPS_")) or e["interleaved"]:
            continue
        d = disc.read_file(e)
        for m in re.finditer(rb"(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){2,}\x00", d):
            try:
                t = m.group()[:-1].decode("cp932")
            except UnicodeDecodeError:
                continue
            if re.search(r"[぀-ヿ]", t) or len(t) >= 3:
                s.update(t)
    return s


# 18행 x 19셀 x 4플레인 = TIM 234행. 실제로 쓰이는 원본 중 가장 큰 K08과 같은 크기까지만 쓴다.
# TIM 임시 버퍼 0x80193800 뒤(234행 끝 0x8019ACA0 이후)에는 다른 데이터가 있어 그 이상은 미검증.
# (247행 K04는 폰트 이름 표 0x8008F350에 없어 게임이 불러오지 않는다)
MAX_GLYPHS = 1368


def sjis_value(c):
    b = c.encode("cp932")
    return b[0] << 8 | b[1]


def hangul_pool(fonts, protected):
    """한글에 배정할 SJIS 코드: 어떤 KNJ에도 없는 JIS 한자 (88-9F, E0-EA 행)."""
    used = set().union(*(set(v) for v in fonts.values())) | protected
    pool = []
    for lead in list(range(0x88, 0xA0)) + list(range(0xE0, 0xEB)):
        for trail in list(range(0x40, 0x7F)) + list(range(0x80, 0xFD)):
            try:
                c = bytes([lead, trail]).decode("cp932")
            except UnicodeDecodeError:
                continue
            if len(c) == 1 and "一" <= c <= "鿿" and c not in used:
                pool.append(bytes([lead, trail]))
    return pool


FONT_ORDER = ["K00", "K01", "K02", "K03", "K04_0", "K04_1", "K04_2", "K05", "K06", "K07", "K08", "K99"]


def target_fonts(block, mode):
    """블록 글자를 공급할 폰트. all = 후보 전부(안전, 용량 큼), chapter = 폰트 표 순서상 첫 후보 하나(개발용 추정)."""
    c = block["font_candidates"]
    if mode == "chapter" and c:
        return [min(c, key=FONT_ORDER.index)]
    return c


def plan_fonts(blocks, chosen, fonts, protected, halfwidth_space=False, mode="all", every=()):
    """폰트별 새 글자 목록과 한글 코드 배정. every: 모든 폰트에 넣을 글자(메뉴).
    반환: charmap {한글: SJIS 2byte}, layout {K: [(SJIS 2byte, 원래 KNJ 번호 | 한글)]}, usage, errors"""
    needs = {k: set(every) for k in fonts}
    errors = []
    for k in fonts:
        missing = {c for c in every if not dt.is_hangul(c) and c not in fonts[k]}
        if missing:
            errors.append(f"메뉴: {k}에 없는 문자 {''.join(sorted(missing))}")
    for b in blocks:
        b = dict(b, font_candidates=target_fonts(b, mode))
        chars = set()
        for x in b["lines"]:
            chars |= dt.display_chars(chosen[x["id"]][0], halfwidth_space)
        hangul = {c for c in chars if dt.is_hangul(c)}
        if not b["font_candidates"]:
            if hangul:
                errors.append(f"{b['id']}: 쓸 수 있는 폰트가 없는 블록에 한글")
            continue
        for k in b["font_candidates"]:
            missing = {c for c in chars - hangul if c not in fonts[k]}
            if missing:
                errors.append(f"{b['id']}: {k}에 없는 문자 {''.join(sorted(missing))}")
            needs[k] |= chars
    syllables = sorted({c for s in needs.values() for c in s if dt.is_hangul(c)})
    pool = hangul_pool(fonts, protected)
    if len(syllables) > len(pool):
        errors.append(f"한글 음절 {len(syllables)}개 > 배정 가능한 코드 {len(pool)}개")
        return {}, {}, {}, errors
    charmap = dict(zip(syllables, pool))
    layout, usage = {}, {}
    for k, chars in fonts.items():
        hs = sorted(c for c in needs[k] if dt.is_hangul(c))
        if not hs:
            continue
        keep = list(range(len(chars)))
        over = len(keep) + len(hs) - MAX_GLYPHS
        dropped = 0
        if over > 0:
            # 대사가 더 쓰지 않고 메뉴에서도 보이지 않는 한자·가나부터 뺀다 (코드 큰 순)
            cand = [i for i in keep if chars[i] not in needs[k] and chars[i] not in protected
                    and ("぀" <= chars[i] <= "ヿ" or "一" <= chars[i] <= "鿿")]
            cand.sort(key=lambda i: -sjis_value(chars[i]))
            if len(cand) < over:
                errors.append(f"{k}: 글자 {len(chars) + len(hs)}개 > {MAX_GLYPHS}, 뺄 수 있는 글자 {len(cand)}개")
                continue
            drop = set(cand[:over])
            keep = [i for i in keep if i not in drop]
            dropped = over
        entries = [(chars[i].encode("cp932"), i) for i in keep] + [(charmap[h], h) for h in hs]
        entries.sort(key=lambda e: e[0][0] << 8 | e[0][1])
        layout[k] = entries
        usage[k] = {"glyphs": len(entries), "hangul": len(hs), "dropped_japanese": dropped,
                    "spare": MAX_GLYPHS - len(entries)}
    return charmap, layout, usage, errors


def tim_planes(tim):
    o = 8 + struct.unpack_from("<I", tim, 8)[0]
    _, x, y, w, h = struct.unpack_from("<IHHHH", tim, o)
    return o, w, h


def glyph_bits(tim, idx):
    o, w, _ = tim_planes(tim)
    pix, row = o + 12, w * 2
    plane, cell = idx % 4, idx // 4
    gx, gy = (cell % PER_ROW) * CELL, (cell // PER_ROW) * CELL
    return [[(tim[pix + (gy + y) * row + (gx + x) // 2] >> (4 * ((gx + x) % 2) + plane)) & 1
             for x in range(CELL)] for y in range(CELL)]


def render(ch, font):
    from PIL import Image, ImageDraw
    im = Image.new("1", (CELL, CELL), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    d.text((0, 0), ch, font=font, fill=1)
    bits = [[1 if im.getpixel((x, y)) else 0 for x in range(CELL)] for y in range(CELL)]
    if not any(map(any, bits)):
        raise SystemExit(f"빈 글리프: {ch}")
    return bits


def build_font(knj_orig, tim_orig, entries, font):
    """새 KNJ·TIM bytes. entries: [(SJIS 2byte, 원래 번호 | 한글 문자)] 정렬 완료."""
    n = len(entries)
    knj = b"".join(bytes([c[1], c[0]]) for c, _ in entries) + b"\0\0"
    knj += b"\0" * (-len(knj) % 4)
    o, w, _ = tim_planes(tim_orig)
    rows = -(-(-(-n // 4)) // PER_ROW) * CELL
    pix = bytearray(w * 2 * rows)
    for idx, (_, src) in enumerate(entries):
        bits = render(src, font) if isinstance(src, str) else glyph_bits(tim_orig, src)
        plane, cell = idx % 4, idx // 4
        gx, gy = (cell % PER_ROW) * CELL, (cell // PER_ROW) * CELL
        for y in range(CELL):
            for x in range(CELL):
                if bits[y][x]:
                    pix[(gy + y) * w * 2 + (gx + x) // 2] |= 1 << (4 * ((gx + x) % 2) + plane)
    head = bytearray(tim_orig[:o + 12])
    struct.pack_into("<I", head, o, 12 + len(pix))
    struct.pack_into("<H", head, o + 10, rows)
    tim = bytes(head) + bytes(pix)
    # 자가 검사: 옮긴 원래 글리프는 원본과 픽셀 단위로 같아야 한다
    for idx, (_, src) in enumerate(entries):
        if not isinstance(src, str) and glyph_bits(tim, idx) != glyph_bits(tim_orig, src):
            raise SystemExit(f"글리프 이동 검증 실패: 원래 번호 {src} -> {idx}")
    return knj, tim


def apply_exe_patches(paths, disc, ents):
    """기계어 패치: 모든 단어의 원래 값을 확인한 뒤 함께 적용한다. 반환 {파일: bytes}, 공백 코드"""
    out, space = {}, None
    for rel in paths:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            pt = json.load(f)
        fp = pt["file"]
        data = bytearray(out.get(fp) or disc.read_file(ents[fp]))
        t_addr, base = int(pt["load"]["t_addr"], 16), int(pt["load"]["file_offset"], 16)
        if struct.unpack_from("<I", data, 0x18)[0] != t_addr:
            raise SystemExit(f"{pt['id']}: 실행 파일 적재 주소 불일치")
        for w in pt["words"]:
            off = int(w["addr"], 16) - t_addr + base
            cur = struct.unpack_from("<I", data, off)[0]
            if cur != int(w["orig"], 16):
                raise SystemExit(f"{pt['id']} {w['addr']}: 원래 값 {cur:08x} != 기대 {w['orig']}")
        for w in pt["words"]:
            struct.pack_into("<I", data, int(w["addr"], 16) - t_addr + base, int(w["new"], 16))
        out[fp] = bytes(data)
        if pt.get("space_code"):
            space = bytes.fromhex(pt["space_code"])
    return out, space


def main(argv):
    cfg_path = argv[1] if len(argv) > 1 else os.path.join(ROOT, "config", "build.json")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    local = verify_source.local_config()
    src_bin = os.path.join(ROOT, local["source_bin"])
    if verify_source.main(["", src_bin]) != 0:
        raise SystemExit("원본 불일치")
    index, blocks = load_assets()
    fresh = extract_dialog.extract(src_bin)
    if extract_dialog.population_hash(fresh) != index["population"]["sha256"]:
        raise SystemExit("번역 자산 모집단이 원본 추출과 다름: tools/TEXT/extract_dialog.py로 갱신")
    fresh_src = srctext.dialog_map(fresh)
    srctext.save_cache("dialog.json", fresh_src)
    srctext.attach_blocks(blocks, fresh_src)   # 저장소 자산에는 원문이 없다 (tools/TEXT/srctext.py)
    if {x["id"]: x["src"] for b in blocks for x in b["lines"]} != fresh_src:
        raise SystemExit("자산 원문(src)이 원본 추출과 다름")

    chosen, errors = choose_texts(blocks, set(cfg["use_statuses"]))
    import extract_menu
    menu_src = srctext.menu_map(extract_menu.extract(src_bin))
    menu, merr = load_menu(set(cfg["use_statuses"]), menu_src)
    errors += merr
    menu_chars = set().union(set(), *(dt.display_chars(t) for _, t, is_ko in menu if is_ko))
    warnings = layout_warnings(chosen)
    disc = psxdisc.Disc(src_bin)
    ents = {e["path"]: e for e in disc.walk()}
    fonts, knj_files = {}, {}
    usable = set(extract_dialog.loadable_fonts(disc, ents))
    for p, e in ents.items():
        if p.startswith("/TIM/K") and p.endswith(".KNJ;1") and p[5:-6] in usable:
            k = disc.read_file(e)
            n = next(i for i in range(0, len(k), 2) if k[i:i + 2] == b"\0\0") // 2  # 0000 종료 앞까지
            fonts[p[5:-6]] = [bytes([k[2 * i + 1], k[2 * i]]).decode("cp932") for i in range(n)]
            knj_files[p[5:-6]] = p
    protected = protected_chars(disc, ents)
    exe_files, space_code = apply_exe_patches(cfg.get("exe_patches", []), disc, ents)
    mode = cfg.get("font_assignment", "all")
    # 후보 폰트가 없는 블록: 원문 글자가 1~2개만 빠진 폰트가 있으면 그 폰트로 본다.
    # (M5/J/MP601_2는 K07에 「派」, M6/D/MP741_3은 K08에 「縛」 하나가 없다 — 원본 게임의 누락으로 보임)
    near = {}
    for b in blocks:
        if not b["font_candidates"]:
            chars = set().union(*(dt.display_chars(x["src"]) for x in b["lines"]))
            miss, k = min((len(chars - set(f)), k) for k, f in fonts.items())
            if miss <= 2:
                b["font_candidates"] = [k]
                near[b["id"]] = (k, "".join(sorted(chars - set(fonts[k]))))
    if near:
        print(f"원문 글자 일부가 빠진 폰트로 배정한 블록 {len(near)}개: {near}")
    reverted = []
    if cfg.get("revert_on_overflow"):
        # 쓸 수 있는 폰트가 없는 블록(원문에 어느 폰트에도 없는 글자가 있음)은 원문 유지
        for b in blocks:
            if not b["font_candidates"]:
                for x in b["lines"]:
                    if chosen[x["id"]][1]:
                        chosen[x["id"]] = (x["src"], False)
                        reverted.append(x["id"])
    for _ in range(len(fonts) + 1):
        charmap, layout, usage, aerr = plan_fonts(blocks, chosen, fonts, protected, space_code is not None, mode,
                                                  menu_chars)
        over = {e.split(":")[0] for e in aerr if "뺄 수 있는 글자" in e}
        if not over or not cfg.get("revert_on_overflow"):
            break
        # 개발 빌드: 용량을 넘긴 폰트의 블록은 원문으로 되돌린다 (그 장이 번역되면 해소)
        for b in blocks:
            if set(target_fonts(b, mode)) & over:
                for x in b["lines"]:
                    if chosen[x["id"]][1]:
                        chosen[x["id"]] = (x["src"], False)
                        reverted.append(x["id"])
    if reverted:
        print(f"주의: 폰트 용량 초과로 원문으로 되돌린 번역 줄 {len(reverted)}개")
    multi = sum(1 for b in blocks if len(b["font_candidates"]) > 1 and any(chosen[x["id"]][1] for x in b["lines"]))
    errors += aerr
    if errors:
        for e in errors[:50]:
            print("오류:", e)
        raise SystemExit(f"검사 실패 {len(errors)}건")

    menu_ko = sum(1 for m in menu if m[2])
    # 한글 글꼴: build 설정의 채택 글꼴(저장소 안, 해시 고정). 없으면 local.json의 개발용 hangul_font
    gr = cfg["glyph_render"]
    font_path = os.path.join(ROOT, gr["font"]) if gr.get("font") else local.get("hangul_font")
    if not font_path or not os.path.exists(font_path):
        raise SystemExit(f"한글 글꼴 파일이 없음: {font_path}")
    font_sha = hashlib.sha256(open(font_path, "rb").read()).hexdigest()
    if gr.get("font_sha256") and font_sha != gr["font_sha256"]:
        raise SystemExit(f"한글 글꼴 해시 불일치: {font_path}")
    replace = dict(exe_files) if translated_any(chosen) or menu_ko else {}
    if layout:
        from PIL import ImageFont
        font = ImageFont.truetype(font_path, cfg["glyph_render"]["size"])
        for k, entries in layout.items():
            kp, tp = f"/TIM/{k}.KNJ;1", f"/TIM/{k}.TIM;1"
            knj, tim = build_font(disc.read_file(ents[kp]), disc.read_file(ents[tp]), entries, font)
            replace[kp], replace[tp] = knj, tim
    enc_map = dict(charmap)
    # 대사 블록
    translated = 0
    for b in blocks:
        recs, any_ko = [], False
        for x in b["lines"]:
            text, is_ko = chosen[x["id"]]
            any_ko |= is_ko
            translated += is_ko
            recs.append((x["flags"], dt.encode(text, enc_map, space_code)))
        if not any_ko:
            continue
        blk = ldp.build_block(recs)
        for f in b["files"]:
            p = f["path"]
            orig = replace.get(p) or disc.read_file(ents[p])
            if p.endswith(".LDP;1"):
                replace[p] = ldp.replace_last_section(orig, blk)
            else:
                old_size = struct.unpack_from("<I", orig, f["offset"])[0]
                if len(blk) > old_size:
                    raise SystemExit(f"{p}: LDP가 아닌 파일의 블록 확장 미지원 ({old_size} -> {len(blk)})")
                t = bytearray(orig)
                t[f["offset"]: f["offset"] + len(blk)] = blk
                replace[p] = bytes(t)
    # 메뉴 문자열 (제자리 교체)
    for x, text, is_ko in menu:
        if not is_ko:
            continue
        p = x["file"]
        data = bytearray(replace.get(p) or disc.read_file(ents[p]))
        o = x["offset"]
        old = dt.encode(x["src"], {})
        if data[o:o + len(old) + 1] != old + b"\0":
            raise SystemExit(f"{x['id']}: 원래 문자열 위치 불일치")
        if any(data[o + len(old) + 1:o + x["slot"] + 1]):
            raise SystemExit(f"{x['id']}: slot 안에 0이 아닌 byte")
        b = dt.encode(text, enc_map)
        if len(b) > x["slot"]:
            errors.append(f"{x['id']}: {len(b)} byte > slot {x['slot']}")
            continue
        data[o:o + x["slot"] + 1] = b + b"\0" * (x["slot"] + 1 - len(b))
        replace[p] = bytes(data)
    # 그래픽 텍스트 (config/graphics.json, tools/GRAPHICS/gfx_text.py)
    gfx_cfg = gfx_text.load_config(ROOT)
    for fp, sha in gfx_cfg.get("fonts", {}).items():
        if hashlib.sha256(open(os.path.join(ROOT, fp), "rb").read()).hexdigest() != sha:
            errors.append(f"그래픽 글꼴 해시 불일치: {fp}")
    for spec in gfx_cfg["images"]:
        replace[spec["file"]] = gfx_text.build_tim(disc.read_file(ents[spec["file"]]), spec, ROOT)
    if gfx_cfg.get("title_logo"):
        tf = gfx_cfg["title_logo"]["file"]
        replace[tf] = title_logo.build(disc.read_file(ents[tf]), gfx_cfg["title_logo"].get("scale", 1.0),
                                       gfx_cfg["title_logo"].get("credit"))[0]
    if errors:
        for e in errors[:50]:
            print("오류:", e)
        raise SystemExit(f"검사 실패 {len(errors)}건")
    for p in list(replace):
        if replace[p] == disc.read_file(ents[p]):
            del replace[p]

    out_dir = os.path.join(ROOT, cfg.get("out_dir", "work/out"))
    stage = os.path.join(out_dir, cfg["name"] + ".files")
    os.makedirs(stage, exist_ok=True)
    man = {"name": cfg["name"], "replace": {}}
    for p, data in replace.items():
        fn = p.strip("/").replace("/", "_").split(";")[0]
        with open(os.path.join(stage, fn), "wb") as f:
            f.write(data)
        man["replace"][p] = os.path.join(cfg["name"] + ".files", fn)
    man_path = os.path.join(out_dir, cfg["name"] + ".manifest.json")
    with open(man_path, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    report = {
        "config": cfg,
        "population": index["population"],
        "translated_lines_used": translated,
        "menu_strings_translated": menu_ko,
        "graphics_replaced": [g["file"] for g in gfx_cfg["images"]],
        "layout_warnings": warnings,
        "font_assignment": mode,
        "reverted_for_capacity": reverted,
        "translated_blocks_with_multiple_font_candidates": multi,
        "hangul_syllables": len(charmap),
        "charmap": {k: v.hex() for k, v in sorted(charmap.items())},
        "font_usage": usage,
        "replaced_files": sorted(replace),
        "glyph_font": {"path": os.path.relpath(font_path, ROOT).replace(os.sep, "/"), "sha256": font_sha},
    }
    with open(os.path.join(out_dir, cfg["name"] + ".report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"메뉴 문자열 {menu_ko}개 번역")
    print(f"번역 줄 {translated}, 한글 음절 {len(charmap)}, 교체 파일 {len(replace)}, 줄 길이 경고 {len(warnings)}")
    if mode == "chapter" and multi:
        print(f"주의: 폰트 배정 chapter 모드 — 후보가 여러 개인 번역 블록 {multi}개는 다른 폰트로 표시되면 한글이 깨질 수 있음")
    for w in warnings[:20]:
        print("경고:", w)
    if not replace:
        print("바뀐 파일 없음 — 이미지를 만들지 않음")
        return 0
    return build_disc.main(["", man_path, out_dir])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
