"""补货点状态表：哪些已经触到补货点，哪些还差多少。

这是最常被问到的问题（「现在哪些到补货点了」），做成固定命令保证每次口径一致。

注意：本脚本只回答「按模型规则哪些档位被触发」，这是**信息提取**。
它不回答「哪只值得买」——那是投资建议，不在本项目范围内。
"""
import argparse, datetime, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp.quote import quote

ROOT = pathlib.Path(__file__).resolve().parent.parent


def collect() -> tuple[list, str]:
    plans = json.loads((ROOT / "plans.json").read_text(encoding="utf-8"))
    rows, stamp = [], ""
    for c, p in plans.items():
        q = quote(c)
        if not q:
            continue
        stamp = f"{q['date']} {q['time']}"
        px, ts = q["price"], p["tranches"]
        cost = p.get("latest_cost", p["entry"])
        rows.append({
            "name": p["name"].lstrip("XD"), "code": c, "px": px,
            "chg": (px - q["prev_close"]) / q["prev_close"] * 100,
            "entry": p["entry"], "entry_date": p.get("entry_date", ""),
            "vs_entry": (px - p["entry"]) / p["entry"] * 100,
            "cost": cost, "vs_cost": (px - cost) / cost * 100,
            "tranches": ts,
            "fired": [t for t in ts if px <= t["buy"]],
            "next": next((t for t in ts if px > t["buy"]), None),
            "inferred": p.get("inferred", False),
            "note": p.get("note"),
        })
    # 触发多的在前；同样多则离下一档越近越前
    rows.sort(key=lambda r: (-len(r["fired"]),
                             (r["next"]["buy"] - r["px"]) / r["px"] if r["next"] else 99))
    return rows, stamp


def render(rows: list, stamp: str) -> str:
    hit = [r for r in rows if r["fired"]]
    safe = [r for r in rows if not r["fired"]]
    L = [f"## 补货点状态　{stamp}", ""]

    if hit:
        L += [f"### 已触及补货点（{len(hit)} 只）", "",
              "| 标的 | 现价 | 今日 | 建仓价 | 最新成本 | 相对成本 | 已触发档位（价） | 下一档 | 来源 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in hit:
            nx = (f"补{r['next']['n']} **{r['next']['buy']:g}**"
                  f"（{(r['next']['buy']-r['px'])/r['px']*100:+.1f}%）" if r["next"] else "**全档已破**")
            fired = "、".join(f"补{t['n']} {t['buy']:g}" for t in r["fired"])
            L.append(f"| {r['name']} {r['code']} | {r['px']:g} | {r['chg']:+.1f}% "
                     f"| {r['entry']:g} | {r['cost']:g} | {r['vs_cost']:+.1f}% "
                     f"| **{fired}** | {nx} | {'推定' if r['inferred'] else '真实'} |")
        near = [r for r in hit if r["next"] and (r["next"]["buy"]-r["px"])/r["px"]*100 > -1.0]
        if near:
            L += ["", "> ⏰ 盘中可能随时触到下一档：" + "、".join(
                f"{r['name']}（差 {abs((r['next']['buy']-r['px'])/r['px']*100):.1f}%）" for r in near)]
        L.append("")

    L += [f"### 尚未触发（{len(safe)} 只）", "",
          "| 标的 | 现价 | 建仓价 | 最新成本 | 相对成本 | 补1 价 | 还需跌 | 来源 |",
          "|---|---|---|---|---|---|---|---|"]
    for r in safe:
        L.append(f"| {r['name']} {r['code']} | {r['px']:g} | {r['entry']:g} | {r['cost']:g} "
                 f"| {r['vs_cost']:+.1f}% | **{r['next']['buy']:g}** "
                 f"| {(r['next']['buy']-r['px'])/r['px']*100:+.1f}% | {'推定' if r['inferred'] else '真实'} |")

    # 完整档位表：三档价格一次看全
    L += ["", "### 各标的完整补货档位", "",
          "| 标的 | 建仓价 | 补1 | 补2 | 补3 | 现价 | 来源 |", "|---|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: x["name"]):
        cells = []
        for t in r["tranches"]:
            cells.append(f"~~{t['buy']:g}~~" if r["px"] <= t["buy"] else f"{t['buy']:g}")
        L.append(f"| {r['name']} | {r['entry']:g} | " + " | ".join(cells)
                 + f" | {r['px']:g} | {'推定' if r['inferred'] else '真实'} |")
    L.append("")
    L.append("> ~~删除线~~ = 该档已跌破")

    n_inf = sum(1 for r in hit if r["inferred"])
    L += ["", "---", "", "**读这张表必须知道的三件事：**", "",
          f"1. 已触发的 {len(hit)} 只里有 **{n_inf} 只是推定档位**，按 −2.5%/−5%/−9% 从最新成本算出，"
          "**不是作者公布的数字**，和他的真实计划可能差很远。",
          "2. **触发 ≠ 他会买。** 他的完整规则还有安全底座筛选和仓位上限（15 批已封顶、"
          "「不出仓不会再进货」）。海航控股就是反例——推定三档全破，但他明说"
          "「第 3 次补货名额暂时不用」。",
          "3. 本表只陈述**按模型规则哪些档位被触发**，不含任何买卖建议。"]
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true", help="推送到手机")
    a = ap.parse_args()
    rows, stamp = collect()
    body = render(rows, stamp)
    print(body)
    if a.push:
        from mp import notify
        hit = sum(1 for r in rows if r["fired"])
        print("\n推送:", notify.send(f"补货点状态 {len(rows)}只·{hit}只触发", body))
