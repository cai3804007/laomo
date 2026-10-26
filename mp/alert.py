"""盯盘告警：检查是否有标的触及补货点/卖点，命中才推送。

触发条件
  买入：某档补货未持有，且现价 <= 该档触发价
  卖出：某档补货已持有，且现价 >= 该档价差卖价
  清仓：主仓现价 >= 清仓目标价

去重
  已推过的触发记在 state/alerted.json，不会每天重复轰炸。
  价格回到触发价之上再跌回来，会被视为新触发重新提醒。
"""
import argparse, datetime, json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp.quote import quote
from mp import notify

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "alerted.json"


def load_state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(s, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def check(plans: dict, live: dict) -> tuple[list, dict]:
    """返回 (本次新触发列表, 全部当前处于触发态的 key)"""
    state, hits, now_on = load_state(), [], {}
    today = datetime.date.today().isoformat()

    for code, p in plans.items():
        q = live.get(code)
        if not q:
            continue
        px = q["price"]

        for t in p["tranches"]:
            if t.get("held"):
                key, on, kind, trig = f"{code}:sell:{t['n']}", px >= t["sell"], "卖出", t["sell"]
            else:
                key, on, kind, trig = f"{code}:buy:{t['n']}", px <= t["buy"], "买入", t["buy"]
            if on:
                now_on[key] = today
                if key not in state:
                    hits.append({"code": code, "name": p["name"], "px": px, "kind": kind,
                                 "n": t["n"], "trig": trig, "qty": t.get("qty"), "plan": p})

        # 主仓清仓目标。推定计划没有目标利润和首仓数量，跳过这项检查
        if not (p.get("target_profit") and p.get("entry_qty")):
            continue
        exit_px = round(p["entry"] + p["target_profit"] / p["entry_qty"], 3)
        key = f"{code}:exit"
        if px >= exit_px:
            now_on[key] = today
            if key not in state:
                hits.append({"code": code, "name": p["name"], "px": px, "kind": "清仓",
                             "n": 0, "trig": exit_px, "qty": p["entry_qty"], "plan": p})
    return hits, now_on


def plan_table(p: dict, px: float, hl: set | None = None) -> list[str]:
    """渲染某只标的的完整计划，hl 是本次触发的档号集合（可能同时触发多档）。"""
    hl = hl or set()
    has_exit = bool(p.get("target_profit") and p.get("entry_qty"))
    exit_px = round(p["entry"] + p["target_profit"] / p["entry_qty"], 3) if has_exit else None
    q = lambda v: f"{v:,}" if v else "—"

    L = ["| 档位 | 买入价 | 数量 | 卖出价 | 状态 | 距现价 |", "|---|---|---|---|---|---|",
         f"| 首仓 | {p['entry']:g} | {q(p.get('entry_qty'))} | "
         f"{f'{exit_px:g}(清仓)' if has_exit else '—'} | 持有 | "
         f"{f'{(exit_px-px)/px*100:+.1f}%' if has_exit else '—'} |"]
    for t in p["tranches"]:
        mark = "**← 触发**" if t["n"] in hl else ("已持有" if t.get("held") else "待触发")
        tgt = t["sell"] if t.get("held") else t["buy"]
        L.append(f"| 补{t['n']} | {t['buy']:g} | {q(t.get('qty'))} | {t['sell']:g} | {mark} | "
                 f"{(tgt-px)/px*100:+.1f}% |")
    if p.get("inferred"):
        marks = {"补": "补过仓", "差": "做过价差", "红": "分过红"}
        done = "、".join(marks[c] for c in p.get("cost_marks", "") if c in marks)
        L += ["",
              f"> ⚠️ **补货点为推定，非作者公布。** 按模型标准参数 −2.5%/−5%/−9%，"
              f"从**最新成本 {p['latest_cost']:g}** 算出"
              + (f"（该标的{done}，成本已由首次进价 {p['entry']:g} 摊薄到此）。" if done
                 else f"（首次进价 {p['entry']:g}）。"),
              "> 他的真实补货表在该标的的原始进货文章里，尚未收录。"]
    return L


def render(hits: list) -> tuple[str, str]:
    d = datetime.datetime.now()
    by_code = {}
    for h in hits:
        by_code.setdefault(h["code"], []).append(h)

    L = [f"## 触发 {len(hits)} 个操作点", ""]
    for code, hs in by_code.items():
        p, px = hs[0]["plan"], hs[0]["px"]
        L.append(f"### {hs[0]['name']}（{code}）　现价 **{px:g}**")
        L.append("")
        for h in hs:
            icon = {"买入": "🔴", "卖出": "🟢", "清仓": "🎯"}[h["kind"]]
            what = "清仓目标" if h["kind"] == "清仓" else f"补{h['n']} {h['kind']}"
            qty = f" ｜ {h['qty']:,} 股" if h.get("qty") else ""
            L.append(f"{icon} **{what}** 触发价 {h['trig']:g}{qty}")
        L += [""] + plan_table(p, px, hl={h["n"] for h in hs if h["n"]}) + [""]

    L += ["---", f"*{d:%Y-%m-%d %H:%M} ｜ 价位来自文章机器识别，下单前核对原文 ｜ 该模型无止损*"]
    names = "、".join(dict.fromkeys(h["name"] for h in hits))
    kinds = "".join(dict.fromkeys({"买入": "买", "卖出": "卖", "清仓": "清"}[h["kind"]] for h in hits))
    return f"[{kinds}] {names} 触及操作点", "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force", action="store_true", help="忽略去重，重新推送当前所有触发")
    a = ap.parse_args()

    plans = json.loads((ROOT / "plans.json").read_text(encoding="utf-8"))
    live = {c: q for c in plans if (q := quote(c))}
    for c, p in plans.items():
        px = live.get(c, {}).get("price")
        print(f"  {p['name']} {c}  现价 {px}  "
              f"补货点 {'/'.join(str(t['buy']) for t in p['tranches'])}")

    if a.force:
        save_state({})
    hits, now_on = check(plans, live)

    if not hits:
        print(f"\n无新触发（当前处于触发态的档位 {len(now_on)} 个）")
        save_state(now_on)
        return 0

    title, body = render(hits)
    print(f"\n【{title}】\n{body}")
    if a.push:
        print("\n推送:", notify.send(title, body, short=f"{len(hits)} 个操作点"))
    save_state(now_on)
    return 0


if __name__ == "__main__":
    sys.exit(main())
