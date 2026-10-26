"""从浏览器 DevTools 复制的 cURL 命令里提取 token + cookie。

手抄 cookie 容易漏字段。正确姿势：
登录 mp.weixin.qq.com 后台 → F12 → Network → 在编辑器里点一次「超链接」搜索 →
找到 searchbiz 或 appmsg 请求 → 右键 Copy → Copy as cURL → 整段存成文件。
"""
import json, pathlib, re

CRED = pathlib.Path(__file__).resolve().parent.parent / ".mp_cred.json"


def from_curl(text: str) -> dict:
    tok = re.search(r"[?&]token=(\d+)", text)
    ck = re.search(r"-H\s+['\"]?[Cc]ookie:\s*([^'\"]+)['\"]?", text) \
         or re.search(r"-b\s+['\"]([^'\"]+)['\"]", text)
    if not tok:
        raise ValueError("没找到 token（URL 里应有 token=数字）")
    if not ck:
        raise ValueError("没找到 cookie（应有 -H 'Cookie: ...' 或 -b '...'）")
    return {"token": tok.group(1), "cookie": ck.group(1).strip()}


def save(cred: dict) -> None:
    CRED.write_text(json.dumps(cred, ensure_ascii=False, indent=2))
    CRED.chmod(0o600)          # 这是登录态，等同密码


def load() -> dict:
    if not CRED.exists():
        raise RuntimeError(f"没有凭证。先运行：./.venv/bin/python mp/auth.py <curl文件>")
    return json.loads(CRED.read_text())


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(2)
    c = from_curl(pathlib.Path(sys.argv[1]).read_text())
    save(c)
    print(f"已保存 token={c['token']}  cookie {len(c['cookie'])} 字符 → {CRED}")
