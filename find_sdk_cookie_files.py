# -*- coding: utf-8 -*-
"""在 AppData / 游戏目录里找 4399 SDK 的 cookie 文件（Netscape 格式 cookies.dat）。

用法：
    python find_sdk_cookie_files.py
    python find_sdk_cookie_files.py --roots D:\\ E:\\
"""
import os
import argparse
from config import CFG, SSJJ_DIR, WILDS_DIR

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))


def default_roots():
    return [
        os.path.join(os.path.expanduser("~"), "AppData"),
        r"C:\ProgramData",
        WILDS_DIR,
        os.path.dirname(SSJJ_DIR) if SSJJ_DIR else "",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="*", default=None)
    ap.add_argument("--depth", type=int, default=7)
    args = ap.parse_args()

    roots = [r for r in (args.roots or default_roots()) if r and os.path.isdir(r)]
    hits = []
    for r in roots:
        base = r.count(os.sep)
        for dp, dns, fns in os.walk(r):
            if dp.count(os.sep) - base > args.depth:
                dns[:] = []
                continue
            for fn in fns:
                if fn.lower() in ("cookies.dat", "cookies.txt") or "pc4399sdk" in dp.lower():
                    hits.append(os.path.join(dp, fn))

    print("候选:", len(hits))
    for p in hits:
        try:
            data = open(p, "rb").read(4000)
        except Exception as e:
            print("ERR", p, e)
            continue
        txt = data.decode("utf-8", "ignore")
        if "4399" in txt or "Netscape" in txt:
            print("=" * 60)
            print(p, len(data))
            print(txt[:900])
    if not hits:
        print("未找到。用 --roots 指定游戏所在盘符再试。")


if __name__ == "__main__":
    main()
