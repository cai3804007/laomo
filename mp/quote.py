"""代号解码 + 行情查询。

作者把股票代码拆成两半藏在昵称里：「白娘子（L601）的对手中原法海（M866）」
→ L601 + M866 → 601866。字母是障眼法，按出现顺序拼接数字即可。
"""
import json, pathlib, re, requests

ROOT = pathlib.Path(__file__).resolve().parent.parent

CODE_HINT = re.compile(r"[A-Za-z](\d{3})")


def aliases() -> dict:
    f = ROOT / "aliases.json"
    return json.loads(f.read_text(encoding="utf-8"))["map"] if f.exists() else {}


def decode(text: str) -> str | None:
    """还原股票代码。优先用型号，拿不到再查化名对照表。

    有些文章（如 10-26 卖出+买入合并篇）全程只用化名不给型号，
    型号匹配会返回 None——这时靠 aliases.json 这本词典兜底。
    """
    return decode_all(text)[0] if decode_all(text) else None


def decode_all(text: str) -> list[str]:
    """返回文中出现的全部标的代码，按出现顺序。一篇多标的时有用。"""
    found = []

    # 1) 型号：L601 + M628 → 601628
    parts = list(dict.fromkeys(CODE_HINT.findall(text)))
    for i in range(len(parts) - 1):
        code = parts[i] + parts[i + 1]
        if re.fullmatch(r"(60|68|00|30)\d{4}", code) and code not in found:
            found.append(code)

    # 2) 化名对照表兜底，按化名在文中首次出现的位置排序
    hits = [(text.index(k), v["code"]) for k, v in aliases().items() if k in text]
    for _, code in sorted(hits):
        if code not in found:
            found.append(code)
    return found


def market(code: str) -> str:
    return ("sh" if code.startswith(("60", "68")) else "sz") + code


def quote(code: str) -> dict | None:
    """新浪行情。返回名称和实时价；非交易时段给的是最近收盘。"""
    r = requests.get(f"https://hq.sinajs.cn/list={market(code)}",
                     headers={"Referer": "https://finance.sina.com.cn"}, timeout=15)
    r.encoding = "gbk"
    m = re.search(r'="([^"]*)"', r.text)
    if not m or not m.group(1):
        return None
    f = m.group(1).split(",")
    if len(f) < 32:
        return None
    return {"code": code, "name": f[0], "open": float(f[1]), "prev_close": float(f[2]),
            "price": float(f[3]), "high": float(f[4]), "low": float(f[5]),
            "date": f[30], "time": f[31]}
