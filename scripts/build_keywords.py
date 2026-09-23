#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_keywords.py — 由求职画像生成「城市 × 方向」搜索关键词（已用真实画像测试）

用法:
  python3 build_keywords.py --profile profile.json --out keywords.txt [--per-city 8]
输出: 每行一个关键词，按平台通用（搜索时再拼平台限定词）。
"""
import argparse, json, re, sys

# 方向近义词展开：一个方向生成多个搜索变体
SYNONYMS = {
    "AI应用": ["AI应用", "AI落地", "AIGC应用"],
    "RPA": ["RPA", "流程自动化", "机器人流程"],
    "数字化转型": ["数字化转型", "信息化", "数字化"],
    "AI产品": ["AI产品", "大模型产品", "AI产品经理"],
    "数据运营": ["数据运营", "业务数据分析"],
    "流程管理": ["流程管理", "业务流程"],
    "Agent": ["AI Agent", "智能体"],
}

STOP_PARTS = {"落地", "应用", "方向", "岗位", "工作", "经理", "相关", "领域"}

def variants(direction: str):
    """把一个方向拆成若干搜索变体：先按 / 、 分隔，再做近义词展开"""
    parts = [p.strip() for p in re.split(r"[/、|,，]", direction) if p.strip()]
    out = []
    for p in parts:
        if p not in out and p not in STOP_PARTS:
            out.append(p)
        for k, vs in SYNONYMS.items():
            if k.lower() in p.lower():
                for v in vs:
                    if v not in out and v not in STOP_PARTS:
                        out.append(v)
    return out or [direction]

def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", default="keywords.txt")
    ap.add_argument("--per-city", type=int, default=8, help="每城市最多保留关键词数")
    a = ap.parse_args()

    p = json.load(open(a.profile, encoding="utf-8"))
    directions, cities = p.get("directions") or [], p.get("cities") or []
    if not directions or not cities:
        sys.exit("画像缺必填字段: directions / cities")
    sal = ""
    if p.get("salary_min") and p.get("salary_max"):
        sal = f" {p['salary_min']}-{p['salary_max']}K"

    seen, per_city = set(), {}
    lines = []
    for city in cities:
        cnt = 0
        for d in directions:
            for v in variants(d):
                kw = f"{city} {v} 招聘"
                key = norm(kw)
                if key in seen:
                    continue
                seen.add(key)
                lines.append(kw)
                cnt += 1
        per_city[city] = cnt

    # 每城市截断到 --per-city，优先保留靠前方向（画像顺序即优先级）
    if a.per_city and a.per_city > 0:
        kept, drop = [], 0
        counters = {c: 0 for c in cities}
        for kw in lines:
            c = kw.split()[0]
            if counters[c] >= a.per_city:
                drop += 1
                continue
            counters[c] += 1
            kept.append(kw)
        lines = kept

    open(a.out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"关键词 {len(lines)} 条（每城市 ≤{a.per_city}）→ {a.out}")
    for kw in lines[:10]:
        print("  ", kw)
    if len(lines) > 10:
        print(f"   ... 共 {len(lines)} 条")

if __name__ == "__main__":
    main()
