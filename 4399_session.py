# -*- coding: utf-8 -*-
r"""
4399 客户端登录态：快照 / 注入（一键快捷登录）
================================================
支持三款游戏（与 4399_dump.py 的读取端一一对应）：

  生死狙击      CEF Cookie 库  %LOCALAPPDATA%\\Wooduan\\Microclient_64\\Cookies
  逃跑吧少年    Netscape 文件  <游戏>\\dmmdzz_Data\\Plugins\\x86\\PC4399SDK_RES\\cookies.dat
  野蛮人大作战  HKCU\\Software\\4399\\Pauth  (+ UserDefault.xml 角色信息)

用法：
  python 4399_session.py save                       # 快照当前登录态 -> out/sessions/
  python 4399_session.py list                       # 列出已保存快照
  python 4399_session.py restore --file SNAP.json   # 注入（会先自动备份）
  python 4399_session.py restore --file SNAP.json --dry-run   # 只演练不落盘
  python 4399_session.py verify  --file SNAP.json   # 读回并逐项比对

安全设计：
  * restore 前把现有库/文件复制到 backup/restore_<时间戳>/，失败可回滚；
  * --dry-run 只打印将要做的变更；
  * 只写 4399 登录票据相关字段，不动其它 cookie；
  * 注入前必须完全退出游戏（运行中的进程会把内存 cookie 回写覆盖）。
"""
import os
import sys
import json
import shutil
import sqlite3
import base64
import datetime
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
SESS = os.path.join(OUT, "sessions")
BACKUP = os.path.join(HERE, "backup")
os.makedirs(SESS, exist_ok=True)

from config import SSJJ_DIR, SSJJ_DB, DMMDZZ_COOKIE as DMMDZZ_FILE, WILDS_CACHE

# 只注入这些票据，其它统计类 cookie 不碰
AUTH_NAMES = {"Xauth", "Uauth", "Pauth", "Puser", "Pnick", "ptusertype", "USESSIONID",
              "USESSIONID4399", "ck_accname", "Qnick", "phlogact"}

EPOCH_1601 = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)
COLS = ["creation_utc", "host_key", "name", "value", "path", "expires_utc", "secure",
        "httponly", "last_access_utc", "has_expires", "persistent", "priority",
        "encrypted_value", "firstpartyonly"]


def now_1601_us():
    return int((datetime.datetime.now(datetime.timezone.utc) - EPOCH_1601).total_seconds() * 1_000_000)


def ts():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def s(v):
    return v.decode("utf-8", "ignore") if isinstance(v, bytes) else v


# ----------------------------------------------------------------- 生死狙击
def ssjj_read(db_path):
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    con.text_factory = bytes
    rows = []
    for r in con.execute("SELECT host_key,name,value,path,expires_utc,secure,httponly FROM cookies"):
        host, name = s(r[0]), s(r[1])
        if "4399" not in host:
            continue
        rows.append({"host": host, "name": name, "value": s(r[2]),
                     "path": s(r[3]) or "/", "expires_utc": int(r[4]),
                     "secure": int(r[5]), "httponly": int(r[6])})
    con.close()
    return rows


def ssjj_write(db_path, cookies, dry=False):
    """把 cookies 写回库：同 (host,name,path) 存在则 UPDATE，否则 INSERT。"""
    con = sqlite3.connect(db_path)
    con.text_factory = bytes
    max_cre = con.execute("SELECT COALESCE(MAX(creation_utc),0) FROM cookies").fetchone()[0]
    ops = []
    for c in cookies:
        if c["name"] not in AUTH_NAMES:
            continue
        cur = con.execute(
            "SELECT count(*) FROM cookies WHERE host_key=? AND name=? AND path=?",
            (c["host"], c["name"], c["path"])).fetchone()[0]
        if cur:
            exp = c["expires_utc"] if c["expires_utc"] > now_1601_us() else now_1601_us() + 7 * 86400 * 1000000
            ops.append(("UPDATE", f'{c["host"]} {c["name"]} = {c["value"][:40]}'))
            if not dry:
                con.execute(
                    "UPDATE cookies SET value=?, encrypted_value=x'', expires_utc=?, secure=?, "
                    "httponly=?, last_access_utc=?, has_expires=1, persistent=1 "
                    "WHERE host_key=? AND name=? AND path=?",
                    (c["value"], exp, c["secure"], c["httponly"], now_1601_us(),
                     c["host"], c["name"], c["path"]))
        else:
            max_cre += 1
            exp = c["expires_utc"] if c["expires_utc"] > now_1601_us() else now_1601_us() + 7 * 86400 * 1000000
            ops.append(("INSERT", f'{c["host"]} {c["name"]} = {c["value"][:40]}'))
            if not dry:
                con.execute(
                    f"INSERT INTO cookies ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                    (max_cre, c["host"], c["name"], c["value"], c["path"], exp,
                     c["secure"], c["httponly"], now_1601_us(), 1, 1, 1, b"", 0))
    if not dry:
        con.commit()
    con.close()
    return ops


# ----------------------------------------------------------------- 逃跑吧少年
def dmmdzz_read(path):
    if not os.path.isfile(path):
        return None
    return base64.b64encode(open(path, "rb").read()).decode()


def dmmdzz_write(path, b64, dry=False):
    data = base64.b64decode(b64)
    if not dry:
        open(path, "wb").write(data)
    return len(data)


# ----------------------------------------------------------------- 野蛮人
def wilds_read():
    import winreg
    res = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\4399") as k:
            i = 0
            while True:
                try:
                    n, v, _ = winreg.EnumValue(k, i)
                    res[n] = v
                    i += 1
                except OSError:
                    break
    except Exception:
        pass
    xml = os.path.join(WILDS_CACHE, "UserDefault.xml")
    if os.path.isfile(xml):
        res["_UserDefault.xml"] = open(xml, encoding="utf-8", errors="ignore").read()
    return res


def wilds_write(values, dry=False):
    import winreg
    ops = []
    for k, v in values.items():
        if k.startswith("_"):
            continue
        ops.append(("REG", f"HKCU\\Software\\4399 {k} = {v[:60]}"))
        if dry:
            continue
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\4399") as key:
            winreg.SetValueEx(key, k, 0, winreg.REG_SZ, v)
    x = values.get("_UserDefault.xml")
    if x:
        p = os.path.join(WILDS_CACHE, "UserDefault.xml")
        ops.append(("FILE", f"{p} ({len(x)} 字符)"))
        if not dry:
            open(p, "w", encoding="utf-8").write(x)
    return ops


# ----------------------------------------------------------------- 命令
def cmd_save(args):
    snap = {"tool": "4399_session", "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "host": os.environ.get("COMPUTERNAME"), "user": os.path.expanduser("~")}
    snap["ssjj"] = ssjj_read(SSJJ_DB) if os.path.isfile(SSJJ_DB) else []
    b64 = dmmdzz_read(DMMDZZ_FILE)
    if b64:
        snap["dmmdzz"] = b64
    snap["wilds"] = wilds_read()

    name = f"session_{args.name or 'A'}_{ts()}.json"
    p = os.path.join(SESS, name)
    json.dump(snap, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    n_auth = sum(1 for c in snap["ssjj"] if c["name"] in AUTH_NAMES)
    print(f"[OK] 快照已保存: {p}")
    print(f"     生死狙击 cookie: 4399域 {len(snap['ssjj'])} 条，其中票据 {n_auth} 条")
    print(f"     逃跑吧少年 cookies.dat: {'已收录 ' + str(len(b64)) + ' 字符(base64)' if b64 else '未找到'}")
    print(f"     野蛮人 注册表: {'Pauth 已收录' if 'Pauth' in snap['wilds'] else '无'}，"
          f"UserDefault.xml {'已收录' if '_UserDefault.xml' in snap['wilds'] else '无'}")
    return p


def cmd_list(args):
    files = sorted(x for x in os.listdir(SESS) if x.endswith(".json"))
    if not files:
        print("没有快照")
        return
    for f in files:
        p = os.path.join(SESS, f)
        try:
            d = json.load(open(p, encoding="utf-8"))
            print(f"{f}   {d.get('time','?')}   ssjj={len(d.get('ssjj',[]))}条  "
                  f"dmmdzz={'有' if d.get('dmmdzz') else '无'}  wilds={'有' if d.get('wilds') else '无'}")
        except Exception as e:
            print(f"{f}   <损坏: {e}>")


def _backup(tag):
    d = os.path.join(BACKUP, f"restore_{tag}")
    os.makedirs(d, exist_ok=True)
    if os.path.isfile(SSJJ_DB):
        shutil.copy2(SSJJ_DB, os.path.join(d, "Cookies"))
    if os.path.isfile(DMMDZZ_FILE):
        shutil.copy2(DMMDZZ_FILE, os.path.join(d, "cookies.dat"))
    print(f"[备份] 现有登录态已复制到 {d}（还原：把这里两个文件拷回原路径即可）")
    return d


def cmd_restore(args):
    snap = json.load(open(args.file, encoding="utf-8"))
    dry = args.dry_run
    tag = ts()
    if not dry:
        _backup(tag)

    print(f"\n=== {'演练(dry-run)' if dry else '注入'} 快照 {os.path.basename(args.file)} ===")

    # 1) 生死狙击
    db = args.db or SSJJ_DB
    if snap.get("ssjj") and os.path.isfile(db):
        ops = ssjj_write(db, snap["ssjj"], dry=dry)
        print(f"[生死狙击] {db}")
        for kind, desc in ops:
            print(f"   {kind:6} {desc}")
    else:
        print("[生死狙击] 跳过（快照无数据或库不存在）")

    # 2) 逃跑吧少年
    if snap.get("dmmdzz"):
        target = args.dmmdzz or DMMDZZ_FILE
        n = dmmdzz_write(target, snap["dmmdzz"], dry=dry)
        print(f"[逃跑吧少年] {target}  <- {n} 字节")
    else:
        print("[逃跑吧少年] 跳过（快照无数据）")

    # 3) 野蛮人
    if snap.get("wilds"):
        ops = wilds_write(snap["wilds"], dry=dry)
        print("[野蛮人大作战]")
        for kind, desc in ops:
            print(f"   {kind:4} {desc}")
    else:
        print("[野蛮人大作战] 跳过（快照无数据）")

    print("\n完成。启动游戏前请确认：游戏进程已完全退出（含启动器/微端）。")


def cmd_verify(args):
    snap = json.load(open(args.file, encoding="utf-8"))
    ok = True
    print("=== 回读比对 ===")
    cur = {f'{c["host"]}|{c["name"]}|{c["path"]}': c for c in ssjj_read(SSJJ_DB)}
    for c in snap.get("ssjj", []):
        if c["name"] not in AUTH_NAMES:
            continue
        k = f'{c["host"]}|{c["name"]}|{c["path"]}'
        got = cur.get(k)
        same = got and got["value"] == c["value"]
        ok &= bool(same)
        print(f'  [{"OK " if same else "差异"}] {c["host"]} {c["name"]}: '
              f'{(got or {}).get("value", "<缺失>")}')
    if snap.get("dmmdzz"):
        same = dmmdzz_read(DMMDZZ_FILE) == snap["dmmdzz"]
        ok &= same
        print(f'  [{"OK " if same else "差异"}] 逃跑吧少年 cookies.dat')
    w = snap.get("wilds") or {}
    if "Pauth" in w:
        cur_p = wilds_read().get("Pauth")
        same = cur_p == w["Pauth"]
        ok &= same
        print(f'  [{"OK " if same else "差异"}] 野蛮人 Pauth = {cur_p}')
    print("\n结论:", "全部一致，注入成功" if ok else "存在差异，见上")


def main():
    ap = argparse.ArgumentParser(description="4399 登录态快照/注入")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("save"); a.add_argument("--name", default=None); a.set_defaults(fn=cmd_save)
    b = sub.add_parser("list"); b.set_defaults(fn=cmd_list)
    c = sub.add_parser("restore")
    c.add_argument("--file", required=True)
    c.add_argument("--dry-run", action="store_true")
    c.add_argument("--db", default=None, help="覆盖 Cookie 库路径（测试用）")
    c.add_argument("--dmmdzz", default=None, help="覆盖 cookies.dat 路径（测试用）")
    c.set_defaults(fn=cmd_restore)
    d = sub.add_parser("verify"); d.add_argument("--file", required=True); d.set_defaults(fn=cmd_verify)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()

