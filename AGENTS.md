# AGENTS.md — 4399 客户端登录态：给 AI 的执行手册

> 本文件写给接手本项目的 AI。人类向的说明在 [README.md](README.md)，不要重复维护它；两处冲突时以**本文件**为准并回改 README。

---

## 0. 三个词（读完全文只需记住这三个）

- **载体（carrier）**：登录态在磁盘上的落地形态，共三种——`CEF SQLite` / `Netscape 文件` / `注册表值`。先定载体，再谈读写；定错载体，后面全错。
- **票据（ticket）**：真正代表"已登录"的字段集合，固定是 `Xauth / Uauth / Pauth / Puser / ptusertype`。其它 cookie（`Hm_*`、`webanlytics*`、`phlogact`）是统计噪声，读写都不必管。
- **回环（round-trip）**：`快照 → 清空票据 → 注入 → 回读`，四个动作一次跑完且逐条字符串相等，才算"注入可用"。只写不读等于没验证。

---

## 1. 执行步骤（每步都有判定标准，达不到不许进下一步）

**S1 盘点**
按注册表卸载项 + 常见目录 + 进程命令行，列出所有 4399 渠道游戏及其安装目录。
判定：每款目标游戏有一行"安装目录 + 可执行文件名"，且至少定位到 1 个载体候选。

**S2 定载体**
对每款游戏判定它属于哪种载体（判据见 §2），不要靠猜。三个快速判据：
- 目录里有 `libcef.dll` / `MicroClient*.exe` → `CEF SQLite`
- 目录里有 `PC4399SDK.dll` 或 `PC4399SDK_RES\` → SDK，看是否落 `cookies.dat`（`Netscape`）或注册表 `Pauth`
- 进程命令行里 `--user-data-dir=` → 直接拿到 CEF 数据根，省掉全盘搜

判定：每款游戏写明 `载体类型 + 绝对路径`，路径必须 `Test-Path` 为真。

**S3 读快照**
用现成工具读，不重写：`python 4399_dump.py`。原理见 §3。
判定：每款游戏至少解析出 1 条票据，值为非空明文；若有值解不出（`<解密失败>`），回到 §3 按前缀分支处理，不许跳过。

**S4 注入（按需）**
`python 4399_session.py restore --file <快照> --dry-run` 先演练，再真注入。
判定：演练输出列出了每条 `UPDATE/INSERT` 的目标 `host name`；真注入后无异常退出码。

**S5 回环验证**
`python 4399_session.py verify --file <快照>`，或按 §3.1 手工比对。
判定：**每一条**票据字段回读字符串与快照完全相等；`cookies.dat` 字节级相等；`Pauth` 字符串相等。任一条不等即失败，不许"部分成功"结论。

---

## 2. 载体速查

| 游戏 | 载体 | 路径（默认值，可由 `config.py` / 环境变量覆盖） | 票据落点 |
|---|---|---|---|
| 生死狙击（4399） | CEF SQLite | `%LOCALAPPDATA%\Wooduan\Microclient_64\Cookies` | 表 `cookies` 的 `value` 列 |
| 逃跑吧少年（4399） | Netscape 文件 | `<游戏根>\dmmdzz_Data\Plugins\x86\PC4399SDK_RES\cookies.dat` | 第 6/7 列 `name`/`value` |
| 野蛮人大作战（4399） | 注册表值 | `HKCU\Software\4399` → `Pauth` | `REG_SZ` 单值 |

补充事实（都实测过，别重新推理）：
- 4399 的渠道标识来自**包名后缀**：`ssjj.wd`（生死狙击）、`kid_tpbsl.wd`（逃跑吧少年）；同一台机器上可存在多个 4399 账号，`Puser` 数值并不通用。
- 三款游戏的登录态**互不复用**：Chrome/Edge 的 cookie 库里没有 `Xauth`，只有统计类 cookie。想找登录态不必去看浏览器。
- 野蛮人另有角色态：`Wilds_Win32_Cache\UserDefault.xml`（`RoleInfoUserID`、`area_id`）与 `saveAccouts.dat`（15 字节 UGK protobuf 账号槽）。这两个**不是**登录票据，别拿来判登录。

---

## 3. 三种载体的读写细节

### 3.1 CEF SQLite（生死狙击）

表结构（本机 CEF 版本，`meta.version=8`）：

```
cookies(creation_utc PK, host_key, name, value, path, expires_utc, secure, httponly,
        last_access_utc, has_expires, persistent, priority, encrypted_value BLOB, firstpartyonly)
```

四条硬约束：
1. **唯一键只有 `creation_utc`**，`(host_key,name,path)` 上没有唯一索引 → 注入用"存在则 `UPDATE`、缺失则 `INSERT` 且 `creation_utc = max+1`"，否则会插出重复行、CEF 取到旧值。
2. **`encrypted_value` 优先于 `value`**：写明文时必须同时 `encrypted_value = x''`，否则明文被忽略。
3. `expires_utc` 是「1601-01-01 起的**微秒**」（>1e16 视为微秒，1e13~1e16 视为毫秒，更小视为秒）。写入必须落在未来，否则被当过期丢弃。
4. 读库前**先复制再以 `immutable=1` 只读打开**：游戏运行时会锁库，直连会拿到脏数据或失败。

解密分支（本机三款游戏恰好全是明文，但代码必须保留分支）：
- `value` 非空 → 直接是明文，`enc=plain`。
- `value` 空、`encrypted_value` 以 `v10/v11` 开头 → 去掉 3 字节前缀后：若长度 > 28 且能取到 `Local State` 的 `os_crypt.encrypted_key`（`DPAPI` 解一层得 32 字节 AES 密钥）→ `AES-256-GCM`，布局 `nonce(12) | ct | tag(16)`；否则整段 `CryptUnprotectData`（老版 CEF）。

### 3.2 Netscape 文件（逃跑吧少年）

- 制表符分隔，7 列：`domain, includeSubdomains, path, secure, expires(Unix 秒), name, value`。
- **整文件覆盖**，不做行级合并；写入前先备份原件，回滚就是拷回。
- 时间戳是 **Unix 秒**，与 CEF 的 1601 微秒**不是**同一套，混用会把 cookie 写成 1970 年。
- 该文件由 SDK 内的 libcurl 生成，游戏退出时才落盘 → 注入后立刻启动游戏会被回写覆盖。

### 3.3 注册表值（野蛮人大作战）

`HKCU\Software\4399\Pauth`，`REG_SZ`，7 段竖线分隔：

```
uid | 账号名 | token(28位) | Unix时间戳 | 平台ID | md5签名 | 类型(0/2)
```

- 签名段**不可伪造**，只能整段复制；任何"改 uid 试一下"的构造都是错的。
- 同键下可能还有 `Pauth` 之外的 SDK 值；写入时用 `CreateKey` + `SetValueEx`，别 `DeleteValue` 后重建。
- `HKCU` → 不需要管理员；写 `C:\Program Files` 下的存档才需要。

---

## 4. 决策边界（写代码前先想清楚"这件事做不做得成"）

| 想法 | 结论 | 依据 |
|---|---|---|
| 不退出，快照后回填 | 可行 | 服务端 session 未销毁 |
| 点"退出登录"后再回填旧 `Xauth` | **不保证** | 注销会销毁服务端会话，本地写回也换不回 |
| 回填 `Pauth`（SDK 长期凭据） | 较可靠 | SDK 启动时拿它换新会话，本身不是会话票据 |
| 两台机器同用一份快照 | 可能被顶号 | 同一 session 并发 |
| 直接改 `Pauth` 的 uid 换号 | 不行 | md5 签名绑定字段 |

操作红线：
- 注入前**必须**确认目标进程（含启动器/微端）已退出，否则内存态回写覆盖结果。
- 只写票据字段与 4399 域行；非 4399 域 cookie、游戏 exe、`config.txt`（厂商私有加密）一律不动。
- 每次写盘前把现值备份到 `backup\restore_<时间戳>\`，并把回滚方法写进当次输出。

---

## 5. 失败排查

| 现象 | 大概率原因 | 处置 |
|---|---|---|
| 读库报 `no such column: is_secure` | 该 CEF 版本列名是 `secure`，不是 `is_secure` | 用 `PRAGMA table_info(cookies)` 动态取列，别硬编码 |
| `PRAGMA` 结果里 `host_key` 匹配不上 | 设了 `text_factory=bytes`，列名也是 `bytes` | 比较前统一 `decode()` |
| 注入后游戏仍是未登录 | ①进程没退干净 ②`encrypted_value` 没清空 ③`expires_utc` 已过期 ④服务端 session 已销毁 | 按此顺序排查 |
| `cookies.dat` 注入了却没生效 | 游戏运行中，退出时被 SDK 回写覆盖 | 退出游戏 → 注入 → 立即启动 |
| 报错 `database is locked` | 直连了运行中的库 | 复制到 `backup\` 再读 |
| 解析 `UserDefault.xml` 只匹配到 1 条 | 用 `<(\w+)>(.*?)</\1>` + `re.S` 时根节点把全文吃掉 | 改用 `xml.etree.ElementTree` |

---

## 6. 本机环境事实（省掉重复探测）

```
Python    3.9+（标准库 sqlite3 / winreg / ctypes 即可，无第三方依赖）
生死狙击   <GAME_ROOT>\SSJJ-4399                 （MicroClient64 = CEF 微端；数据在 %LOCALAPPDATA%\Wooduan）
逃跑吧少年 <GAME_ROOT>\dmmdzz_4399               （game1\dmmdzz.exe，Unity + PC4399SDK）
野蛮人     C:\Program Files\4399野蛮人大作战      （Bin\Release.win32\Wilds.exe + PC4399SDK.dll）
```

路径统一由 `config.py` 解析，顺序是 **环境变量 > config.json > 默认值**：

| 变量 | 含义 |
|---|---|
| `4399_SSJJ_DIR` | CEF 微端数据目录（内含 `Cookies`） |
| `4399_DMMDZZ_COOKIE` | 逃跑吧少年 `cookies.dat` 全路径；留空则自动在 `search_roots` 下探测 |
| `4399_WILDS_DIR` | 野蛮人大作战安装目录 |

先跑 `python config.py` 自检：它会打印三个路径是否存在。找不到就设环境变量，别改代码。

工具职责（不要重写，改现有文件）：
`4399_dump.py`=读（三款）、`4399_session.py`=快照/注入/校验、`_selftest.py`=注入功能回环自测（只跑副本）、`scan_all_4399_stores.py`=全盘找含 4399 域的库、`find_sdk_cookie_files.py`=找 SDK 的 `cookies.dat`、`analyze_wilds_config.py`=野蛮人 `config.txt` 加密探测、`strings_launcher.py`=启动器字符串。

---

## 7. 交回时要做的事

1. 跑一遍 `python 4399_dump.py` 与 `python _selftest.py`，把真实输出贴上，不要凭记忆描述。
2. 更新 [README.md](README.md) 的「已验证 / 未验证」两栏：新增能力进"已验证"，没实证的（如票据服务端有效性）留在"未验证"。
3. 若改了载体路径或字段含义，同时改本文件 §2 表格 —— 那是唯一事实来源。
4. 不要把 `out\`、`backup\`、`out\sessions\*.json` 里的真实票据贴进任何对外文本。

