"""剪贴板守护：盯住剪贴板，出现公众号文章链接就自动跑完整流程并推送。

为什么是剪贴板而不是读微信数据库：
- 微信消息库是 SQLCipher 加密的，解密要从进程内存抠密钥，且每次更新就失效
- 为拿一个 URL 去读整个私人聊天记录，代价不成比例
剪贴板方案零凭证、零风控、不碰任何隐私数据，你只需在微信里点「复制链接」。
"""
import argparse, json, pathlib, re, subprocess, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp import fetch as F, quote as Q, table as T
from mp.run import plan_from_table, render

URL_RE = re.compile(r"https://mp\.weixin\.qq\.com/s[^\s\"'<>]*")
SEEN = pathlib.Path(__file__).resolve().parent.parent / "out" / "seen.json"


def seen() -> set:
    return set(json.loads(SEEN.read_text())) if SEEN.exists() else set()


def remember(url: str) -> None:
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    SEEN.write_text(json.dumps(sorted(seen() | {url}), ensure_ascii=False))


def clip() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


def notify_mac(title: str, msg: str) -> None:
    """系统通知，让你知道后台确实干活了。"""
    subprocess.run(["osascript", "-e",
                    f'display notification {json.dumps(msg)} with title {json.dumps(title)}'],
                   capture_output=True)


def handle(url: str, push: bool) -> str:
    outdir = f"out/mp/{int(time.time())}"
    meta = F.fetch(url, outdir)
    code = Q.decode(meta["text"])
    q = Q.quote(code) if code else None
    lines = T.ocr(meta["images"])
    lines, weak = T.rescue(lines, meta["images"])
    plan = plan_from_table(T.as_table(lines))
    md = render(meta, code, q, plan, weak)
    (pathlib.Path(outdir) / "report.md").write_text(md, encoding="utf-8")
    name = q["name"] if q else (code or "?")
    if push:
        from mp import notify
        notify.send(f"{name} {meta['title']}", md)
    notify_mac(f"{name} 已分析", meta["title"][:60])
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=2.0, help="轮询秒数")
    ap.add_argument("--push", action="store_true", help="同时推送 Server酱")
    ap.add_argument("--once", action="store_true", help="只检查一次就退出")
    a = ap.parse_args()

    print(f"剪贴板守护启动（每 {a.interval}s 检查一次，Ctrl-C 退出）")
    print("在微信里打开文章 → 右上角 ··· → 复制链接，剩下的我来\n")
    last = None
    while True:
        try:
            cur = clip()
            if cur != last:
                last = cur
                m = URL_RE.search(cur or "")
                if m:
                    url = m.group(0)
                    if url in seen():
                        print(f"· 已处理过，跳过 {url[:48]}…")
                    else:
                        print(f"→ 发现新文章 {url[:48]}…")
                        try:
                            print(handle(url, a.push))
                            remember(url)
                        except Exception as e:
                            print(f"  ❌ 处理失败: {e}")
                            notify_mac("分析失败", str(e)[:80])
            if a.once:
                return 0
            time.sleep(a.interval)
        except KeyboardInterrupt:
            print("\n已退出")
            return 0


if __name__ == "__main__":
    sys.exit(main())
