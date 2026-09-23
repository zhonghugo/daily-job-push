# 「岗位机会」表字段规范（daily-job-push）

> 目标表由**使用者自己提供或新建**，token 存在 `~/.workbuddy/daily-job-push/target.json`，**不写在本文件里**（技能目录不含个人数据）。
> 本文件只规定**字段结构**，保证写入不报错。

## 表标识（运行时从配置读）

```bash
BASE=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['base_token'])")
TBL=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['table_id'])")
TABLE_URL=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['table_url'])")
```

没有 target.json → 走 `onboarding.md` 引导（用户已有表就取链接；没有就新建）。

## 字段清单（12 个；技能写入 11 个，唯一人工专属字段是「投递反馈」）

| 字段 | 类型 | 技能写入 | 规范 |
|---|---|---|---|
| 岗位名称 | text | ✅ | 平台原始标题，不润色（保留薪资/年限后缀） |
| 公司名称 | text | ✅ | 简称去后缀（"XX科技有限公司"→"XX科技"） |
| 招聘链接 | text | ✅ | **去重键主来源**，写明细页 URL 原文；拿不到就留空 |
| 薪资范围 | text | ✅ | 平台原文（`15-25K` / `2-4万`），换算后可加注释 |
| 工作地点 | text | ✅ | 城市+区域，页面没写就留空 |
| 来源平台 | select | ✅ | 只能写：`BOSS直聘` / `猎聘` / `前程无忧` / `智联招聘` / `脉脉` / `官网`（白名单外的来源不入库） |
| 状态 | select | ✅ | **新记录一律 `待投递`**。人工流转值：`已投递` / `待跟进` / `不合适` / `已关闭`——技能不得改动这些状态 |
| 匹配理由 | text | ✅ | 一句话：为何与画像相关（≤30 字） |
| 备注 | text | ✅ | 抓取时间 + 搜索词，如 `2026-09-22 10:00 · "深圳 AI应用 招聘"` |
| 发布日期 | date | ✅ | 语义为"入表日前"（沿用本表惯例）——写运行当日；抓到页面真实发布日期时写真实值并在备注说明 |
| 岗位要点 | text | ✅ | **AI 提炼的 JD 要点**：职责 + 硬性要求，≤60 字；只写页面里有的内容，不编造；抓不到就留空 |
| 投递反馈 | text | ❌ | **唯一的人工专属字段**（用户手写投递结果），技能写入时一律留空 |

## lark-cli 常用命令

```bash
# 读（分页拉全量，ndjson 落盘）
lark-cli base +record-list --base-token $BASE --table-id $TBL \
  --page-size 200 --format ndjson --output existing.ndjson --as user

# 写单条
lark-cli base +record-create --base-token $BASE --table-id $TBL --as user \
  --fields '{"岗位名称":"...","公司名称":"...","招聘链接":"...","薪资范围":"...","工作地点":"...","来源平台":"BOSS直聘","状态":"待投递","匹配理由":"...","备注":"..."}'

# 批量写多条：+record-batch-create --records '<json数组>'，每批 ≤200 条、串行执行
#   先小批试 1 条，确认字段名无误再放量（字段名不匹配会整批失败）

# 回读验证：重复 record-list，diff 新增条数与链接集合
```

写入前若不确定字段名，先 `lark-cli base +field-list --base-token $BASE --table-id $TBL --as user` 核对——**字段名不匹配会整批失败**。

## 去重键口径

1. **主键**：`招聘链接` 规范化——去 query/fragment/utm、小写 host、去尾斜杠。同页不同参数视为同一条
2. **退化键**（链接为空时）：`规范(公司名称) + 规范(岗位名称)`——去空格/标点、去括号内容、小写
3. 命中任一键即视为重复，不入库；`scripts/dedup_keys.py` 已实现，勿在别处重写

## 谁写哪个字段（口径，勿混）

- **AI 写**：岗位名称、公司名称、招聘链接、薪资范围、工作地点、来源平台、状态（一律「待投递」）、匹配理由、岗位要点、备注、发布日期
- **人写**：投递反馈（以及状态的后续流转：已投递 / 待跟进 / 不合适 / 已关闭）
- 「岗位要点」是 **AI 总结**，不是原文粘贴——提炼该 JD 最关键的职责与硬性要求，写给人快速判断用
