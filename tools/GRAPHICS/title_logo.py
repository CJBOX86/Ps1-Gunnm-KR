"""타이틀 화면(DATA/TITLE.BIN 0xC의 640x480 16bpp TIM) 로고의 한자를 한글로 다시 그린다.

  銃夢 -> 총몽 (Black Han Sans, 빨강 그라데이션 + 검은 테두리 + 노란·주황 외곽선)
  -火星の記憶- -> -화성의 기억- (나눔명조 ExtraBold, 진한 빨강)

순서: 원래 글자 자리(채도 높은 픽셀 + 주변 테두리)를 지우고 같은 줄의 양옆 픽셀로 가로 보간해
배경·금속 바를 메운 뒤 새 글자를 얹는다. 원본에서 바뀌지 않은 픽셀은 16bit 값(STP 비트 포함)을 그대로 둔다.

미리보기: python tools/GRAPHICS/title_logo.py  -> work/title_kr.png
"""
import os
import struct
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TIM_OFF = 0xC
W, H = 640, 480
FONT_BIG = "assets/fonts/sources/blackhansans/BlackHanSans-Regular.ttf"
FONT_SUB = "assets/fonts/sources/nanummyeongjo/NanumMyeongjo-ExtraBold.ttf"
# (글자, 지울 영역, 새 글자 상자)
BIG = [("총", (84, 38, 258, 234), (98, 52, 248, 224)),
       ("몽", (386, 38, 552, 234), (398, 52, 530, 224))]
SUB_ERASE = (244, 147, 398, 178)
SUB_BOX = (250, 150, 392, 175)
SUB_TEXT = "－화성의 기억－"


def decode(px):
    im = Image.new("RGB", (W, H))
    im.putdata([((v & 31) << 3, (v >> 5 & 31) << 3, (v >> 10 & 31) << 3) for v in px])
    return im


def logo_mask(im, box, dilate=4):
    """상자 안의 채도 높은 픽셀(빨강·노랑·주황)과 그 둘레(검은 테두리)를 지울 영역으로"""
    m = Image.new("L", (W, H), 0)
    x0, y0, x1, y1 = box
    px = im.load()
    mp = m.load()
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if max(r, g, b) - min(r, g, b) > 48 and r > b + 30:
                mp[x, y] = 255
    m = m.filter(ImageFilter.MaxFilter(dilate * 2 + 1))
    # 상자 밖으로 번진 것은 버린다
    clip = Image.new("L", (W, H), 0)
    ImageDraw.Draw(clip).rectangle(box, fill=255)
    return ImageChops.multiply(m, clip)


def fill_rows(im, mask):
    """마스크 픽셀을 같은 줄의 왼쪽·오른쪽 가장 가까운 비마스크 픽셀 사이 선형 보간으로 채운다"""
    px, mp = im.load(), mask.load()
    for y in range(H):
        x = 0
        while x < W:
            if not mp[x, y]:
                x += 1
                continue
            s = x
            while x < W and mp[x, y]:
                x += 1
            a = px[s - 1, y] if s > 0 else px[x, y]
            b = px[x, y] if x < W else a
            n = x - s + 1
            for i in range(s, x):
                t = (i - s + 1) / n
                px[i, y] = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
    return im


def glyph_mask(ch, font_path, box):
    """글자 하나를 상자 크기에 꽉 차게(가로·세로 따로 늘림) 그린 마스크"""
    f = ImageFont.truetype(os.path.join(ROOT, font_path), 400)
    g = Image.new("L", (520, 520), 0)
    ImageDraw.Draw(g).text((40, 20), ch, font=f, fill=255)
    g = g.crop(g.getbbox())
    bw, bh = box[2] - box[0], box[3] - box[1]
    g = g.resize((bw, bh), Image.LANCZOS)
    m = Image.new("L", (W, H), 0)
    m.paste(g, box[:2])
    return m


def vgrad(box, top, bottom):
    x0, y0, x1, y1 = box
    im = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(im)
    for y in range(y0, y1 + 1):
        t = (y - y0) / max(1, y1 - y0)
        d.line([(0, y), (W, y)], fill=tuple(int(top[k] + (bottom[k] - top[k]) * t) for k in range(3)))
    return im


def draw_big(im, ch, box):
    fill = glyph_mask(ch, FONT_BIG, box)
    black = fill.filter(ImageFilter.MaxFilter(5))
    glow = black.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(1.2))
    # 노란 외곽선(위 밝은 노랑 -> 아래 주황)
    im.paste(vgrad(box, (255, 236, 120), (240, 150, 30)), (0, 0), glow)
    im.paste((20, 6, 4), (0, 0), black)
    # 빨강 채움(위 밝은 빨강 -> 아래 진한 빨강), 왼쪽 위 살짝 밝게
    im.paste(vgrad(box, (240, 40, 24), (150, 8, 8)), (0, 0), fill)
    hi = ImageChops.subtract(fill, fill.transform(fill.size, Image.AFFINE, (1, 0, -3, 0, 1, -3)))
    im.paste((255, 120, 90), (0, 0), hi.point(lambda v: v // 3))


def draw_sub(im):
    f = ImageFont.truetype(os.path.join(ROOT, FONT_SUB), 60)
    g = Image.new("L", (900, 120), 0)
    ImageDraw.Draw(g).text((10, 10), SUB_TEXT, font=f, fill=255)
    g = g.crop(g.getbbox())
    bw, bh = SUB_BOX[2] - SUB_BOX[0], SUB_BOX[3] - SUB_BOX[1]
    g = g.resize((bw, bh), Image.LANCZOS)
    m = Image.new("L", (W, H), 0)
    m.paste(g, SUB_BOX[:2])
    shadow = m.transform(m.size, Image.AFFINE, (1, 0, -1, 0, 1, -1))
    im.paste((235, 225, 225), (0, 0), shadow.point(lambda v: v * 2 // 3))
    im.paste((150, 16, 16), (0, 0), m)


def scaled(box, k):
    """상자를 가운데 기준으로 k배"""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    hw, hh = (box[2] - box[0]) * k / 2, (box[3] - box[1]) * k / 2
    return (round(cx - hw), round(cy - hh), round(cx + hw), round(cy + hh))


def draw_credit(im, c):
    """한글화 크레딧 한 줄 (저작권 표기 아래 가운데). c: text, font, size, x, y(글자 아래 기준)"""
    f = ImageFont.truetype(os.path.join(ROOT, c["font"]), c["size"])
    d = ImageDraw.Draw(im)
    d.text((c["x"] + 1, c["y"] + 1), c["text"], font=f, fill=(20, 20, 20), anchor="md")
    d.text((c["x"], c["y"]), c["text"], font=f, fill=(235, 235, 235), anchor="md")


def build(title_bin, scale=1.0, credit=None):
    px = list(struct.unpack_from(f"<{W * H}H", title_bin, TIM_OFF + 20))
    if struct.unpack_from("<IHHHH", title_bin, TIM_OFF + 8)[3:] != (640, 480):
        raise ValueError("TITLE.BIN 형식 불일치")
    orig = decode(px)
    im = orig.copy()
    erase = Image.new("L", (W, H), 0)
    for _, ebox, _ in BIG:
        erase = ImageChops.lighter(erase, logo_mask(orig, ebox))
    sub = logo_mask(orig, SUB_ERASE, dilate=2)
    erase = ImageChops.lighter(erase, sub)
    fill_rows(im, erase)
    for ch, _, box in BIG:
        draw_big(im, ch, scaled(box, scale))
    draw_sub(im)
    if credit:
        draw_credit(im, credit)
    out = bytearray(title_bin)
    nb = im.tobytes()
    new = [nb[i:i + 3] for i in range(0, W * H * 3, 3)]
    ob = orig.tobytes()
    old = [ob[i:i + 3] for i in range(0, W * H * 3, 3)]
    for i, (c, o) in enumerate(zip(new, old)):
        if c == o:
            continue
        v = (c[0] >> 3) | (c[1] >> 3) << 5 | (c[2] >> 3) << 10
        struct.pack_into("<H", out, TIM_OFF + 20 + 2 * i, v if v else 0x8000)  # 0x0000은 투명이라 불투명 검정으로
    return bytes(out), im


def main(argv):
    _TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path[:0] = [os.path.join(_TOOLS, d) for d in sorted(os.listdir(_TOOLS))
                    if d.isupper() and os.path.isdir(os.path.join(_TOOLS, d))]  # tools/ 아래 기능별 폴더
    import psxdisc
    import verify_source
    local = verify_source.local_config()
    disc = psxdisc.Disc(os.path.join(ROOT, local["source_bin"]))
    ents = {e["path"]: e for e in disc.walk()}
    _, im = build(disc.read_file(ents["/DATA/TITLE.BIN;1"]))
    dst = os.path.join(ROOT, "work", "title_kr.png")
    im.save(dst)
    print(dst)


if __name__ == "__main__":
    main(sys.argv)
