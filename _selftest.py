# -*- coding: utf-8 -*-
"""自测：在副本上完整跑一遍「快照 -> 清空 -> 注入 -> 回读」，不碰真实游戏数据。"""
import os, sys, json, shutil, sqlite3, tempfile, io, contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import importlib
m = importlib.import_module("4399_session")

tmp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selftest_work")
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp)

# 1) 准备副本
src_db = m.SSJJ_DB
test_db = os.path.join(tmp, "Cookies")
shutil.copy2(src_db, test_db)
src_dmm = m.DMMDZZ_FILE
test_dmm = os.path.join(tmp, "cookies.dat")
shutil.copy2(src_dmm, test_dmm)

print("[1] 副本已就绪:", test_db, test_dmm)

# 2) 快照（走真实读取函数，但作用在副本上）
cookies = m.ssjj_read(test_db)
auth = [c for c in cookies if c["name"] in m.AUTH_NAMES]
print(f"[2] 快照读取: 4399域 {len(cookies)} 条，票据 {len(auth)} 条")
for c in auth:
    print("     ", c["name"], "=", c["value"][:50])

# 3) 模拟「退出登录」：把票据行的 value 清空、encrypted_value 清空
con = sqlite3.connect(test_db)
for c in auth:
    con.execute("UPDATE cookies SET value='', encrypted_value=x'' WHERE host_key=? AND name=? AND path=?",
                (c["host"], c["name"], c["path"]))
con.commit()
left = con.execute("SELECT count(*) FROM cookies WHERE value!='' AND host_key LIKE '%4399%'").fetchone()[0]
con.close()
print(f"[3] 已模拟退出登录：4399域剩余非空 cookie {left} 条")

# 4) 注入（作用在副本上）
ops = m.ssjj_write(test_db, cookies, dry=False)
print(f"[4] 注入完成，执行 {len(ops)} 条语句")

# 5) 回读比对
after = {f'{c["host"]}|{c["name"]}': c["value"] for c in m.ssjj_read(test_db)}
bad = [c["name"] for c in auth if after.get(f'{c["host"]}|{c["name"]}') != c["value"]]
print("[5] 回读比对:", "全部一致 ✅" if not bad else f"不一致 ❌ {bad}")
for c in auth:
    print("     ", f'{c["name"]:<12}', after.get(f'{c["host"]}|{c["name"]}'))

# 6) Netscape 文件注入（副本）
b64 = m.dmmdzz_read(test_dmm)
open(test_dmm, "wb").write(b"# cleared\n")
n = m.dmmdzz_write(test_dmm, b64)
same = m.dmmdzz_read(test_dmm) == b64
print(f"[6] cookies.dat 注入 {n} 字节，回读一致: {same}")

# 7) 注册表 dry-run（不落盘）
w = m.wilds_read()
dops = m.wilds_write(w, dry=True)
print("[7] 注册表 dry-run（未真正写入）:")
for k, d in dops:
    print("     ", k, d[:80])
