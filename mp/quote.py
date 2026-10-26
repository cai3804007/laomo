"""代号解码 + 行情查询。

作者把股票代码拆成两半藏在昵称里：「白娘子（L601）的对手中原法海（M866）」
→ L601 + M866 → 601866。字母是障眼法，按出现顺序拼接数字即可。
"""
import re, requests

CODE_HINT = re.compile(r"[A-Za-z](\d{3})")


def decode(text: str) -> str | None:
    """从正文里还原 6 位股票代码。"""
    parts = CODE_HINT.findall(text)
    seen = list(dict.fromkeys(parts))          # 去重保序
    for i in range(len(seen) - 1):
        code = seen[i] + seen[i + 1]
        if re.fullmatch(r"(60|68|00|30)\d{4}", code):
            return code
    return None


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
