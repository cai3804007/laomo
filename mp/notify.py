"""Server酱推送。兼容 Server酱³(sctp 开头) 和 Turbo 版。

tags 用于 app 端分组查看，多个用 | 分隔。本仓库固定用 laomo。
key 和默认 tag 从 .env 读，.env 已在 .gitignore 里。
"""
import os, pathlib, re, requests

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _env() -> dict:
    """读 .env（简单 KEY=VALUE），环境变量优先。"""
    d = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                d[k.strip()] = v.strip()
    d.update({k: v for k, v in os.environ.items() if k.startswith("SERVERCHAN_")})
    return d


def send(title: str, markdown: str, sendkey: str | None = None,
         tags: str | None = None, short: str | None = None) -> dict:
    env = _env()
    key = sendkey or env.get("SERVERCHAN_SENDKEY", "")
    if not key:
        raise RuntimeError("缺少 SERVERCHAN_SENDKEY（放 .env 或环境变量）")
    tags = tags if tags is not None else env.get("SERVERCHAN_TAGS", "")

    m = re.match(r"^sctp(\d+)t", key)
    url = (f"https://{m.group(1)}.push.ft07.com/send/{key}.send" if m
           else f"https://sctapi.ftqq.com/{key}.send")

    data = {"title": title[:100], "desp": markdown}
    if tags:
        data["tags"] = tags
    if short:
        data["short"] = short[:64]
    r = requests.post(url, data=data, timeout=25)
    r.raise_for_status()
    return r.json()
