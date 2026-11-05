# 4399 客户端登录态提取 / 快照 / 注入

从 Windows 本机上已安装的 **4399 渠道客户端游戏** 中读取登录态（`Xauth / Uauth / Pauth / Puser`），
并支持把登录态**快照**下来、在需要时**注入**回去，适用于重装、换机、切号等场景。

> 只在**你自己的机器、你自己的账号**上使用。工具全程只读优先、写前必备份。

已实测的三款游戏：

| 游戏 | 登录态载体 | 位置 |
|---|---|---|
| 生死狙击（4399） | CEF / Chromium 的 SQLite Cookie 库 | `%LOCALAPPDATA%\Wooduan\Microclient_64\Cookies` |
| 逃跑吧少年（4399） | PC4399SDK 落的 Netscape cookie 文件 | `<游戏根>\dmmdzz_Data\Plugins\x86\PC4399SDK_RES\cookies.dat` |
| 野蛮人大作战（4399） | 注册表值 | `HKCU\Software\4399` → `Pauth` |

原理与工程细节见 **[AGENTS.md](AGENTS.md)**（写给人和 AI 的执行手册）。

---

## 快速开始

```powershell
git clone <this-repo>
cd 4399-login-extract              # 仓库目录
python config.py                   # 1) 先自检路径
python 4399_dump.py                # 2) 读登录态，输出到 out\
```

`config.py` 会打印三个路径是否存在。找不到就设环境变量（不用改代码）：

```powershell
$env:4399_SSJJ_DIR      = "$env:LOCALAPPDATA\Wooduan\Microclient_64"
$env:4399_DMMDZZ_COOKIE = "D:\Games\dmmdzz_4399\game1\dmmdzz_Data\Plugins\x86\PC4399SDK_RES\cookies.dat"
$env:4399_WILDS_DIR     = "C:\Program Files\4399野蛮人大作战"
```

或者复制 `config.example.json` 为 `config.json` 后填路径。

## 快照 / 注入

```powershell
python 4399_session.py save --name A                        # 快照当前登录态 -> out\sessions\
python 4399_session.py list                                 # 列出快照
python 4399_session.py restore --file out\sessions\xxx.json --dry-run   # 演练
python 4399_session.py restore --file out\sessions\xxx.json            # 真注入（自动备份）
python 4399_session.py verify  --file out\sessions\xxx.json            # 回读逐条比对
```

注入前必须**完全退出游戏与启动器/微端**，否则内存里的 cookie 会在退出时回写覆盖。

## 能否"退出登录后再注入回来"？

| 场景 | 结论 | 原因 |
|---|---|---|
| 不退出，直接快照 → 重装/换机后回填 | ✅ 可行 | 服务端会话仍活着 |
| 点"退出登录"后再回填旧 `Xauth` | ⚠️ 不保证 | 注销会销毁服务端会话，本地写回也换不回 |
| 回填 `Pauth`（SDK 长期凭据） | ✅ 较可靠 | SDK 启动时拿它换新会话 |
| 两台机器同用一份快照 | ⚠️ 可能被顶号 | 同一 session 并发 |

## 文件说明

| 文件 | 作用 |
|---|---|
| `config.py` | 路径解析（环境变量 > config.json > 默认值） |
| `4399_dump.py` | 读取三款游戏的登录态，输出 `out\result.json` / `result.txt` |
| `4399_session.py` | 快照 / 注入 / 回读校验 |
| `_selftest.py` | 注入功能的回环自测（只在副本上跑，不碰真实数据） |
| `scan_all_4399_stores.py` | 全盘扫描哪些 Cookie 库含 4399 域 |
| `search_account_content.py` | 按内容定位票据落在哪个文件 |
| `find_sdk_cookie_files.py` | 找 4399 SDK 的 `cookies.dat` |
| `analyze_wilds_config.py` | 探测《野蛮人大作战》`config.txt` 的加密方式 |
| `strings_launcher.py` | 从启动器 exe 提取登录相关字符串，判断载体 |
| `AGENTS.md` | 给 AI 的执行手册（步骤 + 判定标准 + 踩坑表） |

## 技术要点（摘自 AGENTS.md）

- CEF 的 `cookies` 表唯一键是 `creation_utc`，`(host,name,path)` 上没有唯一索引；`encrypted_value` 优先于 `value`；`expires_utc` 是「1601 起微秒」。
- Chromium 80+ 用 `v10` + AES-256-GCM（密钥在 `Local State`，先 DPAPI 解一层）；老版 CEF 是 `v10` + DPAPI 直解。
- Netscape 文件的时间戳是 **Unix 秒**，别和 CEF 的 1601 微秒混用。
- 注册表 `Pauth` 带 md5 签名，不可伪造，只能整段复制。

## 环境

- Windows（依赖 `winreg` / DPAPI）
- Python 3.9+，**无第三方依赖**（遇到 AES-GCM 加密的库时才需要 `cryptography`）

## 免责

仅供在自己拥有或已获授权的设备与账号上做登录态备份与迁移。请勿用于他人账号。
`out\`、`backup\`、`out\sessions\` 下是**真实登录票据**，等同账号密码，已被 `.gitignore` 排除，务必不要提交。

## License

MIT
