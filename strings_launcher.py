# -*- coding: utf-8 -*-
"""从启动器 exe 中提取登录相关字符串（ascii + UTF-16LE），用于快速判断载体类型。

判读要点：
  - 出现 InternetGetCookieW / InternetSetCookieW  → 走 WinINET cookie（老 IE 控件）
  - 出现 --user-data-dir / WebView2 / EBWebView  → 走 WebView2，profile 目录里才有 Cookies
  - 出现 PC4399SDK / cookies.dat                 → 走 4399 SDK，票据落在 cookies.dat 或注册表

用法：
    python strings_launcher.py <exe> [<exe> ...]
    python strings_launcher.py                     # 用 config.py 里的野蛮人安装目录做默认
"""
import os
import re
import sys
import glob
from config import WILDS_DIR

KW = ["my.4399", "4399.com", "webview", "WebView", "cef", "CEF", "Cookies", "cookie",
      "user-data", "Pauth", "Xauth", "Uauth", "login", "Login", "passport",
      "InternetGetCookie", "InternetSetCookie", "AppData", "PC4399SDK", "cookies.dat"]


def scan(path):
    print("=" * 70)
    print(path, os.path.getsize(path) if os.path.isfile(path) else "缺失")
    if not os.path.isfile(path):
        return
    data = open(path, "rb").read()
    seen = set()
    for m in re.finditer(rb"[\x20-\x7e]{6,}", data):
        s = m.group().decode("ascii", "ignore")
        if any(k.lower() in s.lower() for k in KW) and s not in seen:
            seen.add(s)
            print("  A:", s[:160])
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
        s = m.group().decode("utf-16-le", "ignore")
        if any(k.lower() in s.lower() for k in KW) and s not in seen:
            seen.add(s)
            print("  W:", s[:160])


def main():
    files = sys.argv[1:]
    if not files:
        files = sorted(glob.glob(os.path.join(WILDS_DIR, "*.exe"))) + \
                sorted(glob.glob(os.path.join(WILDS_DIR, "Bin", "Release.win32", "*.exe")))
    for f in files:
        scan(f)


if __name__ == "__main__":
    main()
