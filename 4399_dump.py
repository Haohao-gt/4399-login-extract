# -*- coding: utf-8 -*-
r"""
4399 三款客户端游戏（生死狙击 / 逃跑吧少年 / 野蛮人大作战）登录态读取工具
============================================================================
原理（对应本机实测结果）：
  1) 生死狙击  -> 4399「极速登陆器」MicroClient64，基于 CEF(Chromium)
        Cookie 库: %LOCALAPPDATA%\\Wooduan\\Microclient_64\\Cookies  (SQLite)
        关键 Cookie: Xauth / Uauth / Puser / Pnick / ptusertype
        加密方式: value 字段多为明文；若为 encrypted_value，则按
                 v10 + DPAPI（老 CEF）/ v10 + AES-256-GCM（Chromium 80+，密钥取自 Local State）
  2) 逃跑吧少年 -> PC4399SDK（libcurl），登录票据落地为 Netscape cookie 文件
        <游戏根>\dmmdzz_Data\Plugins\x86\PC4399SDK_RES\cookies.dat
        关键 Cookie: Pauth / Xauth / Uauth / Puser / ck_accname
  3) 野蛮人大作战 -> PC4399SDK + 自有存档
        注册表: HKCU\\Software\\4399\\Pauth（SDK 自动登录凭据，含 uid/账号/token）
        存档:   <安装目录>\\Wilds_Win32_Cache\\UserDefault.xml（RoleInfoUserID、area_id）
                <安装目录>\\Wilds_Win32_Cache\\saveAccouts.dat（账号列表，protobuf）
        config.txt 为厂商私有加密，未纳入解析。

用法：
    python 4399_dump.py            # 读取全部，输出 out/result.json + out/result.txt
    python 4399_dump.py --json     # 只在控制台打印 JSON
只读，不修改任何游戏文件；读取前会把 Cookie 库复制到 backup/ 再解析。
"""
import os
import sys
import json
import shutil
import sqlite3
import datetime
import base64
import ctypes
import ctypes.wintypes as wt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
BACKUP = os.path.join(HERE, "backup")
os.makedirs(OUT, exist_ok=True)
os.makedirs(BACKUP, exist_ok=True)

from config import SSJJ_DIR, SSJJ_DB, DMMDZZ_COOKIE, WILDS_DIR, WILDS_CACHE

KEY_COOKIES = {"Xauth", "Uauth", "Pauth", "Puser", "Pnick", "ck_accname", "USESSIONID", "ptusertype"}


# ------------------------------------------------------------------ DPAPI
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def dpapi_decrypt(data: bytes):
    try:
        buf = ctypes.create_string_buffer(data, len(data))
        b_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
        b_out = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(b_in), None, None, None, None, 0, ctypes.byref(b_out)):
            return None
        try:
            return ctypes.string_at(b_out.pbData, b_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(b_out.pbData)
    except Exception:
        return None


def chromium_key(user_data_dir):
    p = os.path.join(user_data_dir, "Local State")
    if not os.path.isfile(p):
        return None
    try:
        cfg = json.load(open(p, encoding="utf-8"))
        enc = base64.b64decode(cfg["os_crypt"]["encrypted_key"])
        if enc.startswith(b"DPAPI"):
            enc = enc[5:]
        k = dpapi_decrypt(enc)
        return k if k and len(k) in (16, 32) else None
    except Exception:
        return None


def decrypt_cookie(blob, key):
    if not blob:
        return "", "empty"
    body = blob[3:] if blob[:3] in (b"v10", b"v11", b"v20") else blob
    if key and len(body) > 28:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            return AESGCM(key).decrypt(body[:12], body[12:-16] + body[-16:], None).decode("utf-8", "ignore"), "AES-GCM"
        except Exception:
            pass
    pt = dpapi_decrypt(body)
    if pt is not None:
        return pt.decode("utf-8", "ignore"), "DPAPI"
    return "<解密失败>", "unknown"


def chrome_time(v):
    if not v or v <= 0:
        return "会话"
    try:
        sec = v / 1e6 if v > 10 ** 16 else (v / 1e3 if v > 10 ** 13 else v)
        t = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=sec)
        return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(v)


# ------------------------------------------------------------------ 读取器
def read_cef_cookies(store_dir, tag):
    db = None
    for cand in (os.path.join(store_dir, "Cookies"),
                 os.path.join(store_dir, "Network", "Cookies"),
                 os.path.join(store_dir, "Default", "Network", "Cookies")):
        if os.path.isfile(cand):
            db = cand
            break
    if not db:
        return {"found": False, "dir": store_dir}

    key = None
    for up in (store_dir, os.path.dirname(store_dir)):
        key = chromium_key(up)
        if key:
            break

    bdir = os.path.join(BACKUP, tag)
    os.makedirs(bdir, exist_ok=True)
    tmp = os.path.join(bdir, "Cookies")
    try:
        shutil.copy2(db, tmp)
        for extra in ("Cookies-journal", "Cookies-wal", "Cookies-shm"):
            src = os.path.join(os.path.dirname(db), extra)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(bdir, extra))
    except Exception as e:
        return {"found": True, "db": db, "error": f"复制失败: {e}"}

    out = []
    err = None
    try:
        con = sqlite3.connect(f"file:{tmp}?mode=ro&immutable=1", uri=True)
        con.text_factory = bytes
        cols = [c[1].decode() if isinstance(c[1], bytes) else c[1]
                for c in con.execute("PRAGMA table_info(cookies)")]
        for row in con.execute("SELECT host_key,name,value,path,expires_utc,"
                               "       COALESCE(encrypted_value, x'') FROM cookies"):
            host, name, val, path, exp, enc = row
            host = (host or b"").decode("utf-8", "ignore")
            name = (name or b"").decode("utf-8", "ignore")
            path = (path or b"").decode("utf-8", "ignore")
            txt = (val or b"").decode("utf-8", "ignore")
            how = "plain"
            if not txt and enc:
                txt, how = decrypt_cookie(bytes(enc), key)
            out.append({"host": host, "name": name, "path": path or "/",
                        "value": txt, "enc": how, "expires": chrome_time(exp)})
        con.close()
    except Exception as e:
        err = str(e)
    return {"found": True, "db": db, "aes_key": bool(key), "cookies": out, "error": err}


def read_netscape(path):
    if not os.path.isfile(path):
        return {"found": False, "path": path}
    rows = []
    for line in open(path, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        p = [x.strip() for x in line.split("\t")]
        if len(p) >= 7:
            try:
                exp = (datetime.datetime.fromtimestamp(int(p[4])).strftime("%Y-%m-%d %H:%M:%S")
                       if int(p[4]) > 0 else "会话")
            except Exception:
                exp = p[4]
            rows.append({"host": p[0], "path": p[2], "secure": p[3] == "TRUE",
                         "expires": exp, "name": p[5], "value": p[6], "enc": "plain"})
    return {"found": True, "path": path, "cookies": rows}


def read_reg_pauth():
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
        return {"found": False}
    return {"found": bool(res), "values": res}


def read_wilds():
    info = {"install": WILDS_DIR, "exists": os.path.isdir(WILDS_DIR)}
    xml = os.path.join(WILDS_CACHE, "UserDefault.xml")
    if os.path.isfile(xml):
        keys = {}
        try:
            import xml.etree.ElementTree as ET
            root = ET.parse(xml).getroot()
            for el in root.iter():
                if el.text and el.text.strip():
                    keys[el.tag] = el.text.strip()
        except Exception as e:
            keys["_parse_error"] = str(e)
        info["userdefault"] = {k: v for k, v in keys.items()
                               if k in ("RoleInfoUserID", "area_id", "UserAgreement", "_parse_error")}
    acc = os.path.join(WILDS_CACHE, "saveAccouts.dat")
    if os.path.isfile(acc):
        b = open(acc, "rb").read()
        info["saveAccouts"] = {"size": len(b), "hex": b.hex(" ")}
    return info


def parse_pauth(v):
    """4399 Pauth: uid|用户名|token|ts|平台id|签名|类型"""
    if not isinstance(v, str):
        return None
    p = v.split("|")
    if len(p) < 6:
        return {"raw": v}
    ts = int(p[3]) if p[3].isdigit() else 0
    when = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
    return {"uid": p[0], "account": p[1], "token": p[2], "time": when,
            "platform_id": p[4], "sign": p[5], "raw": v}


# ------------------------------------------------------------------ 主流程
def main():
    result = {"generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "host_user": os.path.expanduser("~")}

    ssjj = read_cef_cookies(SSJJ_DIR, "生死狙击_MicroClient")
    dmmdzz = read_netscape(DMMDZZ_COOKIE)
    wilds = read_wilds()
    reg = read_reg_pauth()

    result["生死狙击"] = ssjj
    result["逃跑吧少年"] = dmmdzz
    result["野蛮人大作战"] = wilds
    result["4399SDK注册表"] = reg
    if reg.get("found") and "Pauth" in reg["values"]:
        result["4399SDK注册表"]["Pauth解析"] = parse_pauth(reg["values"]["Pauth"])

    json.dump(result, open(os.path.join(OUT, "result.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    # Netscape 导出（方便浏览器/curl 导入）
    lines = ["# Netscape HTTP Cookie File"]
    for blk in (ssjj, dmmdzz):
        for c in blk.get("cookies", []):
            if c["name"] in KEY_COOKIES:
                lines.append("\t".join([c["host"], "TRUE", c["path"], "TRUE", "0", c["name"], c["value"]]))
    open(os.path.join(OUT, "cookies_4399_netscape.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")

    # 人读汇总
    L = []
    def w(s=""):
        L.append(s)

    w("=" * 78)
    w(f"4399 客户端登录态读取结果   {result['generated']}")
    w("=" * 78)
    for game in ("生死狙击", "逃跑吧少年"):
        blk = result[game]
        w(f"\n【{game}】")
        if not blk.get("found"):
            w("  未找到存储位置")
            continue
        w(f"  来源: {blk.get('db') or blk.get('path')}")
        for c in blk.get("cookies", []):
            if c["name"] in KEY_COOKIES:
                w(f"    {c['name']:<14}= {c['value']}")
                w(f"    {'':<14}  (domain={c['host']} 到期={c['expires']})")
        if blk.get("error"):
            w("  错误: " + blk["error"])

    w("\n【野蛮人大作战】")
    w(f"  安装目录: {wilds.get('install')}  存在={wilds.get('exists')}")
    for k, v in (wilds.get("userdefault") or {}).items():
        w(f"    {k} = {v}")
    if wilds.get("saveAccouts"):
        w(f"    saveAccouts.dat ({wilds['saveAccouts']['size']}字节): {wilds['saveAccouts']['hex']}")

    w("\n【4399 平台 SDK 自动登录凭据 HKCU\\Software\\4399】")
    if reg.get("found"):
        for k, v in reg["values"].items():
            w(f"    {k} = {v}")
        pa = result["4399SDK注册表"].get("Pauth解析") or {}
        if pa.get("account"):
            w(f"    -> 账号={pa['account']}  uid={pa['uid']}  登录时间={pa['time']}  平台={pa['platform_id']}")
    else:
        w("    未找到")

    txt = "\n".join(L)
    open(os.path.join(OUT, "result.txt"), "w", encoding="utf-8").write(txt)
    print(txt)
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


