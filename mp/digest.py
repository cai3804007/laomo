"""生成并推送「持仓 + 买卖计划」摘要。面向手机阅读。

去掉化名（只给真实标的），买点/卖点单独成段并按接近触发的程度排序。

关键逻辑：**卖点只对已持有的档位才有意义**。补货档没触发就没有那批仓位，
它的价差卖价只是预设，不能列进"可执行卖出"里——否则会看着像有单可下。
"""
import argparse, json, pathlib, sys, datetime
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp.quote import quote
from mp import notify

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOLD = {"601628"}          # 已清仓，不再计入持仓

# 除息/除权日新浪会返回 "XD中远海" 这种带前缀且被截断的名称，用固定表兜底
NAMES = {"601866": "中远海发", "600690": "海尔智家", "000651": "格力电器",
         "600221": "海航控股", "601390": "中国中铁", "601868": "中国能建",
         "600916": "中国黄金", "600600": "青岛啤酒", "601881": "中国银河",
         "600578": "京能电力", "601186": "中国铁建", "000507": "珠海港",
         "601788": "光大证券", "000895": "双汇发展", "600009": "上海机场"}


def _load(name):
    """先找原路径，再找 data/ 下的同名文件。

    out/ 被 gitignore，CI 里拿不到；把文件放 data/ 即可让云端也跑起来。
    """
    cands = [ROOT / name, ROOT / "data" / pathlib.Path(name).name]
    for c in cands:
        if c.exists():
            return json.load(open(c, encoding="utf-8"))
    raise FileNotFoundError(f"找不到 {name}（也试过 data/{pathlib.Path(name).name}）")


def _cost(v) -> float:
    """「23.8补差」→ 23.8"""
    import re
    return float(re.match(r"[\d.]+", str(v)).group())


def build() -> tuple[str, str]:
    plans, holds = _load("plans.json"), _load("out/holdings.json")
    live = {}
    for c in {h["代码"] for h in holds} | set(plans):
        if (q := quote(c)):
            live[c] = q

    pend, active = [], []
    for code, p in plans.items():
        px = live.get(code, {}).get("price")
        if not px:
            continue
        for t in p["tranches"]:
            r = {"code": code, "name": p["name"], "px": px, "n": t["n"],
                 "buy": t["buy"], "sell": t["sell"], "qty": t["qty"],
                 "profit": (t["sell"] - t["buy"]) * t["qty"]}
            if t.get("held"):
                r["gap"] = (t["sell"] - px) / px * 100
                active.append(r)
            else:
                r["gap"] = (t["buy"] - px) / px * 100
                pend.append(r)
    pend.sort(key=lambda x: -x["gap"])
    active.sort(key=lambda x: x["gap"])

    now = datetime.datetime.now()
    L = ["### 🔴 买入计划（待触发补货点）", "",
         "按接近触发的程度排序。「配对卖价」= 该档买入后对应的价差卖点", "",
         "| 标的 | 档 | 触发价 | 数量 | 现价 | 还需跌 | 配对卖价 |",
         "|---|---|---|---|---|---|---|"]
    for b in pend:
        L.append(f"| {b['name']} {b['code']} | 补{b['n']} | **{b['buy']:g}** | {b['qty']:,} "
                 f"| {b['px']:g} | **{b['gap']:+.1f}%** | {b['sell']:g} |")

    L += ["", "### 🟢 卖出计划（已持有、可执行）", ""]
    if active:
        L += ["| 标的 | 档 | 卖出价 | 数量 | 现价 | 还需涨 | 利润 |",
              "|---|---|---|---|---|---|---|"]
        for s in active:
            L.append(f"| {s['name']} {s['code']} | 补{s['n']} | **{s['sell']:g}** | {s['qty']:,} "
                     f"| {s['px']:g} | **{s['gap']:+.1f}%** | {s['profit']:,.0f} 元 |")
    else:
        L.append("**当前没有可执行的卖点。** 这三只的补货档一个都没触发——"
                 "没有补货仓位，就没有价差可做。只剩主仓的清仓目标在等。")

    L += ["", "**清仓目标**（达到即全部卖出）：" + " ｜ ".join(
        f"{p['name']} 赚 {p['target_profit']:,} 元" for p in plans.values()), "",
        f"> 仅含已抓到计划的 {len(plans)} 只。其余持仓的补货表在更早的文章里，尚未收录。", ""]

    L += ["### 持仓一览", "", "| 标的 | 代码 | 成本 | 现价 | 浮动 |", "|---|---|---|---|---|"]
    rows = []
    for h in holds:
        if h["代码"] in SOLD:
            continue
        px = live.get(h["代码"], {}).get("price") or h["现价"]
        c = _cost(h["最新成本"])
        nm = NAMES.get(h["代码"]) or h["名称"].lstrip("XD")
        rows.append((nm, h["代码"], c, px, (px - c) / c * 100))
    if (q := live.get("600690")):
        rows.append(("海尔智家", "600690", 19.55, q["price"], (q["price"] - 19.55) / 19.55 * 100))
    rows.sort(key=lambda r: r[4])
    for n, c, cost, px, chg in rows:
        L.append(f"| {n} | {c} | {cost:g} | {px:g} | **{chg:+.2f}%** |")

    up = sum(1 for r in rows if r[4] > 0)
    L += ["", f"{len(rows)} 批持仓：**{up} 只翻红，{len(rows)-up} 只浮亏**", "",
          "---", f"*{now:%Y-%m-%d %H:%M} 生成 ｜ 价位为机器识别结果，下单前核对原文 ｜ 该模型无止损设计*"]

    title = f"老墨持仓 {now:%m-%d} ｜ {len(rows)}批 · {up}红{len(rows)-up}绿"
    return title, "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    t, body = build()
    print(f"【{t}】\n\n{body}")
    if a.push:
        print("\n推送:", notify.send(t, body, short=f"{len(body)}字 · 买卖点已更新"))
