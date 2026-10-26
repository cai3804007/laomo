"""用订阅号后台的「超链接」接口，列出任意公众号的历史文章。

这是微信公众平台的内部接口，不是公开 API：
- **有严格频率限制**。连续快速请求会返回 ret=200013 freq control，
  之后要等几小时甚至 24 小时。所以默认每页间隔 8-15 秒随机，别调小。
- token/cookie 有效期大约几小时到几天，过期重新登录拿。
- count 最大给 5 最稳，给大了更容易触发风控。
"""
import random, time, requests
from mp import auth

BASE = "https://mp.weixin.qq.com/cgi-bin"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")

RET_MSG = {
    200013: "触发频率限制(freq control)。停手等几小时，别重试——越试锁越久。",
    200003: "登录态失效，重新登录后台再抓一次 cURL。",
    200002: "参数错误（fakeid 或 token 不对）。",
    -99999: "未知错误，多半是 cookie 不完整。",
}


def _get(path: str, params: dict, cred: dict) -> dict:
    r = requests.get(f"{BASE}/{path}", params={**params, "token": cred["token"],
                                               "lang": "zh_CN", "f": "json", "ajax": "1"},
                     headers={"User-Agent": UA, "Cookie": cred["cookie"],
                              "Referer": f"{BASE}/appmsg?t=media/appmsg_edit&token={cred['token']}"},
                     timeout=30)
    r.raise_for_status()
    d = r.json()
    ret = d.get("base_resp", {}).get("ret", 0)
    if ret != 0:
        raise RuntimeError(f"接口返回 ret={ret}: "
                           f"{RET_MSG.get(ret, d.get('base_resp', {}).get('err_msg', ''))}")
    return d


def search_biz(name: str, cred: dict | None = None) -> list[dict]:
    """按名称搜公众号，返回候选（含 fakeid）。"""
    cred = cred or auth.load()
    d = _get("searchbiz", {"action": "search_biz", "begin": 0, "count": 5, "query": name}, cred)
    return [{"fakeid": x["fakeid"], "nickname": x["nickname"], "alias": x.get("alias", "")}
            for x in d.get("list", [])]


def articles(fakeid: str, limit: int = 1, cred: dict | None = None,
             delay: tuple[float, float] = (8, 15), count: int = 1) -> list[dict]:
    """拉文章列表。

    注意：count 调小**不能**绕过限流——风控看的是请求次数，不是返回条数。
    拉 1 条和拉 5 条同样消耗一次配额。count=1 的意义只是在够用时少拿点数据。
    真正省配额的是 limit<=count，这样只发一次请求、完全不翻页。
    """
    cred = cred or auth.load()
    out, begin = [], 0
    while len(out) < limit:
        d = _get("appmsg", {"action": "list_ex", "begin": begin, "count": count,
                            "fakeid": fakeid, "type": 9, "query": ""}, cred)
        page = d.get("app_msg_list", [])
        if not page:
            break
        for a in page:
            out.append({"title": a["title"], "link": a["link"],
                        "create_time": a["create_time"], "digest": a.get("digest", "")})
        begin += len(page)
        total = d.get("app_msg_cnt", 0)
        print(f"      已取 {len(out)}/{min(limit, total) or limit} 条")
        if begin >= total:
            break
        if len(out) < limit:
            time.sleep(random.uniform(*delay))   # 必须慢，否则触发风控
    return out[:limit]
