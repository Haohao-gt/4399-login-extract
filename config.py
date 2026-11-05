# -*- coding: utf-8 -*-
"""
统一路径配置。优先级：环境变量 > config.json > 内置默认值。

环境变量：
  4399_SSJJ_DIR        CEF 微端数据目录（内含 Cookies）
  4399_DMMDZZ_COOKIE   逃跑吧少年 cookies.dat 全路径
  4399_WILDS_DIR       野蛮人大作战安装目录

config.json（与本文件同目录，可选，参考 config.example.json）：
  {
    "ssjj_dir": "...",
    "dmmdzz_cookie": "...",
    "wilds_dir": "...",
    "search_roots": ["C:\\\\", "D:\\\\", "F:\\\\"]
  }
"""
import os
import json
import glob

HERE = os.path.dirname(os.path.abspath(__file__))
LOCALAPPDATA = os.environ.get("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))

DEFAULTS = {
    # 生死狙击：4399 极速登陆器（CEF）数据目录，Cookies 子文件即 Cookie 库
    "ssjj_dir": os.path.join(LOCALAPPDATA, "Wooduan", "Microclient_64"),
    # 逃跑吧少年：留给自动探测；也可显式写死
    "dmmdzz_cookie": "",
    # 野蛮人大作战：安装目录（存档在 Wilds_Win32_Cache 下）
    "wilds_dir": r"C:\Program Files\4399野蛮人大作战",
    # 自动探测 cookies.dat 时扫描的盘符/根目录
    "search_roots": ["C:\\", "D:\\", "E:\\", "F:\\"],
}

# cookies.dat 在游戏目录中的固定相对路径
DMMDZZ_REL = os.path.join("dmmdzz_Data", "Plugins", "x86", "PC4399SDK_RES", "cookies.dat")


def _load_file():
    p = os.path.join(HERE, "config.json")
    if not os.path.isfile(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def _find_dmmdzz(roots, max_depth=4):
    """在给定根目录下浅层搜索 dmmdzz_Data/.../cookies.dat。"""
    pat_tail = os.path.join("dmmdzz_Data", "Plugins", "x86", "PC4399SDK_RES", "cookies.dat")
    for root in roots:
        if not os.path.isdir(root):
            continue
        base = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, _ in os.walk(root):
            if dirpath.count(os.sep) - base > max_depth:
                dirnames[:] = []
                continue
            cand = os.path.join(dirpath, pat_tail)
            if os.path.isfile(cand):
                return cand
    return ""


def load():
    cfg = dict(DEFAULTS)
    cfg.update(_load_file())
    cfg["ssjj_dir"] = os.environ.get("4399_SSJJ_DIR", cfg["ssjj_dir"])
    cfg["dmmdzz_cookie"] = os.environ.get("4399_DMMDZZ_COOKIE", cfg["dmmdzz_cookie"])
    cfg["wilds_dir"] = os.environ.get("4399_WILDS_DIR", cfg["wilds_dir"])
    if not cfg["dmmdzz_cookie"]:
        cfg["dmmdzz_cookie"] = _find_dmmdzz(cfg.get("search_roots") or DEFAULTS["search_roots"])
    return cfg


CFG = load()
SSJJ_DIR = CFG["ssjj_dir"]
SSJJ_DB = os.path.join(SSJJ_DIR, "Cookies")
DMMDZZ_COOKIE = CFG["dmmdzz_cookie"]
WILDS_DIR = CFG["wilds_dir"]
WILDS_CACHE = os.path.join(WILDS_DIR, "Wilds_Win32_Cache")


if __name__ == "__main__":
    print("ssjj_dir     :", SSJJ_DIR, os.path.isdir(SSJJ_DIR))
    print("ssjj Cookies :", SSJJ_DB, os.path.isfile(SSJJ_DB))
    print("dmmdzz cookie:", DMMDZZ_COOKIE or "<未找到，请设置 4399_DMMDZZ_COOKIE>")
    print("wilds_dir    :", WILDS_DIR, os.path.isdir(WILDS_DIR))
