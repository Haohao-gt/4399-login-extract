# -*- coding: utf-8 -*-
"""探测《野蛮人大作战》config.txt 的加密方式（单字节 XOR / 结构判断），只读。

用法：
    python analyze_wilds_config.py                     # 用 config.py 里的安装目录
    python analyze_wilds_config.py --file <config.txt>
"""
import os
import sys
import argparse
import collections
from config import WILDS_DIR


def printable_ratio(b):
    ok = sum(1 for c in b if 32 <= c < 127 or c in (9, 10, 13) or c > 127)
    return ok / max(1, len(b))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join(WILDS_DIR, "config.txt"))
    args = ap.parse_args()

    data = open(args.file, "rb").read()
    print("文件:", args.file)
    print("长度:", len(data))
    print("前64字节:", data[:64].hex(" "))
    print("DPAPI 特征:", "是" if data[:4] == b"\x01\x00\x00\x00" else "否（非标准 DPAPI 头）")

    best = sorted(((printable_ratio(bytes(c ^ k for c in data)), k) for k in range(1, 256)), reverse=True)
    print("\n单字节 XOR 前 5 名（可打印率 / 密钥）：")
    for ratio, k in best[:5]:
        print(f"  0x{k:02x}  {ratio:.2f}")

    if best[0][0] < 0.95:
        print("\n结论：不像单字节 XOR，考虑多字节循环密钥 / RC4 / 私有混淆（本仓库未破解）。")
    print("\n首字节分布:", collections.Counter(data).most_common(5))


if __name__ == "__main__":
    main()
