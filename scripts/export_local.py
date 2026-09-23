#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_local.py — local 模式产出岗位表（daily-job-push 专用）

用法:
  python3 export_local.py --jobs new_jobs.json --outdir . [--date 2026-09-22]

输入:
  new_jobs.json  由 dedup_keys.py 产出：[{岗位名称, 公司名称, ...}, ...]

输出三个文件（同目录，字段口径与飞书表完全一致）:
  jobs-YYYY-MM-DD.md      人读表格（岗位名是超链接）
  jobs-YYYY-MM-DD.csv     可导入飞书多维表格 / Excel / Notion
  jobs-YYYY-MM-DD.ndjson  机器读，供下次运行 --existing 去重（别删）
"""
import argparse
import csv
import datetime
import json
import pathlib

FIELDS = ["岗位名称", "公司名称", "招聘链接", "薪资范围", "工作地点",
          "来源平台", "状态", "匹配理由", "岗位要点", "备注",
          "发布日期", "投递反馈"]

MD_COLS = ["岗位名称", "公司名称", "薪资范围", "工作地点", "来源平台",
           "状态", "匹配理由", "岗位要点", "备注"]


def cell(s: str) -> str:
    """Markdown 表格单元格转义"""
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", required=True, help="new_jobs.json")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    a = ap.parse_args()

    jobs = json.load(open(a.jobs, encoding="utf-8"))
    rows = []
    for j in jobs:
        r = {k: (j.get(k) or "") for k in FIELDS}
        r["状态"] = r["状态"] or "待投递"
        r["发布日期"] = r["发布日期"] or a.date
        rows.append(r)

    d = pathlib.Path(a.outdir)
    d.mkdir(parents=True, exist_ok=True)
    base = f"jobs-{a.date}"
    md_p, csv_p, nd_p = d / f"{base}.md", d / f"{base}.csv", d / f"{base}.ndjson"

    with open(csv_p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    lines = [
        f"# 岗位搜集 {a.date}",
        "",
        f"共 {len(rows)} 条 · 状态一律「待投递」，投不投自己筛",
        "",
        "| " + " | ".join(MD_COLS) + " |",
        "|" + "---|" * len(MD_COLS),
    ]
    for r in rows:
        cells = []
        for col in MD_COLS:
            v = r.get(col, "")
            if col == "岗位名称" and r.get("招聘链接"):
                url = r["招聘链接"].replace("|", "%7C")
                cells.append(f"[{cell(v)}]({url})")
            else:
                cells.append(cell(v))
        lines.append("| " + " | ".join(cells) + " |")
    md_p.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(nd_p, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"fields": r}, ensure_ascii=False) + "\n")

    print(f"新增 {len(rows)} 条")
    print("人读表格:", md_p.resolve())
    print("导入用表:", csv_p.resolve())
    print("去重底表:", nd_p.resolve(), "（下轮 --existing 指向它）")


if __name__ == "__main__":
    main()
