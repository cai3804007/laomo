"""每日任务：查目标公众号有无新文章 → 抓取提取 → Server酱推送。

用 seen.json 记录已处理过的文章，避免重复推送。
"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp import listing, fetch as F, quote as Q, table as T, notify
from mp.run import plan_from_table, render

STATE = pathlib.Path(__file__).resolve().parent.parent / "out" / "seen.json"


def seen() -> set:
    return set(json.loads(STATE.read_text())) if STATE.exists() else set()


def mark(links: set) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(links), ensure_ascii=False))


def process(url: str, outdir: str) -> tuple[str, dict]:
    meta = F.fetch(url, outdir)
    code = Q.decode(meta["text"])
    q = Q.quote(code) if code else None
    lines = T.ocr(meta["images"])
    lines, weak = T.rescue(lines, meta["images"])
    plan = plan_from_table(T.as_table(lines))
    return render(meta, code, q, plan, weak), {"code": code, "plan": plan, "meta": meta["title"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--account", default="韭菜老墨", help="目标公众号名称")
    ap.add_argument("--fakeid", help="已知 fakeid 时直接给，省一次搜索请求")
    ap.add_argument("--check", type=int, default=1,
                    help="检查最近 N 篇。默认 1——只发一次请求，最省配额")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="只看有哪些新文章，不抓取")
    a = ap.parse_args()

    fakeid = a.fakeid
    if not fakeid:
        print(f"[1/3] 搜索公众号「{a.account}」…")
        hits = listing.search_biz(a.account)
        if not hits:
            print("      没搜到"); return 1
        for h in hits:
            print(f"      {h['nickname']}  fakeid={h['fakeid']}")
        fakeid = hits[0]["fakeid"]
        print(f"      用第一个。下次可加 --fakeid {fakeid} 省一次请求")

    print(f"[2/3] 拉最近 {a.check} 篇…")
    try:
        arts = listing.articles(fakeid, limit=a.check, count=max(a.check, 1))
    except RuntimeError as e:
        print(f"      ❌ {e}")
        if "200013" in str(e):
            print("\n      appmsg 接口被限流。注意：")
            print("      · 不要重试，每次重试都会延长锁定时间")
            print("      · 通常 1-24 小时自行恢复，明天再跑一次")
            print("      · 恢复后每天只跑一次，--check 1 就够（只发一次请求）")
            print("\n      这期间仍可用单篇模式，它不需要任何凭证：")
            print('      ./.venv/bin/python mp/run.py "<文章链接>"')
        return 2
    done = seen()
    new = [x for x in arts if x["link"] not in done]
    print(f"      共 {len(arts)} 篇，其中 {len(new)} 篇是新的")
    for x in new:
        print(f"      · {time.strftime('%Y-%m-%d', time.localtime(x['create_time']))} {x['title']}")
    if a.dry_run or not new:
        return 0

    print(f"[3/3] 逐篇提取…")
    reports = []
    for i, x in enumerate(new):
        md, _ = process(x["link"], f"out/mp/{x['create_time']}")
        reports.append(md)
        print(f"      [{i+1}/{len(new)}] {x['title']} 完成")
    body = "\n\n---\n\n".join(reports)
    print("\n" + body)
    if a.push:
        print("\n推送:", notify.send(f"{a.account} {len(new)}篇新文章", body))
    mark(done | {x["link"] for x in new})
    return 0


if __name__ == "__main__":
    sys.exit(main())
