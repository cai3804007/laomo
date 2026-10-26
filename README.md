# 公众号文章 → 交易操作结构化

抓取公众号文章，解码标的代号，提取完整的买入/补仓/卖出价位表，推送到微信。

## 为什么从视频号改成公众号

最初做的是视频号方案（录屏 + Whisper 转写 + OCR）。后来发现目标账号
**「韭菜老墨」在公众号发同样的内容**，于是整套视频号采集全部废弃，原因：

| | 视频号 | 公众号 |
|---|---|---|
| 内容载体 | 加密视频流 | 公开 HTML |
| 要不要登录微信 | 必须 | 单篇不用 |
| 能否纯云端跑 | 不能 | **能** |
| 识别误差 | ASR 同音字 + 数字听错 | 正文零误差 |

## 配图 OCR 不能省

这位作者把**补货1 / 补货2 的卖出价只放在表格图里，正文完全没写**。
纯文本抓取会漏掉一半卖点。所以保留了 macOS Vision OCR 这条路。

低置信度的数字单元格会**自动裁切放大 6 倍重新识别**——实测把 `2.4` 从
置信度 0.30 救到 1.00。小字号数字在整图里识别率低，单独放大后表现完全不同。

## 标的代号解码

作者把股票代码拆两半藏在昵称里规避审查：

> 「白娘子（**L601**）的对手中原法海（**M866**）」 → `601` + `866` → **601866 中远海发**

字母是障眼法。`mp/quote.py` 按出现顺序拼接数字，校验是否为合法 A 股代码
（60/68/00/30 开头），再查新浪行情接口拿名称和实时价。

## 用法（日常就用这个）

微信收到推送 → 打开文章 → 右上角 `···` → **复制链接** → 然后：

```bash
cd /Users/sean/Desktop/wechat_video && ./go
```

`./go` 自动从剪贴板读链接。全程约 15 秒，**零凭证、零风控、零维护**。

```bash
./go "https://mp.weixin.qq.com/s/xxxxx"   # 也可以直接给链接
./go --push                                # 顺便推送到微信（需 SERVERCHAN_SENDKEY）
```

输出 `out/mp/report.md` 和 `report.json`。

## 后台守护（推荐）

`mp/watch.py` 常驻后台盯剪贴板，一出现公众号文章链接就自动抓取、分析、推送，
并弹 macOS 通知。你在微信里只需点一下「复制链接」。

```bash
# 前台试跑
./.venv/bin/python mp/watch.py --push

# 装成开机自启
launchctl load  ~/Library/LaunchAgents/com.sean.wechatmp.watch.plist
launchctl unload ~/Library/LaunchAgents/com.sean.wechatmp.watch.plist   # 停掉
tail -f out/log/watch.log                                               # 看日志
```

已处理过的链接记在 `out/seen.json`，重复复制不会重复分析。

> ⚠️ **隐私**：剪贴板守护会读取你复制的**所有内容**（包括密码等）。
> 代码只对 `mp.weixin.qq.com` 链接做处理，其余内容不记录、不落盘、不外发，
> 但介意的话就别装开机自启，需要时前台手动跑。

## 接收端：把「捕获」和「分析」解耦

`mp/server.py` 是一个 HTTP 接收端。**任何**能拿到文章链接的东西 POST 过来就自动分析，
分析端不用关心对方是谁：

```bash
./.venv/bin/python mp/server.py --port 8765 --push --token 自定义口令
```

```bash
curl -X POST "http://<mac-ip>:8765/hook?token=xxx" -d 'url=https://mp.weixin.qq.com/s/xxx'
```

不管对方发 form、JSON、还是整包事件（如可爱猫的 `10004` 事件里嵌着 appmsg XML），
都用正则把链接捞出来，所以**换捕获方案不用改这边一行代码**。

### 为什么要解耦

OCR 用的是 **macOS Vision 框架，Windows 上跑不了**，所以流水线不能整体搬到
Windows 服务器。正确切法是让 Windows 只做捕获：

```
Windows（可爱猫 / WeChatFerry，微信已登录）
  └─ 捕获公众号消息 → 提取 URL → POST ─┐
                                        ↓
Mac（mp/server.py）
  └─ 抓取 → 解码标的 → 查行情 → Vision OCR → 出表格 → Server酱推送
```

### 关于可爱猫 / WeChatFerry

可爱猫的 HTTP 插件文档里有「收到公众号消息」事件（类型 `10004`），原理上可行。
但：

- **封号风险最高**——注入式外挂，微信明确打击。**务必用小号**，别拿主号冒险
- **版本锁定**——微信要降到它支持的版本并关自动更新
- **生态老化**——查不到 2026 年的可靠实测，相关仓库近期几乎无提交
- WeChatFerry（wcf）是同类里更活跃的开源选择，风险性质相同

这两个都**没有实测过**，`mp/server.py` 这一端是现成可用的，捕获端自行决定。

### 为什么没走全自动

试过用订阅号后台的 `appmsg` 接口自动拉文章列表（代码在 `mp/listing.py`、
`mp/daily.py`，凭证机制也打通了，`searchbiz` 实测可用），但 **`appmsg` 当场触发
频率限制 ret=200013，至今没跑通过一次**。

也实测过所有 cookie-free 的替代方案，对这个号全部不可用：

| 方案 | 结果 |
|---|---|
| 搜狗微信 | 只索引**认证**订阅号，目标是未认证个人号 |
| wechat2rss 免费列表 | 未收录 |
| RSSHub 公共实例 | 403 |
| 读 Mac 微信本地消息库 | SQLCipher 加密，要从进程内存抠密钥；侵入性过高且易失效，放弃 |

`appmsg` 限流过了 3 天仍未解除，推测该账号被持续限制（新注册未认证号常见）。

根本原因是微信没有公开的「某公众号最新文章」接口，第三方服务只是把登录态问题
转移给了服务商。对一天一篇的场景，剪贴板这 15 秒比维护一套会过期、会被限流的
自动化更划算。`mp/daily.py` 留着，限流解除后随时能切回去。

## 模块

| 文件 | 职责 |
|---|---|
| `mp/fetch.py` | 抓文章 → 元数据 + 正文 + 配图（图片需带 Referer 过防盗链） |
| `mp/quote.py` | 代号解码 → 股票代码 → 新浪行情查名称和现价 |
| `mp/table.py` | 配图 OCR → 按坐标重建表格 + 低置信自动补救 |
| `mp/run.py` | 单篇主流程与报告渲染 |
| `mp/auth.py` | 从 DevTools 的 Copy as cURL 里提取 token + cookie |
| `mp/listing.py` | 搜公众号 + 翻历史文章列表（带频率控制） |
| `mp/daily.py` | 定时拉列表模式（因 appmsg 限流**未跑通**，保留备用） |
| `mp/watch.py` | **剪贴板守护**：自动检测链接 → 分析 → 推送，带去重 |
| `mp/server.py` | **HTTP 接收端**：任何来源 POST 一个 URL 就自动分析 |
| `mp/notify.py` | Server酱推送 |
| `bin/ocr_vision.swift` | macOS Vision OCR，`swiftc -O -o bin/ocr_vision bin/ocr_vision.swift` |

## 获取历史文章列表

单篇抓取不需要登录，但「列出某公众号全部历史文章」没有公开入口。
办法是借用**自己的订阅号后台**：编辑器里的「超链接 → 选择其他公众号」能搜索
任意公众号并浏览其历史文章，底层是两个内部接口。

### 一次性准备

1. [mp.weixin.qq.com](https://mp.weixin.qq.com) 注册个人订阅号（免费，要邮箱+身份证+扫码）。
   **一个身份证只能注册 1 个**，有现成的就别注册了。
2. 登录后台 → F12 打开 Network → 内容与互动 → 草稿箱 → 写新图文 →
   工具栏「超链接」→ 选「选择其他公众号」→ 随便搜一下
3. 在 Network 里找到 `searchbiz` 或 `appmsg` 请求 → 右键 → **Copy as cURL** → 存成文件
4. `./.venv/bin/python mp/auth.py 那个文件` —— 自动提取 token + cookie 存到 `.mp_cred.json`

### 用法

```bash
./.venv/bin/python mp/daily.py --account 韭菜老墨 --dry-run   # 先看有哪些新文章
./.venv/bin/python mp/daily.py --account 韭菜老墨 --push      # 抓取+提取+推送
./.venv/bin/python mp/daily.py --fakeid MzA4... --check 10    # 已知 fakeid 省一次请求
```

### 频率限制（最重要的约束）

这是内部接口不是公开 API，**风控很严**：

- 连续快速请求 → `ret=200013 freq control`，之后要等**几小时到 24 小时**
- 所以 `listing.py` 默认每页间隔 **8–15 秒随机**，`count` 固定 5。**别调小**
- 触发限制后**不要重试**，越试锁越久
- token/cookie 有效期几小时到几天，过期重新走一遍上面的 Copy as cURL

每天查最近 5 篇只需要 1-2 次请求，完全在安全范围内。

## 还没做

- **定时推送**。列表已通，接 GitHub Actions + cron + Server酱 即可纯云端跑。
  注意 `.mp_cred.json` 要放进 repo secrets，且会过期——需要失效告警。
- Server酱推送**尚未实测**（缺 SENDKEY）。

## 免责

工具只做抓取和提取，不判断这些操作是否值得跟。价位是机器识别结果，动钱前核对原文。


## 云端推送（GitHub Actions）

`.github/workflows/digest.yml` 每个交易日 15:20（A 股收盘后）生成持仓+买卖点摘要并推送，
也可在 Actions 页面手动触发。

### 配置密钥

仓库 **Settings → Secrets and variables → Actions**：

| 标签页 | 名称 | 值 |
|---|---|---|
| **Secrets** | `SERVERCHAN_SENDKEY` | Server酱 SendKey（机密） |
| **Variables** | `SERVERCHAN_TAGS` | `laomo`（分组标签，非机密） |

环境变量优先级高于本地 `.env`（见 `mp/notify.py`），所以云端设了就生效，代码不用改。
变量契约见 `.env.example`。

### 持仓数据怎么给云端

`out/` 被 gitignore，CI 拿不到 `holdings.json`，**工作流会检测到并优雅跳过**
（不报错、不发失败邮件）。要启用，把文件放到 `data/`：

```bash
mkdir -p data && cp out/holdings.json data/
git add data/holdings.json && git commit -m "add holdings data" && git push
```

`mp/digest.py` 会自动回退到 `data/` 下的同名文件。

> 注意：这会把持仓明细提交进仓库。**仓库是 private 再这么做**，public 仓库请改用其它方式
> （例如把数据 base64 后存成 Secret，在工作流里解出来）。

### 哪些脚本不能上云

| 脚本 | 原因 |
|---|---|
| `mp/run.py` | OCR 依赖 macOS Vision 框架，Linux runner 跑不了 |
| `mp/daily.py` | 需要微信后台登录态，且 `appmsg` 接口持续限流 |
