#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""dedup_keys.py — 岗位去重归并 + 明细页链接判定（daily-job-push 专用）

用法:
  # 1) 判定单条链接是明细页还是搜索/列表页
  python3 dedup_keys.py --check-link "https://www.liepin.com/job/1961234567.shtml"

  # 2) 用已有记录做去重归并，分出「真正的新岗位」与「老岗位又出现在新渠道」
  python3 dedup_keys.py --existing existing.ndjson --candidates candidates.json \
      --out new_jobs.json [--today 2026-09-26]

existing.ndjson  : lark-cli base +record-list --format ndjson 的导出（字段平铺，含 record_id 亦可）
candidates.json  : [{"岗位名称":"..","公司名称":"..","招聘链接":"..","薪资范围":"..", ...}, ...]

产物:
  --out（默认 new_jobs.json）
      真正的新岗位，每条带 渠道数=1 与 同岗来源（格式不变，仍是数组）
  --merge-out（默认 <out> 去掉 .json + .merges.json）
      已有岗位又出现在新渠道 → 归并计划。同一岗位跨渠道出现不再丢弃，而是记进「同岗来源」
      · 有 record_id（飞书模式）→ 另写 <out> 去掉 .json + .updates.json，
        可直接作为 +record-batch-update 的 --json 请求体
      · 无 record_id（本地模式）→ 另写 merges-<today>.ndjson，
        下轮拼 existing.ndjson 时排在 jobs-*.ndjson 之后，归并后的版本天然胜出

另有一份 stdout 报告：
  · 每轮归并明细 + 五类标记（键冲突 / 同名不同限定 / 同链接重复 / 同链接但岗位名不同 / 同名待确认）
  · **存量体检**：只读列出「同一去重键挂着多条记录」的清单，不改任何记录、不产生写回体。
    老脚本没脱 markdown 链接壳，链接去重对存量记录从未生效，表里攒下了重复行——
    候选碰不到这些键就永远没人知道，故每轮全量扫一遍。清理由人做，技能不得自动删行。

⚠️ **候选命中多行时，本轮不改、只报**（stdout 的「键冲突（本轮未归并）」）：
   要么存量里本来就有重复行，要么候选自己不带限定词、看不出该落在哪一条
   （「AI产品经理」在传音有 J19661 / HR领域 / 数据运营方向 三个岗）。两种都只有人能定，
   猜测着并进其中一条 = 把来源行挂到错的岗位上，所以宁可这一轮不写。

⚠️ **T 键会用括号限定词筛行**：`norm_text` 去括号内容是为了跨平台兜底（同一岗位一边带
   req id 一边不带），代价是同公司同名不同岗共用一个键。故 T 键命中的行要先过
   `title_conflicts` ——「(J19661)」与「（HR领域）」两边都有限定词且无交集 → 不是同一岗位，
   既不算命中也不算冲突；候选因此按新岗位入库并在报告里点名（❓同名不同限定）。

⚠️ **渠道数 = 去重后的平台数**（不是来源行数）。同一平台重复见到（列表页 + 明细页，
   或隔几天又搜到）会长出第二行来源，但那不构成「跨渠道在招」的证据——按行数计会伪造信号
   （PRD 实验 1 的核心指标是「几个渠道在招」，渠道指平台）。两个数都留着：渠道数给信号，
   行数在归并明细里显示为「来源 N 条」。

⚠️ 归并只改「渠道数」「同岗来源」两个字段。绝不改 招聘链接/来源平台/状态/薪资范围：
   链接是去重键本身，改了会破坏下一轮去重；状态是人工专属，技能不得触碰。
"""
import argparse, datetime, json, os, re, sys
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

SRC_SEP = " · "          # 同岗来源 单行内的分隔符；平台/薪资/地点/链接都含不到它
MD_LINK = re.compile(r"\[[^\]]*\]\(\s*([^)\s]+)\s*\)")

def raw_url(v) -> str:
    """表里 招聘链接 存的是 markdown `[查看岗位](url)` —— 取回裸 URL 再去规范化。

    ⚠️ 不脱这层壳的话，存量记录的链接去重键会变成 `[查看岗位](https://…)` 这种废字符串，
    链接去重对存量**完全失效**，只剩「公司+岗位」兜底（实测踩过）。
    """
    s = str(v or "").strip()
    m = MD_LINK.search(s)
    return m.group(1) if m else s

def norm_link(url: str) -> str:
    """去 query/fragment、去 www、小写 host、去尾斜杠 —— 同页不同参数视为同一条"""
    if not url:
        return ""
    url = raw_url(url)
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

def paren_tokens(s) -> set:
    """岗位名里的括号限定词，如 (J19661) / （HR领域）。

    T 键故意去括号内容，是为了跨平台兜底——同一岗位一边带 req id、一边不带。
    代价是同公司同名不同岗会共用一个 T 键，靠这里把它们区分开。
    """
    return {norm_text(t) for t in re.findall(r"[（(【\[](.*?)[)）】\]]", str(s or ""))
            if norm_text(t)}

def title_conflicts(a, b) -> bool:
    """两个岗位名的基础名相同（T 键已保证）时，括号限定词是否互相排斥。

    两边都有限定词且**毫无交集** → 两个不同岗位（J19661 vs HR领域 vs 数据运营方向）；
    任一边没有限定词、或限定词有交集 → 可能是同一岗位。只在这一种情形下判"不同"，
    所以永不把两个岗位静默合成一条：拿不准就留给键冲突，报给人看。
    """
    ta, tb = paren_tokens(a), paren_tokens(b)
    return bool(ta and tb and not (ta & tb))

def title_uncertain(a, b) -> bool:
    """T 键命中、却看不出是不是同一个岗位：限定词毫无交集且至少一边有。

    「一边带 req id、一边不带」的同一岗位长这样，两个不同岗位（裸标题候选撞上
    「（HR领域）」行）也长这样——判断不了，所以照并但报 ❓同名待确认，让人扫一眼。
    两边限定词一致（或都没有）时不算不确定，别拿误报淹掉真报警。
    """
    ta, tb = paren_tokens(a), paren_tokens(b)
    return bool((ta | tb) and not (ta & tb))

def idx_add(m: dict, keys, i: int):
    """把下标挂到多个键上（一个键可挂多行，同 ① 的 key2rec）"""
    for k in keys:
        lst = m.setdefault(k, [])
        if i not in lst:
            lst.append(i)

def keys_of(job: dict):
    """返回该岗位的全部去重键（命中任一即视为同一个岗位）"""
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

# ———————————————— 同岗来源：格式与读写 ————————————————

def one(v):
    """select 字段回读时可能是数组，取第一个值"""
    if isinstance(v, (list, tuple)):
        return v[0] if v else ""
    return v or ""

def as_day(v, fallback: str) -> str:
    """发布日期 回读可能是 '2026-09-23 21:30' / epoch(秒或毫秒) / 空 —— 一律裁成 YYYY-MM-DD"""
    if isinstance(v, (int, float)) and v > 0:
        ts = v / 1000 if v > 1e11 else v
        try:
            return datetime.date.fromtimestamp(ts).isoformat()
        except (OSError, OverflowError, ValueError):
            return fallback
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v or ""))
    return m.group(1) if m else fallback

def source_line(job: dict, day: str) -> str:
    """同岗来源 的一行：`[首次见到] 平台 · 薪资原文 · 地点原文 · 链接`（链接存裸 URL）"""
    return SRC_SEP.join([
        f"[{day}] {one(job.get('来源平台')) or '-'}",
        str(one(job.get("薪资范围")) or "-"),
        str(one(job.get("工作地点")) or "-"),
        raw_url(job.get("招聘链接") or job.get("链接")) or "-",
    ])

def parse_sources(text) -> list:
    """同岗来源 文本 → 行列表（空行丢弃）"""
    return [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]

def source_id_of_line(line: str) -> str:
    """从一行里还原来源身份，用于判重（同一来源再见到就不重复记）"""
    m = re.match(r"^\[[^\]]*\]\s*", line)
    parts = (line[m.end():] if m else line).split(SRC_SEP)
    url = raw_url(parts[-1]) if len(parts) >= 4 else ""
    if url and url != "-":
        return "L:" + norm_link(url)
    return "P:" + (parts[0].strip() if parts else "?")

def source_id(job: dict) -> str:
    """本条候选的来源身份：有链接按链接，无链接退化为平台名"""
    lk = norm_link(job.get("招聘链接") or job.get("链接") or "")
    return "L:" + lk if lk else "P:" + str(one(job.get("来源平台")) or "?")

def platform_of_line(line: str) -> str:
    """从一行来源里取出平台名（`[首次见到] 平台 · 薪资 · 地点 · URL` 的第 2 段）"""
    m = re.match(r"^\[[^\]]*\]\s*", line)
    parts = (line[m.end():] if m else line).split(SRC_SEP)
    return parts[0].strip() if parts else "?"

def channels_of(lines: list) -> int:
    """渠道数 = **去重后的平台数**，不是行数。

    同一平台重复见到（列表页 + 明细页，或隔几天又搜到）会长出第二行来源，但那不构成
    「跨渠道在招」的证据——按行数计会伪造信号（PRD 实验 1 的核心指标是「几个渠道在招」，
    渠道指平台）。行数另有计数，两个都留着：渠道数给信号，行数给人看热度。
    """
    return len({platform_of_line(ln) for ln in lines})

def seed_sources(fields: dict, day: str) -> list:
    """老记录的 同岗来源 若为空（历史数据），用记录自身字段补一条，保证口径一致"""
    return parse_sources(fields.get("同岗来源")) or [source_line(fields, as_day(fields.get("发布日期"), day))]

def merge_source(lines: list, job: dict, day: str):
    """把候选的来源并入 lines。返回 (lines, 状态) —— 状态: new / repeat"""
    sid = source_id(job)
    if any(source_id_of_line(ln) == sid for ln in lines):
        return lines, "repeat"
    return lines + [source_line(job, day)], "new"

# ———————————————— 已有记录索引 ————————————————

def load_existing(path: str):
    """返回 (key2rec, n)。key2rec: 去重键 -> [{"_id","record_id","fields"}, …]（按读入顺序）

    **每个键存列表**，两个原因：
    1. last-wins 由调用方取 `[-1]` 实现——本地模式把 merges-*.ndjson 拼在
       jobs-*.ndjson 之后，归并后的新版本因此天然胜出（append-only 的更正日志）
    2. 列表长度 >1 才看得见**同一个键下的重复行**。若只留最后一条，存量重复行会被
       悄悄吞掉——而它们正是「⚠️ 键冲突」要报的东西（老脚本链接键失效留下的）
    """
    key2rec, n = {}, 0
    for ln_no, line in enumerate(open(path, encoding="utf-8"), 1):
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
        n += 1
        entry = {
            "_id": rec.get("record_id") or f"{os.path.basename(path)}:{ln_no}",
            "record_id": rec.get("record_id"),
            "fields": f,
        }
        for k in keys_of(f):
            key2rec.setdefault(k, []).append(entry)
    return key2rec, n

def audit_existing(key2rec):
    """存量体检：同一个去重键下挂着多条**带 record_id** 的记录。

    老脚本没脱 markdown 壳，链接去重对存量记录从未生效（只剩「公司+岗位」兜底），
    表里因此攒下了重复行。一个去重键下挂着多行时，命中该键的候选整条都不归并（本轮
    只报），所以脏行会一直挡住跨渠道信号；候选碰不到这些键就更没人知道了——故装载时
    全量体检一次。只读，不产生任何写回体。

    分两档，因为处置方式不同：
      · 同链接（L 键）——同一条 URL 挂在多行上。**再按岗位名分**：
          岗位名相同 → 多半是重复行（历次重跑把公司名写飘了），可直接合并；
          岗位名不同 → 链接可能配错了（一行挂着别家的岗位），必须核对
      · 同名待查（T 键）——公司+岗位名同但链接不同，**可能是两个岗位**，得看一眼；
          组内两两括号限定词互斥的（J19661 / HR领域 / 数据运营方向）只是共用宽键的
          不同岗位，不是重复，不报

    返回 (同链接, 同名待查)，元素为 (键, [(记录, 岗位名是否一致)…])。
    """
    by_link, by_title, seen = [], [], set()
    for k, lst in sorted(key2rec.items()):
        rows = [e for e in lst if e["record_id"]]
        ids = frozenset(e["_id"] for e in rows)
        if len(ids) > 1 and ids not in seen:
            seen.add(ids)     # 同一批行可能同时踩中 L 键和 T 键，只报一次
            if k.startswith("L:"):
                same = len({norm_text(one(e["fields"].get("岗位名称")) or "")
                            for e in rows}) == 1
                by_link.append((k, rows, same))
            else:
                titles = [one(e["fields"].get("岗位名称")) for e in rows]
                if not all(title_conflicts(titles[i], titles[j])
                           for i in range(len(titles)) for j in range(i + 1, len(titles))):
                    by_title.append((k, rows))
    return by_link, by_title

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-link")
    ap.add_argument("--existing")
    ap.add_argument("--candidates")
    ap.add_argument("--out", default="new_jobs.json")
    ap.add_argument("--merge-out")
    ap.add_argument("--today", help="运行日期 YYYY-MM-DD（默认取系统日期；仅为方便复现测试）")
    a = ap.parse_args()

    if a.check_link:
        print(check_link(a.check_link))
        return
    if not a.existing or not a.candidates:
        sys.exit("需要 --existing 与 --candidates（或 --check-link）")

    today = a.today or datetime.date.today().isoformat()
    stem = re.sub(r"\.json$", "", a.out)
    merge_out = a.merge_out or stem + ".merges.json"

    key2rec, n = load_existing(a.existing)
    cands = json.load(open(a.candidates, encoding="utf-8"))

    kept, leads, bad = [], [], []
    key2kept = {}          # 去重键 -> [kept 下标]（同批内归并；一个键可能挂多条不同岗位）
    merges, pending = [], {}   # pending: 已有记录 _id -> 归并条目（同一行被多次归并时累加）
    conflicts = {}         # 存量重复行告警，与归并解耦：候选只是重复确认时也要报出来
    n_repeat = 0           # 同一来源重复见到（不算新渠道，但证明岗位还在）
    twins = []             # 同名不同限定：T 键撞上但括号限定词互斥 → 按新岗位入库，报给人看

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

        # ① 命中已有记录 → 归并（老岗位又出现在新渠道，不再丢弃）
        # T 键去括号内容是为了跨平台兜底（同一岗位一边带 req id 一边不带），代价是
        # 同公司同名不同岗会共用一个键。逐行比括号限定词，把明确不是同一岗位的行剔掉，
        # 它们既不参与归并、也不算进「键冲突」——否则传音那 3 个岗位中任何一个候选
        # 都会命中 3 行，整条候选都落不了库（命中多行 = 本轮只报不并）。
        cand_title = one(j.get("岗位名称"))
        hits, dropped = {}, []
        for k in (k for k in jk if k in key2rec):
            if k.startswith("L:"):      # 同一 URL 即同一岗位，不筛（链接挂错由存量体检报）
                hits[k] = key2rec[k]
                continue
            keep = [e for e in key2rec[k]
                    if not title_conflicts(cand_title, one(e["fields"].get("岗位名称")))]
            keep_ids = {e["_id"] for e in keep}
            dropped += [one(e["fields"].get("岗位名称")) for e in key2rec[k]
                        if e["_id"] not in keep_ids]
            if keep:
                hits[k] = keep
        if hits:
            # 同一个键可能有多行：取最后读到的（本地模式的更正日志靠这个生效）
            win = hits[sorted(hits)[0]][-1]
            eid = win["_id"]
            # 一条岗位同时命中多条**带 record_id** 的已有记录：要么存量里本来就有重复行
            # （老脚本链接键失效留下的），要么候选本身不含限定词、无法判断落在哪一条
            # （"AI产品经理" 在传音有 J19661 / HR领域 / 数据运营方向 三个岗）。两种都
            # 只有人能定，**本轮就不动**——不猜、不合并、不产生写回体，只报出来。
            # 只认带 record_id 的：本地模式下同一个键出现多行是 merges-*.ndjson
            # 更正日志的正常形态（同一岗位的新旧版本），不是重复
            span = {e["_id"]: e for lst in hits.values() for e in lst if e["record_id"]}
            if len(span) > 1:
                # 带上每行的岗位名：命中的未必都是重复——退化键会去括号内容，
                # "AI产品经理(J19661)" 与 "AI产品经理（HR领域）" 同键却是两个岗位，
                # 不带名字用户没法判断该合哪几条
                c = conflicts.setdefault(eid, {
                    # 报的是**候选**（裸标题那个），不是它差点并进去的那一行：
                    # 用户要判断的是"这条新线索该算哪个岗位"，命中的行在下面逐条列
                    "岗位名称": cand_title or "?",
                    "公司名称": one(j.get("公司名称")),
                    "命中记录": [
                        {
                            "_id": k,
                            "岗位名称": one(e["fields"].get("岗位名称")) or "?",
                            "公司名称": one(e["fields"].get("公司名称")),
                        }
                        for k, e in sorted(span.items())
                    ],
                    "候选": [],
                })
                # 本轮不归并，候选自己的来源行就没地方写了（既非新岗位也非归并）：
                # 至少打印出来，别让这条线索无声消失
                c["候选"].append(f"{cand_title or '?'} —— {source_line(j, today)}")
                continue
            # 候选自带链接、却只靠「公司+岗位」键命中 = 同名不同链接，可能同名不同岗
            # （T 键会去括号内容，"AI产品经理(J19661)" 与 "AI产品经理（HR领域）" 同键），
            # 照并但标注，让人看一眼决定拆不拆
            ambiguous = bool(norm_link(j.get("招聘链接") or "")) and not any(
                k.startswith("L:") for k in hits) and title_uncertain(
                    cand_title, one(win["fields"].get("岗位名称")))
            m = pending.get(eid)
            if m is None:
                m = pending[eid] = {
                    "_id": eid,
                    "_fields": win["fields"],
                    "_lines": seed_sources(win["fields"], today),
                    "_hit": set(),
                    "record_id": win["record_id"],
                    "岗位名称": one(win["fields"].get("岗位名称")) or "?",
                    "公司名称": one(win["fields"].get("公司名称")),
                    "同名待确认": ambiguous,
                }
                m["原渠道数"] = channels_of(m["_lines"])
                m["原行数"] = len(m["_lines"])
                merges.append(m)
            m["_hit"] |= set(hits)
            m["同名待确认"] = m["同名待确认"] or ambiguous
            lines, state = merge_source(m["_lines"], j, today)
            if state == "repeat":
                n_repeat += 1
                continue
            m["_lines"] = lines
            continue

        if dropped:
            twins.append((cand_title, one(j.get("公司名称")),
                          sorted({t for t in dropped if t})))

        # ② 命中本批已收的岗位 → 同批归并（同批内 T 键同样会串键，只认标题兼容的）
        same = None
        for k in jk:
            for i in reversed(key2kept.get(k, [])):
                if k.startswith("T:") and title_conflicts(
                        cand_title, one(kept[i].get("岗位名称"))):
                    continue
                same = i
                break
            if same is not None:
                break
        if same is not None:
            i = same
            lines = parse_sources(kept[i].get("同岗来源"))
            before, before_ch = len(lines), channels_of(lines)
            lines, state = merge_source(lines, j, today)
            if state == "repeat":
                n_repeat += 1
                continue
            after_ch = channels_of(lines)
            kept[i]["同岗来源"] = "\n".join(lines)
            kept[i]["渠道数"] = after_ch
            kept[i]["备注"] = (str(kept[i].get("备注", "")) +
                               f" · 同批另有来源（渠道 {before_ch}→{after_ch}"
                               f" · 来源 {before}→{len(lines)} 条）").strip(" ·")
            idx_add(key2kept, keys_of(kept[i]), i)
            continue

        # ③ 真正的新岗位
        lines = [source_line(j, today)]
        j = dict(j, 渠道数=1, 同岗来源="\n".join(lines))
        kept.append(j)
        idx_add(key2kept, jk, len(kept) - 1)

    for m in merges:                       # 收尾：算出最终要写回的字段
        lines, fields = m.pop("_lines"), m.pop("_fields")
        m["命中键"] = sorted(m.pop("_hit"))
        m["新渠道数"] = channels_of(lines)
        m["来源行数"] = len(lines)
        m["新增来源"] = lines[m["原行数"]:]
        m["更新字段"] = {"渠道数": m["新渠道数"], "同岗来源": "\n".join(lines)}
        m["合并后字段"] = {**fields, **m["更新字段"]}   # 本地模式回写用
    # 候选全部是「重复确认」的条目没有新渠道可写，丢掉，省一次无谓写回
    merges = [m for m in merges if m["新增来源"]]

    json.dump(kept, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    upd_path, local_path = None, None
    # 先清掉自己上一轮的派生产物：本轮没有归并却留着旧的 updates.json，
    # 会被下游当成"本轮写回体"原样提交（文件名固定，无法分辨新旧）
    for stale in (merge_out, stem + ".updates.json"):
        if os.path.exists(stale):
            os.remove(stale)
    if merges:
        json.dump(merges, open(merge_out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        api = [m for m in merges if m["record_id"]]
        if api:
            upd_path = stem + ".updates.json"
            json.dump({"update_records": {m["record_id"]: m["更新字段"] for m in api}},
                      open(upd_path, "w", encoding="utf-8"), ensure_ascii=False)
        local = [m for m in merges if not m["record_id"]]
        if local:
            # 追加而非覆盖：一天跑两次时，早先那次的归并结果不能被这次抹掉
            # 形状与 export_local.py 的 jobs-*.ndjson 一致（{"fields": …}），
            # 两个文件会被拼成同一个 existing.ndjson，别让下游看见两种形状
            local_path = f"merges-{today}.ndjson"
            with open(local_path, "a", encoding="utf-8") as f:
                for m in local:
                    f.write(json.dumps({"fields": m["合并后字段"]}, ensure_ascii=False) + "\n")

    n_new_ch = sum(m["新渠道数"] - m["原渠道数"] for m in merges)
    print(f"已有记录 {n} 条（去重键 {len(key2rec)} 个）")
    print(f"候选 {len(cands)} → 新岗位 {len(kept)}（其中线索待补 {len(leads)}）"
          f"｜归并老岗位 {len(merges)}（新增渠道 {n_new_ch}）"
          f"｜重复确认 {n_repeat}｜无效丢弃 {len(bad)}")
    by_link, by_title = audit_existing(key2rec)
    if by_link or by_title:
        print(f"  ── 存量体检（只读，不改记录）：{len(by_link)} 组同链接、"
              f"{len(by_title)} 组同名待查，需人工清理 ──")
        for k, rows, same_title in by_link:
            sts = sorted({one(e["fields"].get("状态")) or "?" for e in rows})
            if same_title and len(sts) > 1:
                # 同一条 URL 两行、岗位名一致，但状态是人工流转出来的两份：先定保留谁
                print(f"  ⚠️ 同链接重复但状态不同 {k[2:]}（{len(rows)} 行，岗位名一致，"
                      f"状态 {' / '.join(sts)} → 定下保留哪一份再合并）：")
            elif same_title:
                print(f"  ⚠️ 同链接重复 {k[2:]}（同一条 URL 挂在 {len(rows)} 行上，"
                      f"岗位名一致 → 多半是重复行，可直接合并）：")
            else:
                print(f"  ❗ 同链接但岗位名不同 {k[2:]}（{len(rows)} 行，"
                      f"可能有行挂错了链接，**先核对再动**）：")
            for e in rows:
                print(f"      {e['_id']}  {one(e['fields'].get('岗位名称')) or '?'} "
                      f"@{one(e['fields'].get('公司名称'))}")
        for k, rows in by_title:
            print(f"  ❓ 同名待查 {k[2:]}（{len(rows)} 行，链接不同 → 可能都是不同岗位）：")
            for e in rows:
                print(f"      {e['_id']}  {one(e['fields'].get('岗位名称')) or '?'} "
                      f"@{one(e['fields'].get('公司名称'))}")
        print("      → 岗位名一致的同链接行可直接合并；岗位名不同或链接不同的先核对——"
              "退化键会去括号内容，「X(J19661)」与「X（HR领域）」同键却是两个岗位")
    for m in merges:
        flag = "  ❓同名待确认（仅公司+岗位名相同、链接不同，可能同名不同岗）" if m["同名待确认"] else ""
        # 行数与渠道数不等 = 同一平台又见到（不算跨渠道），把来源数一并打出来免得误读成漏记
        rows = (f" · 来源 {m['原行数']}→{m['来源行数']} 条"
                if m["来源行数"] != m["新渠道数"] else "")
        print(f"  归并: {m['岗位名称']} @{m['公司名称']} "
              f"渠道 {m['原渠道数']}→{m['新渠道数']}{rows}{flag}")
    for c in conflicts.values():
        # 命中多行、无法自动判断落在哪一条：本轮未归并、未产生写回体，只能人工处理
        print(f"  ⚠️ 键冲突（本轮未归并）: {c['岗位名称']} @{c['公司名称']} 同时命中 "
              f"{len(c['命中记录'])} 条已有记录：")
        for r in c["命中记录"]:
            print(f"      {r['_id']}  {r['岗位名称']} @{r['公司名称']}")
        for ln in c["候选"]:
            print(f"      ← 本轮候选（未归并）: {ln}")
        print("      → 请人工判断：这几条未必都是重复——退化键会去括号内容，"
              "「X(J19661)」与「X（HR领域）」同键却是两个岗位；"
              "确系重复的合并后，下一轮才会归并进去")
    for title, com, others in twins:
        print(f"  ❓同名不同限定: {title} @{com} —— 已有「{'、'.join(others)}」"
              f"同公司同基础岗位名但括号限定词互斥，按新岗位入库；若确为同岗请人工合并")
    for p in leads[:5]:
        print("  线索:", p)
    for p, r in bad[:8]:
        print("  丢弃:", p, "->", (r or "")[:70])
    print("已写出:", a.out, ("｜" + merge_out) if merges else "")
    if upd_path:
        print("飞书写回体:", upd_path, f"（{len(api)} 条）")
    if local_path:
        print("本地归并日志:", local_path, "（下轮拼进 existing.ndjson，排在 jobs-* 之后）")

if __name__ == "__main__":
    main()
