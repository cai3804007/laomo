"""建仓计划生成器：给定标的和首仓价，按参数生成补货/价差表。

参数在 model/params.json，改那里就是改你自己的模型。
默认值是从老墨 4 个完整实例反推的均值。
"""
import argparse, json, math, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp.quote import quote

ROOT = pathlib.Path(__file__).resolve().parent.parent
P = json.load(open(ROOT / "model/params.json", encoding="utf-8"))


def round_lot(n: int) -> int:
    """A 股按 100 股一手取整。"""
    return max(100, int(round(n / 100.0)) * 100)


def make(code: str, entry: float | None = None, amount: float | None = None,
         params: dict = P) -> dict:
    q = quote(code)
    if not q:
        raise RuntimeError(f"查不到 {code} 的行情")
    entry = entry or q["price"]
    amount = amount or params["first_batch_amount"]
    qty = round_lot(amount / entry)
    first_cost = entry * qty

    rows, total_cost, total_qty = [], first_cost, qty
    for t in params["tranches"]:
        buy = round(entry * (1 + t["drop_pct"] / 100), 2)
        tq = round_lot(qty * t["qty_ratio"])
        sell = round(buy * (1 + t["spread_pct"] / 100), 2)
        rows.append({"n": t["n"], "buy": buy, "qty": tq, "sell": sell,
                     "profit": round((sell - buy) * tq, 2),
                     "gap_from_now": (buy - q["price"]) / q["price"] * 100})
        total_cost += buy * tq
        total_qty += tq

    target = round(first_cost * params["exit_target_pct"] / 100)
    return {"code": code, "name": q["name"], "now": q["price"], "entry": entry,
            "first_qty": qty, "first_cost": first_cost, "tranches": rows,
            "full_cost": total_cost, "full_qty": total_qty,
            "avg_cost": total_cost / total_qty, "exit_profit": target,
            "exit_price": round(entry + target / qty, 3),
            "stop_loss": params.get("stop_loss")}


def render(p: dict) -> str:
    L = [f"## {p['name']}（{p['code']}）建仓计划", "",
         f"现价 **{p['now']:g}** ｜ 首仓价 **{p['entry']:g}** ｜ "
         f"首仓 {p['first_qty']:,} 股 = {p['first_cost']:,.0f} 元", "",
         "| 档位 | 买入价 | 数量 | 卖出价 | 该档利润 | 距现价 |", "|---|---|---|---|---|---|",
         f"| 首仓 | {p['entry']:g} | {p['first_qty']:,} | — | "
         f"目标赚 {p['exit_profit']:,} 元清仓 | {(p['entry']-p['now'])/p['now']*100:+.1f}% |"]
    for t in p["tranches"]:
        L.append(f"| 补{t['n']} | {t['buy']:g} | {t['qty']:,} | {t['sell']:g} | "
                 f"{t['profit']:,.0f} 元 | {t['gap_from_now']:+.1f}% |")
    L += ["", f"满仓 **{p['full_cost']:,.0f} 元** / {p['full_qty']:,} 股 / "
              f"摊薄均价 **{p['avg_cost']:.3f}**",
          f"清仓目标：主仓涨到约 **{p['exit_price']:g}**（赚 {p['exit_profit']:,} 元）"]
    L.append(f"止损：**{p['stop_loss'] or '无（沿用原模型，这是最大缺口）'}**")
    return "\n".join(L)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("code"); ap.add_argument("--entry", type=float)
    ap.add_argument("--amount", type=float)
    a = ap.parse_args()
    print(render(make(a.code, a.entry, a.amount)))
