"""URL 接收端：任何能拿到公众号文章链接的东西，POST 过来就自动分析。

把「捕获」和「分析」解耦——可爱猫 / WeChatFerry / iOS 快捷指令 / curl
都只需要 POST 一个 URL，分析端不用改。

  curl -X POST http://<mac-ip>:8765/hook -d 'url=https://mp.weixin.qq.com/s/xxx'

也接受可爱猫那种整包 JSON（自动从任意字段里把链接抠出来）。
"""
import json, re, sys, pathlib, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp.watch import URL_RE, seen, remember, handle, notify_mac

PUSH = False
TOKEN = None          # 设了就要求 ?token= 匹配，防内网里被乱调


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 默认日志太吵
        pass

    def _reply(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(200, {"ok": True, "seen": len(seen())})

    def do_POST(self):
        if TOKEN and f"token={TOKEN}" not in (self.path or ""):
            return self._reply(403, {"error": "bad token"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace") if n else ""

        # 不管对方发 form、JSON 还是整包事件，统一用正则捞链接
        url = None
        if (m := URL_RE.search(raw)):
            url = m.group(0)
        elif raw.startswith("{"):
            try:
                url = URL_RE.search(json.dumps(json.loads(raw), ensure_ascii=False)).group(0)
            except Exception:
                pass
        elif "=" in raw:
            v = parse_qs(raw).get("url", [""])[0]
            url = m.group(0) if (m := URL_RE.search(v)) else None

        if not url:
            return self._reply(400, {"error": "没找到 mp.weixin.qq.com 文章链接"})
        if url in seen():
            return self._reply(200, {"ok": True, "skipped": "已处理过", "url": url})

        self._reply(202, {"ok": True, "accepted": url})   # 先应答，别让对方等
        threading.Thread(target=self._work, args=(url,), daemon=True).start()

    def _work(self, url: str):
        print(f"→ {url}")
        try:
            print(handle(url, PUSH))
            remember(url)
        except Exception as e:
            print(f"  ❌ {e}")
            notify_mac("分析失败", str(e)[:80])


def main():
    import argparse, socket
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="0.0.0.0", help="默认监听所有网卡，内网可达")
    ap.add_argument("--token", help="简单鉴权，调用方需带 ?token=")
    ap.add_argument("--push", action="store_true")
    a = ap.parse_args()
    global PUSH, TOKEN
    PUSH, TOKEN = a.push, a.token

    ip = socket.gethostbyname(socket.gethostname())
    try:
        srv = ThreadingHTTPServer((a.bind, a.port), H)
    except OSError as e:
        if e.errno == 48:
            print(f"端口 {a.port} 已被占用——多半是上一个接收端还在跑。\n"
                  f"  查看: lsof -i :{a.port}\n"
                  f"  停掉: pkill -f mp/server.py\n"
                  f"  或换端口: --port {a.port + 1}")
            return 1
        raise
    print(f"接收端启动 → http://{ip}:{a.port}/hook"
          + (f"?token={a.token}" if a.token else ""))
    print(f"推送 Server酱: {'开' if PUSH else '关'}   已处理 {len(seen())} 篇\n")
    srv.serve_forever()


if __name__ == "__main__":
    sys.exit(main() or 0)
