# -*- coding: utf-8 -*-
"""全盘扫描：找出所有含 4399 域名的 Cookie 库并打印票据，同时可用于核对"登录态到底存在哪"。

用法：
    python scan_all_4399_stores.py                 # 扫 AppData + 程序目录
    python scan_all_4399_stores.py --roots C:\\ D:\\
"""
import os
import sys
import sqlite3
import shutil
import tempfile
import argparse

from config import WILDS_DIR, SSJJ_DIR, CFG

LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))


def default_roots():
    return [
        LOCALAPPDATA,
        os.path.join(os.path.expanduser("~"), "AppData", "Roaming"),
        os.path.join(os.path.expanduser("~"), "AppData", "LocalLow"),
        r"C:\ProgramData",
        r"C:\Program Files",
        r"C:\Program Files (x86)",
        os.path.dirname(SSJJ_DIR) if SSJJ_DIR else "",
        WILDS_DIR,
    ]


def probe(path):
    """复制到临时文件后只读打开，避免锁库。"""
    tmp = os.path.join(tempfile.gettempdir(), "ck_probe_db")
    shutil.copy2(path, tmp)
    con = sqlite3.connect("file:" + tmp + "?mode=ro&immutable=1", uri=True)
    con.text_factory = bytes
    cols = [c[1].decode("utf-8", "ignore") if isinstance(c[1], bytes) else c[1]
            for c in con.execute("PRAGMA table_info(cookies)")]
    if "host_key" not in cols:
        con.close()
        return None
    rows = list(con.execute("SELECT host_key,name,value,encrypted_value FROM cookies"))
    con.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="*", default=None)
    ap.add_argument("--depth", type=int, default=6)
    args = ap.parse_args()

    roots = [r for r in (args.roots or default_roots()) if r and os.path.isdir(r)]
    cands = []
    for r in roots:
        base = r.count(os.sep)
        for dp, dns, fns in os.walk(r):
            if dp.count(os.sep) - base > args.depth:
                dns[:] = []
                continue
            for fn in fns:
                if fn == "Cookies":
                    cands.append(os.path.join(dp, fn))

    print("候选 Cookies 库:", len(cands))
    hits = 0
    for p in cands:
        try:
            rows = probe(p)
        except Exception:
            continue
        if not rows:
            continue
        hit = [x for x in rows if x[0] and b"4399" in x[0]]
        if not hit:
            continue
        hits += 1
        print("=" * 70)
        print("库:", p, " 总条目:", len(rows), " 4399相关:", len(hit))
        for h, n, v, enc in hit:
            print("   %-22s %-28s = %s  [enc:%d]" % (
                h.decode("utf-8", "ignore"), n.decode("utf-8", "ignore"),
                (v or b"").decode("utf-8", "ignore")[:80], len(enc or b"")))
    if not hits:
        print("未发现含 4399 域名的 Cookie 库（换 --roots 再试，例如 D:\\ E:\\）")


if __name__ == "__main__":
    main()
