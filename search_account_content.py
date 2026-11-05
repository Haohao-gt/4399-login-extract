# -*- coding: utf-8 -*-
"""按内容查找 4399 票据出现的位置（换机/换号后排查"登录态落到哪个文件"）。

用法：
    python search_account_content.py --needles <账号名> <uid> Xauth Pauth
    python search_account_content.py                      # 只搜字段名 Xauth/Pauth/Uauth
"""
import os
import argparse
from config import CFG, WILDS_DIR, SSJJ_DIR

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))

SKIP_EXT = {".dll", ".exe", ".png", ".jpg", ".jpeg", ".pak", ".zip", ".rar", ".7z",
            ".mp4", ".mp3", ".ttf", ".otf", ".bin", ".so", ".dylib", ".pyc"}
MAXSIZE = 8 * 1024 * 1024


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--needles", nargs="*", default=["Xauth", "Pauth", "Uauth"])
    ap.add_argument("--depth", type=int, default=7)
    args = ap.parse_args()
    needles = [n.encode() for n in args.needles]

    roots = [
        LOCALAPPDATA,
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
        os.path.join(os.path.expanduser("~"), "AppData", "LocalLow"),
        r"C:\ProgramData",
        WILDS_DIR,
        os.path.dirname(SSJJ_DIR) if SSJJ_DIR else "",
    ]
    roots = [r for r in roots if r and os.path.isdir(r)]

    hits = []
    for r in roots:
        base = r.count(os.sep)
        for dp, dns, fns in os.walk(r):
            if dp.count(os.sep) - base > args.depth:
                dns[:] = []
                continue
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.splitext(fn)[1].lower() in SKIP_EXT:
                    continue
                try:
                    if os.path.getsize(p) > MAXSIZE:
                        continue
                    data = open(p, "rb").read()
                except Exception:
                    continue
                found = [n.decode() for n in needles if n in data]
                if found:
                    hits.append((p, found, len(data)))

    print("命中文件:", len(hits))
    for p, f, n in hits:
        print(f"  {p}  ({n} 字节) -> {','.join(f)}")


if __name__ == "__main__":
    main()
