"""凭证探测：不依赖任何 UI 入口，直接验证 token+cookie 能否调通接口。

用法三选一：
  1) ./.venv/bin/python mp/probe.py <curl文件>       从 Copy as cURL 提取
  2) ./.venv/bin/python mp/probe.py --token 123 --cookie "a=b; c=d"
  3) ./.venv/bin/python mp/probe.py                  用已保存的 .mp_cred.json
验证通过会自动保存凭证。
"""
import argparse, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp import auth, listing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("curlfile", nargs="?")
    ap.add_argument("--token"); ap.add_argument("--cookie")
    ap.add_argument("--cookie-file", help="从文件读 cookie，避免进 shell 历史")
    ap.add_argument("--query", default="韭菜老墨")
    a = ap.parse_args()

    if a.curlfile:
        cred = auth.from_curl(pathlib.Path(a.curlfile).read_text())
    elif a.token and a.cookie_file:
        from mp.login import normalize
        raw = pathlib.Path(a.cookie_file).read_text()
        cred = {"token": a.token.strip(), "cookie": normalize(raw)}
    elif a.token and a.cookie:
        from mp.login import normalize
        cred = {"token": a.token.strip(), "cookie": normalize(a.cookie)}
    else:
        cred = auth.load()
    print(f"  token={cred['token']}  cookie {len(cred['cookie'])} 字符")

    ck = cred["cookie"]
    missing = [k for k in ("slave_sid", "slave_user", "bizuin") if k not in ck]
    if missing:
        print(f"  ⚠️ cookie 里缺少 {missing} —— 多半复制不全，接口大概率会失败")

    print(f"\n  调 searchbiz 搜「{a.query}」…")
    try:
        hits = listing.search_biz(a.query, cred)
    except Exception as e:
        print(f"  ❌ {e}")
        return 1
    if not hits:
        print("  接口通了，但没搜到这个号 —— 换个关键词试试")
    else:
        print(f"  ✅ 接口通了，{len(hits)} 个结果：")
        for h in hits:
            print(f"      {h['nickname']}  (alias={h['alias'] or '无'})  fakeid={h['fakeid']}")
    auth.save(cred)
    print(f"\n  凭证已保存 → {auth.CRED}")
    print(f"  下一步: ./.venv/bin/python mp/daily.py --fakeid {hits[0]['fakeid'] if hits else '<fakeid>'} --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
