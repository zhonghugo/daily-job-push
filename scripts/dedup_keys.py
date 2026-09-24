#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedup_keys.py — 岗位去重 + 明细页链接判定（daily-job-push 专用）

用法:
  # 1) 判定单条链接是明细页还是搜索/列表页
  python3 dedup_keys.py --check-link "https://www.liepin.com/job/1961234567.shtml"

  # 2) 用已有记录做去重，筛出真正的新岗位
  python3 dedup_keys.py --existing existing.ndjson --candidates candidates.json --out new_jobs.json

existing.ndjson  : lark-cli base +record-list --format ndjson 的导出（字段平铺，含 record_id 亦可）
candidates.json  : [{"岗位名称":"..","公司名称":"..","招聘链接":"..","薪资范围":"..", ...}, ...]
"""
import argparse, json, re, sys
from urllib.parse import urlparse, unquote

SEARCH_HINTS = ("query=", "key=", "keyword=", "searchword=", "search=", "/so/", "/sou/", "/list/", "/zhaopin/", "/search")
BOT_HOSTS = ("sou.zhipin.com", "we.51job.com", "www.zhaopin.com/sou")

# 各平台明细页的 URL 特征（按域名登记；新增平台时在此追加一行即可）
DETAIL_PATTERNS = {
    "zhipin.com":   r"/job_detail/",
    "liepin.com":   r"/(job|lptjob|a)/\d+",
    "maimai.cn":    r"/(web/job/|web/feed/detail)",
    "51job.com":    r"(job\d+\.html|/\d+\.html|/jobs/[^/]+/\d+\.html)",
    "zhaopin.com":  r"(/cc[a-z]?\d+j\d+\.htm|/job/[a-z0-9]{6,})",
    # —— 公司官网 / 官方招聘系统（域名与明细页形态都要核验，防假冒站）——
    "tencent.com":     r"/jobdesc\.html",
    "sf-express.com":  r"/searchjobsearchbyid/\d+",
    "crc.com.cn":      r"/jobdetail|/position/\d+",
    # —— 垂直 / 转载 / 聚合站（JD 完整，可当明细页用，写入时备注注明来源）——
    "yingjiesheng.com": r"/job-",
    "bebee.com":        r"/(cn|tw|hk|sg)/jobs/.+",
    "rpa-learning.com": r"/jobs/.+",
    "gdrc.org.cn":      r"/job/detail-?\d+",
    "jrzp.com":         r"/job\d+\.shtml",
    "quanzhi.com":      r"/job/(detail/)?[a-z0-9]{6,}",
    "qcc.com":          r"/jobdetail/[a-z0-9]{16,}",
    "yl1001.com":       r"jobdetail_\d+",
}
# 官网直招的通用明细页特征（路径里出现即视为职位详情，命中在 SEARCH_HINTS 之后判定）
OFFICIAL_DETAIL_HINTS = r"(jobdesc\.html|/jobdetail|/job-detail|/job_desc|/position/\d+)"

def norm_link(url: str) -> str:
    """去 query/fragment、去 www、小写 host、去尾斜杠 —— 同页不同参数视为同一条"""
    if not url:
        return ""
    url = url.strip()
    p = urlparse(url if "://" in url else "http://" + url)
    host = (p.netloc or "").lower()
    host = re.sub(r"^www\.", "", host)
    path = re.sub(r"/+$", "", p.path or "")
    return f"{host}{path}"

def norm_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[（(【\[].*?[)）】\]]", "", s)          # 去括号内容
    s = re.sub(r"(有限公司|股份有限公司|科技公司|公司)$", "", s)
    s = re.sub(r"[\s\-_/·、,，.。·]+", "", s)
    return s

def keys_of(job: dict):
    """返回该岗位的全部去重键（命中任一即重复）"""
    ks = []
    lk = norm_link(job.get("招聘链接") or job.get("链接") or "")
    if lk:
        ks.append("L:" + lk)
    com, pos = norm_text(job.get("公司名称", "")), norm_text(job.get("岗位名称", ""))
    if com and pos:
        ks.append("T:" + com + "|" + pos)
    return ks

def check_link(url: str) -> str:
    """detail 明细页 / search 搜索或列表页 / unknown 无法判定"""
    if not url:
        return "unknown"
    low = url.lower()
    parsed = urlparse(low if "://" in low else "http://" + low)
    host = parsed.netloc
    path = unquote(parsed.path or "")      # 解码 %XX —— 中文/长链接 slug 也能正确判定
    # 先按域名白名单判定（域名内只有登记的形态才算明细页），再看全局搜索特征
    for dom, pat in DETAIL_PATTERNS.items():
        if dom in host:
            return "detail" if re.search(pat, path) else "search"
    if any(h in host for h in BOT_HOSTS) or any(h in low for h in SEARCH_HINTS):
        return "search"
    if re.search(OFFICIAL_DETAIL_HINTS, path):
        return "detail"
    # 通用：路径里带长数字/哈希 id 视为明细页（含纯数字自增 id 与 hex 哈希 id 两种形态）
    return "detail" if re.search(r"/[a-z0-9_-]*\d{6,}", path) or re.search(r"/[a-f0-9]{16,}", path) else "unknown"

def load_existing(path: str):
    keys = set()
    n = 0
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        f = rec.get("fields", rec)          # 兼容嵌套导出
        if not isinstance(f, dict):
            continue
        keys.update(keys_of(f))
        n += 1
    return keys, n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-link")
    ap.add_argument("--existing")
    ap.add_argument("--candidates")
    ap.add_argument("--out", default="new_jobs.json")
    a = ap.parse_args()

    if a.check_link:
        print(check_link(a.check_link))
        return
    if not a.existing or not a.candidates:
        sys.exit("需要 --existing 与 --candidates（或 --check-link）")

    keys, n = load_existing(a.existing)
    cands = json.load(open(a.candidates, encoding="utf-8"))
    kept, leads, dup, bad = [], [], [], []
    for j in cands:
        link = (j.get("招聘链接") or "").strip()
        kind = check_link(link) if link else "detail"      # 无链接直接按线索处理
        if kind == "search":
            bad.append((j.get("岗位名称", "?"), link))     # 真搜索/列表页，丢弃
            continue
        if kind == "unknown" and link:
            # 聚合页/文库页 → 降级为线索：清空链接，备注标注（去重自动退化为「公司+岗位」键）
            j = dict(j, 招聘链接="")
            j["备注"] = (j.get("备注", "") + " · 线索待补（原链接为聚合页）").strip(" ·")
            leads.append(j.get("岗位名称", "?"))
        jk = keys_of(j)
        if not jk:
            bad.append((j.get("岗位名称", "?"), "无可用去重键"))
            continue
        if any(k in keys for k in jk):
            dup.append(j.get("岗位名称", "?"))
            continue
        kept.append(j)
        keys.update(jk)                     # 同批内也去重

    json.dump(kept, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"已有记录 {n} 条（去重键 {len(keys)} 个）")
    print(f"候选 {len(cands)} → 入库 {len(kept)}（其中线索待补 {len(leads)}）"
          f"｜重复丢弃 {len(dup)}｜无效丢弃 {len(bad)}")
    for p in leads[:5]:
        print("  线索:", p)
    for p in dup[:8]:
        print("  重复:", p)
    for p, r in bad[:8]:
        print("  丢弃:", p, "->", (r or "")[:70])
    print("已写出:", a.out)

if __name__ == "__main__":
    main()
