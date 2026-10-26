# 老墨持仓追踪

把「韭菜老墨」公众号文章里的交易操作提取成结构化数据，追踪持仓与买卖计划，推送到手机。

## 工作方式

**手动喂链接**。在微信里打开文章 → 右上角 `···` → 复制链接，然后：

```bash
./go "https://mp.weixin.qq.com/s/xxxxx"          # 单篇
./go "链接1 链接2 链接3"                          # 批量
./go                                             # 不带参数则读剪贴板
./go "链接" --push                               # 顺便推送到手机
```

输出 `out/mp/report.md` 和 `report.json`。

> 早期做过自动发现新文章的方案（订阅号后台 `appmsg` 接口、可爱猫转发、剪贴板守护），
> 均已移除：接口持续限流、外挂有封号风险，而手动复制链接只要 2 秒。

## 两个关键设计

### 配图 OCR 不能省

这位作者**把部分补货卖价只放在表格图里，正文完全不写**。纯文本抓取会漏掉一半卖点。
所以保留了 macOS Vision OCR 这条路（`bin/ocr_vision.swift`）。

低置信度的数字单元格会**自动裁切放大 6 倍重新识别**——实测把 `2.4` 从置信度 0.30 救到 1.00。

### 标的代号解码

作者把股票代码拆开藏在化名里规避审查：

> 「白娘子（**L601**）的对手中原法海（**M866**）」 → `601` + `866` → **601866 中远海发**
> 「格利（**L000**）小家电（**M651**）」 → **000651 格力电器**

`mp/quote.py` 按出现顺序拼接数字，校验是否为合法 A 股代码（60/68/00/30 开头），
再查新浪行情接口拿真实名称和实时价。

## 持仓摘要与推送

```bash
./.venv/bin/python mp/digest.py           # 只看
./.venv/bin/python mp/digest.py --push    # 推送到手机
```

生成「买入计划（待触发补货点）/ 卖出计划（已持有、可执行）/ 持仓一览」三段，
按接近触发的程度排序。

> **卖点只对已持有的档位才有意义**。补货档没触发就没有那批仓位，它的价差卖价只是预设，
> 不会列进「可执行卖出」——否则会看着像有单可下。档位状态在 `plans.json` 的 `held` 字段。

## 建仓计划生成器

从作者 4 个真实案例反推出参数（买价平均偏差 0.26%、卖价 0.53%），参数全部外置：

```bash
./.venv/bin/python model/plan.py 600690 --entry 19.55 --amount 58650
```

改 `model/params.json` 就等于建立你自己的模型。详见 [老墨模型拆解.md](老墨模型拆解.md)。

## 环境变量

| 变量 | 用途 | 本地 | 云端 |
|---|---|---|---|
| `SERVERCHAN_SENDKEY` | Server酱推送密钥（机密） | `.env` | Actions **Secrets** |
| `SERVERCHAN_TAGS` | 推送标签，App 端分组用 | `.env` | Actions **Variables** |

环境变量优先级高于 `.env`（`mp/notify.py`），云端设了就生效，代码不用改。
契约见 `.env.example`。

## 云端推送

`.github/workflows/digest.yml` 每个交易日 15:20（A 股收盘后）推送，也可手动触发。

`out/` 被 gitignore，CI 拿不到 `holdings.json`，**工作流会检测到并优雅跳过**
（不报错、不发失败邮件）。要启用：

```bash
mkdir -p data && cp out/holdings.json data/ && git add data/ && git commit -m "add holdings" && git push
```

`mp/digest.py` 会自动回退到 `data/` 下的同名文件。

> 这会把持仓明细提交进仓库，**仓库是 private 再这么做**。

**`mp/run.py` 不能上云**——OCR 依赖 macOS Vision 框架，Linux runner 跑不了。

## 模块

| 文件 | 职责 |
|---|---|
| `mp/fetch.py` | 抓文章 → 元数据 + 正文 + 配图（图片需带 Referer 过防盗链） |
| `mp/quote.py` | 代号解码 → 股票代码 → 新浪行情查名称和现价 |
| `mp/table.py` | 配图 OCR → 按坐标重建表格 + 低置信自动放大补救 |
| `mp/run.py` | 单篇主流程与报告渲染 |
| `mp/digest.py` | 持仓摘要生成与推送 |
| `mp/notify.py` | Server酱推送（兼容 Server酱³ 和 Turbo） |
| `model/plan.py` | 参数化建仓计划生成器 |
| `model/params.json` | 模型参数，改这里就是改你自己的模型 |
| `plans.json` | 各标的的补货/卖出计划，随文章处理累积 |
| `bin/ocr_vision.swift` | macOS Vision OCR，`swiftc -O -o bin/ocr_vision bin/ocr_vision.swift` |

## 文档

- [持仓与计划.md](持仓与计划.md) —— 当前持仓明细与今日变动
- [老墨模型拆解.md](老墨模型拆解.md) —— 四层模型结构、反推的量化参数、六个缺口

## 免责

工具只做抓取和提取，不判断这些操作是否值得跟。所有价位为机器识别结果，操作前核对原文。
该模型本身无止损设计。
