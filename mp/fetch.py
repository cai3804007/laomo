"""抓一篇公众号文章 → 元数据 + 正文 + 配图。

公众号文章是公开网页，不需要登录态。图片在 mmbiz.qpic.cn 上有防盗链，
请求时必须带 Referer: https://mp.weixin.qq.com。
"""
import re, datetime, pathlib, requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
HDR = {"User-Agent": UA}
IMG_HDR = {"User-Agent": UA, "Referer": "https://mp.weixin.qq.com"}


def fetch(url: str, outdir: str) -> dict:
    d = pathlib.Path(outdir); (d / "img").mkdir(parents=True, exist_ok=True)
    html = requests.get(url, headers=HDR, timeout=30).text
    if re.search(r"环境异常|去验证|该内容已被发布者删除|参数错误", html):
        raise RuntimeError("文章被拦截或已删除")

    meta = {"url": url}
    for k, pat in [("title", r'var msg_title\s*=\s*[\'"](.*?)[\'"]'),
                   ("author", r'var author\s*=\s*[\'"](.*?)[\'"]'),
                   ("biz", r'var biz\s*=\s*[\'"](.*?)[\'"]')]:
        m = re.search(pat, html); meta[k] = m.group(1) if m else None
    m = re.search(r'var ct\s*=\s*[\'"](\d+)[\'"]', html)
    meta["published"] = (datetime.datetime.fromtimestamp(int(m.group(1)))
                         .strftime("%Y-%m-%d %H:%M") if m else None)

    node = BeautifulSoup(html, "lxml").find(id="js_content")
    if node is None:
        raise RuntimeError("找不到正文节点 js_content")
    for br in node.find_all("br"):
        br.replace_with("\n")
    txt = re.sub(r"[ \t\xa0]+", " ", node.get_text("\n"))
    meta["text"] = "\n".join(l.strip() for l in txt.split("\n") if l.strip())

    paths = []
    for i, u in enumerate([i.get("data-src") for i in node.find_all("img") if i.get("data-src")]):
        r = requests.get(u, headers=IMG_HDR, timeout=30)
        if r.status_code != 200:
            continue
        ext = "png" if r.content[:4] == b"\x89PNG" else "jpeg"
        p = d / "img" / f"{i:02d}.{ext}"
        p.write_bytes(r.content)
        paths.append(str(p))
    meta["images"] = paths
    (d / "article.txt").write_text(meta["text"], encoding="utf-8")
    return meta
