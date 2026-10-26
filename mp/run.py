"""公众号文章 → 交易操作结构化报告"""
import argparse, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp import fetch as F, quote as Q, table as T

NUM = re.compile(r"\d+(?:\.\d+)?")


def plan_from_table(tbl: list[list[str]]) -> list[dict]:
    """按列位置解析 操作|买入价|数量|卖出 四列。

    第四列可能是卖出价，也可能是「赚2200」这种目标利润——
    必须按原文判断，不能见数字就当价格（2200 会被算成卖价，利润飙到 5000 万）。
    """
    out = []
    for r in tbl:
        if len(r) < 3 or not re.search(r"进货|补货|建仓|买入", r[0]):
            continue
        def num(i):
            if i >= len(r): return None
            m = NUM.search(r[i])
            return float(m.group()) if m else None
        row = {"操作": r[0].replace(" ", ""), "买入价": num(1), "数量": num(2),
               "卖出价": None, "目标利润": None}
        if row["数量"]:
            row["数量"] = int(row["数量"])
        cell = r[3] if len(r) > 3 else ""
        if re.search(r"赚|目标|盈利", cell):
            row["目标利润"] = num(3)
        else:
            row["卖出价"] = num(3)
            if row["卖出价"] and row["买入价"] and row["数量"]:
                row["价差利润"] = round((row["卖出价"] - row["买入价"]) * row["数量"], 2)
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="*",
                    help="一个或多个文章链接。省略则从剪贴板读（剪贴板里有几条就处理几条）")
    ap.add_argument("--outdir", default="out/mp")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()

    import re as _re
    PAT = r"https://mp\.weixin\.qq\.com/s[^\s\"'<>]*"
    if a.url:
        urls = [u for arg in a.url for u in _re.findall(PAT, arg)] or a.url
    else:
        import subprocess
        clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        urls = _re.findall(PAT, clip)
        if not urls:
            print("剪贴板里没有公众号文章链接。\n"
                  "在微信里打开文章 → 右上角 ··· → 复制链接，然后重跑。")
            return 1
        print(f"从剪贴板读到 {len(urls)} 条链接")

    urls = list(dict.fromkeys(urls))          # 去重保序
    if len(urls) > 1:
        print(f"批量处理 {len(urls)} 篇\n" + "=" * 60)
        fail = 0
        for i, u in enumerate(urls, 1):
            print(f"\n【{i}/{len(urls)}】 {u}")
            try:
                one(u, a)
            except Exception as e:
                fail += 1
                print(f"  ❌ 失败: {e}")
        print(f"\n{'=' * 60}\n完成 {len(urls)-fail}/{len(urls)} 篇")
        return 1 if fail else 0
    return one(urls[0], a)


def one(url: str, a) -> int:
    print("[1/4] 抓文章…")
    meta = F.fetch(url, a.outdir)
    print(f"      《{meta['title']}》 {meta['published']}  "
          f"正文{len(meta['text'])}字  配图{len(meta['images'])}张")

    print("[2/4] 解码标的…")
    code = Q.decode(meta["text"])
    q = Q.quote(code) if code else None
    print(f"      {code} → {q['name'] if q else '查询失败'}")

    print("[3/4] 配图 OCR…")
    lines = T.ocr(meta["images"])
    n0 = len(T.low_confidence(lines))
    lines, weak = T.rescue(lines, meta["images"])
    tbl = T.as_table(lines)
    plan = plan_from_table(tbl)
    print(f"      {len(lines)}行文本 → {len(plan)}档计划；"
          f"低置信 {n0} 处，放大重认救回 {n0-len(weak)} 处，剩 {len(weak)} 处待人工")

    print("[4/4] 生成报告…")
    md = render(meta, code, q, plan, weak)
    p = pathlib.Path(a.outdir) / "report.md"
    p.write_text(md, encoding="utf-8")
    json.dump({"meta": {k: v for k, v in meta.items() if k != "text"},
               "code": code, "quote": q, "plan": plan,
               "low_confidence": weak},
              open(pathlib.Path(a.outdir) / "report.json", "w"),
              ensure_ascii=False, indent=2)
    print(f"\n{md}")
    if a.push:
        from mp import notify
        print("推送:", notify.send(f"{q['name'] if q else code} {meta['title']}", md))


def render(meta, code, q, plan, weak) -> str:
    L = [f"## {meta['title']}", "",
         f"**{q['name'] if q else '?'}（{code}）** ｜ {meta['published']} ｜ {meta['author']}", ""]
    if q:
        L.append(f"现价 **{q['price']}**（昨收 {q['prev_close']}，日内 {q['low']}–{q['high']}）"
                 f" ·  {q['date']} {q['time']}")
        L.append("")
    if plan:
        L += ["### 操作计划", "",
              "| 档位 | 买入价 | 数量 | 卖出价 | 该档利润 | 距现价 |", "|---|---|---|---|---|---|"]
        for r in plan:
            gap = f"{(r['买入价']-q['price'])/q['price']*100:+.1f}%" if q and r["买入价"] else "—"
            sell = f"{r['卖出价']:g}" if r["卖出价"] else "—"
            if r.get("价差利润"):
                prof = f"{r['价差利润']:,.0f} 元"
            elif r.get("目标利润"):
                prof = f"目标 {r['目标利润']:,.0f} 元后清仓"
            else:
                prof = "—"
            qty = f"{r['数量']:,}" if r.get("数量") else "—"
            buy = f"{r['买入价']:g}" if r.get("买入价") is not None else "—"
            L.append(f"| {r['操作']} | {buy} | {qty} | {sell} | {prof} | {gap} |")
        rows = [r for r in plan if r.get("数量") and r.get("买入价")]
        tot = sum(r["买入价"] * r["数量"] for r in rows)
        qt = sum(r["数量"] for r in rows)
        if qt:
            L += ["", f"满仓投入 **{tot:,.0f} 元** / {qt:,} 股 / 摊薄均价 **{tot/qt:.4f}**", ""]
    if weak:
        L += ["> ⚠️ OCR 低置信单元格（需人工复核）：" +
              "、".join(f"`{w['text']}`({w['confidence']:.1f})" for w in weak), ""]
    if not any("止损" in meta["text"] for _ in [1]):
        L.append("> ⚠️ 全文未出现**止损**位。最后一档之下无预设动作。")
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main() or 0)
