"""대사 평문(SJIS 디코드 결과) <-> 번역 자산 표기 변환과 제어 토큰 검사.

자산 표기:
  - 줄바꿈 `\\\\`(0x5C 두 개)  -> 실제 줄바꿈 문자 "\n"
  - 페이지 넘김 `@@`           -> "{page}"
  - 그 밖의 제어 코드           -> "{코드}" 예: {WS2501} {b3} {br} {WP-200+050} {[1}
  - 나머지는 표시 문자 그대로
제어 코드 문법은 원본 대사 19,226개 전체에서 남는 ASCII 없이 맞는 것을 확인했다
(research/analysis/2026-10-06-translation-format.md).
"""
import re

CODE = (r"WS\d{4}|WP[+-]\d{3}[+-]\d{3}|BKC\d{3}|BKA[0-9a-f]|BL\d{4}|FR[CA][0-9a-f]|CSA\d"
        r"|i\d{3}|c[0-9a-f]{3}|w[+-]\d\d|[stanbg][0-9a-z]|\[DD\d|\[\d")
RAW_TOKEN = re.compile(r"\\\\|@@|" + CODE)
ASSET_TOKEN = re.compile(r"\n|\{page\}|\{(" + CODE + r")\}")
LAYOUT = ("\n", "{page}")   # 번역문에서 자유롭게 바꿀 수 있는 토큰


def to_asset(plain):
    """원본 평문 -> 자산 표기. 제어 코드가 아닌 ASCII가 있으면 ValueError."""
    out, pos = [], 0
    for m in RAW_TOKEN.finditer(plain):
        out.append(_check_text(plain[pos:m.start()]))
        t = m.group()
        out.append("\n" if t == "\\\\" else "{page}" if t == "@@" else "{" + t + "}")
        pos = m.end()
    out.append(_check_text(plain[pos:]))
    return "".join(out)


def _check_text(s):
    if re.search(r"[\x00-\x7f]", s):
        raise ValueError(f"제어 코드가 아닌 ASCII: {s!r}")
    return s


def split(asset):
    """자산 표기 -> [("tok", 원시 코드) | ("text", 문자열)]"""
    out, pos = [], 0
    for m in ASSET_TOKEN.finditer(asset):
        if m.start() > pos:
            out.append(("text", asset[pos:m.start()]))
        t = m.group()
        out.append(("tok", "\\\\" if t == "\n" else "@@" if t == "{page}" else m.group(1)))
        pos = m.end()
    if pos < len(asset):
        out.append(("text", asset[pos:]))
    for kind, v in out:
        if kind == "text" and ("{" in v or "}" in v):
            raise ValueError(f"알 수 없는 토큰: {v!r}")
    return out


def structural_tokens(asset):
    """배치용(줄바꿈·페이지)을 뺀 제어 코드 순서."""
    return [v for k, v in split(asset) if k == "tok" and v not in ("\\\\", "@@")]


def check_translation(src, ko):
    """번역문이 원문의 구조 제어 코드를 같은 순서로 유지하는지 검사. 문제 목록을 반환."""
    try:
        a, b = structural_tokens(src), structural_tokens(ko)
    except ValueError as e:
        return [str(e)]
    if a != b:
        return [f"제어 코드 불일치: 원문 {a} / 번역 {b}"]
    return []


# 번역문 편의 변환: 폰트에 없는 흔한 문장부호를 폰트에 있는 글자로
PUNCT = {",": "、", "，": "、", "･": "・", "…": "・・・", "‥": "・・", "·": "・"}


def normalize_ko(asset):
    """번역문 편의 변환: 문장부호 치환 후 표시 문자 중 반각 ASCII(공백 제외)를 전각으로 바꾼다."""
    out = []
    for kind, v in split(asset):
        if kind == "tok":
            out.append({"\\\\": "\n", "@@": "{page}"}.get(v, "{" + v + "}"))
        else:
            v = "".join(PUNCT.get(c, c) for c in v)
            out.append("".join(chr(ord(c) + 0xFEE0) if "!" <= c <= "~" else c for c in v))
    return "".join(out)


def is_hangul(c):
    return "가" <= c <= "힣"


def encode(asset, charmap, space=None):
    """자산 표기 -> 게임 평문 bytes (XOR 전). charmap: 한글 등 대체 문자 -> SJIS 2byte.
    space: 띄어쓰기(반각 ' ')에 쓸 2byte 코드. None이면 전각 공백."""
    out = bytearray()
    for kind, v in split(asset):
        if kind == "tok":
            out += v.encode("ascii")
            continue
        for ch in v:
            if ch in charmap:
                out += charmap[ch]
            elif ch == " ":
                out += space or "　".encode("cp932")
            else:
                b = ch.encode("cp932")
                if len(b) != 2:
                    raise ValueError(f"인코딩할 수 없는 문자: {ch!r}")
                out += b
    if len(out) % 2:
        raise ValueError("본문 길이가 홀수")
    return bytes(out)


def visual_lines(asset):
    """줄바꿈·페이지로 나눈 각 줄의 표시 칸 수 (전각 1칸, 공백도 1칸)."""
    out, cur = [], 0
    for kind, v in split(asset):
        # w±NN도 줄을 바꾼다 (층 선택창: 9칸 질문 뒤 {w+02} 다음에 선택지가 새 줄로 나옴)
        if kind == "tok" and (v in ("\\\\", "@@") or re.fullmatch(r"w[+-]\d\d", v)):
            out.append(cur)
            cur = 0
        elif kind == "text":
            cur += len(v)
    out.append(cur)
    return out


def window_width(asset, default=25):
    """{WSwwhh} 창 코드의 너비. 없으면 기본값."""
    m = re.search(r"\{WS(\d\d)\d\d\}", asset)
    return int(m.group(1)) if m else default


def page_heights(asset):
    """페이지({page})별 줄 수. 줄바꿈과 w±NN이 줄을 늘린다."""
    out, cur = [], 1
    for kind, v in split(asset):
        if kind == "tok" and v == "@@":
            out.append(cur)
            cur = 1
        elif kind == "tok" and (v == "\\\\" or re.fullmatch(r"w[+-]\d\d", v)):
            cur += 1
    out.append(cur)
    return out


def window_height(asset, default=3):
    """{WSwwhh} 창 코드의 높이. 없으면 가장 흔한 3줄
    (창 코드 없는 원문은 한 줄로 길게 쓰고 자동 줄바꿈에 맡긴다)."""
    m = re.search(r"\{WS\d\d(\d\d)\}", asset)
    return int(m.group(1)) if m else default


def display_chars(asset, halfwidth_space=False):
    """글리프가 필요한 문자 집합 (제어 토큰 제외). 띄어쓰기는 반각 공백이면 글리프 불필요, 아니면 전각 공백."""
    s = set()
    for kind, v in split(asset):
        if kind == "text":
            s.update("　" if c == " " else c for c in v if not (c == " " and halfwidth_space))
    return s
