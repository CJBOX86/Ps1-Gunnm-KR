"""지원 원본 식별: 크기와 강한 해시를 config/source.json의 프로필과 대조한다.

사용법: python tools/DISC/verify_source.py [image.bin]
경로를 생략하면 config/local.json의 source_bin을 사용한다. 불일치 시 종료 코드 1.
"""
import hashlib
import json
import os
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def local_config():
    p = os.path.join(ROOT, "config", "local.json")
    if not os.path.exists(p):
        raise SystemExit("config/local.json 없음: config/local.example.json을 복사해 경로를 지정하라")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def identify(path):
    sha1, sha256, crc, size = hashlib.sha1(), hashlib.sha256(), 0, 0
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            sha1.update(chunk)
            sha256.update(chunk)
            crc = zlib.crc32(chunk, crc)
            size += len(chunk)
    return {"size": size, "crc32": f"{crc:08x}", "sha1": sha1.hexdigest(), "sha256": sha256.hexdigest()}


def main(argv):
    path = argv[1] if len(argv) > 1 else os.path.join(ROOT, local_config()["source_bin"])
    with open(os.path.join(ROOT, "config", "source.json"), encoding="utf-8") as f:
        profiles = json.load(f)["profiles"]
    got = identify(path)
    for prof in profiles:
        track = prof["tracks"][0]
        if all(track[k] == got[k] for k in ("size", "crc32", "sha1", "sha256")):
            print(json.dumps({"profile": prof["id"], **got}, indent=1))
            return 0
    print(json.dumps({"profile": None, **got}, indent=1))
    print("지원 원본과 일치하지 않음", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
