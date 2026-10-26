"""交互式录入登录态。cookie 不走命令行参数，避免进 shell 历史。

cookie 等同于后台登录密码，只存在本机 .mp_cred.json（权限 600）。
"""
import getpass, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from mp import auth, listing

KEY_FIELDS = ("slave_sid", "slave_user", "bizuin", "data_bizuin")


def normalize(ck: str) -> str:
    """清掉换行/制表/多余空白，剥掉可能带上的 'Cookie:' 前缀和引号。

    DevTools 里 Cookie 那行是折行显示的，复制出来常夹换行；
    getpass 又只读一行，不处理的话会被静默截断。
    """
    ck = ck.strip().strip('"\'')
    if ck.lower().startswith("cookie:"):
        ck = ck[7:]
    ck = re.sub(r"[\r\n\t]+", " ", ck)
    ck = re.sub(r"\s*;\s*", "; ", ck)
    return re.sub(r"\s{2,}", " ", ck).strip().strip(";").strip()


def main():
    print("公众号后台登录态录入\n" + "-" * 44)
    print("token：后台任意页面地址栏里 token= 后面那串数字")
    tok = (sys.argv[1] if len(sys.argv) > 1 else input("  token > ")).strip()
    if m := re.search(r"token=(\d+)", tok):
        tok = m.group(1)
    if not tok.isdigit():
        print("  token 应该是纯数字"); return 1

    print("\ncookie：F12 → Network → 刷新页面 → 点任一请求 →")
    print("        Request Headers 里的 Cookie 整行值，全选复制")
    print("        （输入时不回显，粘贴后直接回车）")
    print("        或直接输入一个文件路径（把 cookie 存成文件，避免换行被截断）")
    ck = getpass.getpass("  cookie > ").strip()

    # 输入的是文件路径就读文件——粘贴带换行时 getpass 只会读到第一行，
    # 整段 cookie 会被悄悄截断，走文件最稳。
    if ck and len(ck) < 300 and pathlib.Path(ck).expanduser().is_file():
        ck = pathlib.Path(ck).expanduser().read_text()
        print(f"  从文件读入 {len(ck)} 字符")

    ck = normalize(ck)
    if not ck:
        print("  cookie 不能为空"); return 1

    miss = [k for k in KEY_FIELDS if k not in ck]
    n_field = ck.count("=")
    print(f"\n  token={tok}  cookie {len(ck)} 字符 / 约 {n_field} 个字段")
    if len(ck) < 200:
        print("  ⚠️ 这个长度不正常，微信后台 cookie 通常上千字符")
        print("     多半是粘贴时被换行截断了 —— 改用文件方式重来")
    if miss:
        print(f"  ⚠️ 缺少关键字段 {miss}")
        print("     服务端会交叉校验多个字段，少一个就会失败。确保整行都选中了。")
        if input("  仍然继续？(y/N) ").lower() != "y":
            return 1

    cred = {"token": tok, "cookie": ck}
    print("\n  验证中：调 searchbiz 搜「韭菜老墨」…")
    try:
        hits = listing.search_biz("韭菜老墨", cred)
    except Exception as e:
        print(f"  ❌ {e}")
        print("\n  ret=200003 → 登录态不对或已过期，重新登录后台再复制一次")
        print("  ret=200013 → 触发频率限制，等几小时再试，别连续重试")
        return 1

    auth.save(cred)
    print(f"  ✅ 通了，凭证已存到 {auth.CRED}（权限 600，已在 .gitignore 里）\n")
    if hits:
        for h in hits:
            print(f"      {h['nickname']}  fakeid={h['fakeid']}")
        print(f"\n  下一步：")
        print(f"  ./.venv/bin/python mp/daily.py --fakeid {hits[0]['fakeid']} --dry-run")
    else:
        print("  接口通了但没搜到该号，换关键词：mp/probe.py --query 别的名字")
    return 0


if __name__ == "__main__":
    sys.exit(main())
