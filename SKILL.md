---
name: daily-job-push
description: 每日岗位搜集推送：解析求职画像 → 自动生成搜索关键词 → 多平台搜索在招岗位 → 去重 → 写入岗位表 → 推送当日新增摘要。有飞书环境就写进飞书多维表格并推消息，没有飞书就输出本地 Markdown/CSV 表格（两种模式搜集与去重逻辑完全一致）。画像与目标表都是外部配置，换配置就能换人跑，技能本身不含任何个人数据。当用户说"跑一次岗位推送""搜今天的岗位""搜岗位""更新岗位表""帮我每天搜岗位"时使用；也可挂成每日定时自动化。
agent_created: true
---

# daily-job-push · 每日岗位搜集推送

AI 只负责**搜集、去重、汇总、推送**；投不投、合不合适，**由人自己筛**（口径红线，任何输出不得表述为"AI 替我筛选/过滤不合适"）。

## 运行环境：开场先探测一次

**不要假设用户在飞书环境里**。正式开跑前探测一次，再决定第 2/7/9 步怎么走：

```bash
if command -v lark-cli >/dev/null 2>&1 && lark-cli auth status >/dev/null 2>&1; then
  echo "MODE=feishu"
else
  echo "MODE=local"
fi
```

| 模式 | 前提 | 岗位写到哪 |
|---|---|---|
| **feishu**（首选） | 有 `lark-cli` 且已授权 | 飞书多维表格 + 摘要推飞书消息 |
| **local**（保底） | 任何 AI 助手都能跑 | `jobs-YYYY-MM-DD.md`（表格）+ `jobs-YYYY-MM-DD.csv` |

**local 模式不是残废版**：搜集、去重、标注、摘要四件事一模一样，只是最后一步"写哪里"从飞书换成文件。切到 local 时要**主动告知用户**："当前环境没有飞书通道，我把结果整理成本地表格，可直接导入飞书/Excel。"

## 配置：跑之前必须有这些

| 配置 | 位置 | 哪些模式需要 |
|---|---|---|
| 求职画像 | `~/.workbuddy/daily-job-push/profile.json` | **两种模式都要** |
| 目标表 | `~/.workbuddy/daily-job-push/target.json` | 仅 feishu 模式 |
| 飞书授权 | `lark-cli` 已登录 | 仅 feishu 模式 |

**画像读取链**（命中第一个就用，全程引用变量，别口述转写）：

```bash
CONF="$HOME/.workbuddy/daily-job-push"
PROFILE_FILE=""
for p in "./job-profile.json" "$CONF/profile.json"; do
  [ -f "$p" ] && PROFILE_FILE="$p" && break
done
echo "画像文件: $PROFILE_FILE"
```

1. `$PWD/job-profile.json` —— 项目级覆盖（一台机器跑多套画像时用）
2. `~/.workbuddy/daily-job-push/profile.json` —— 用户级默认，**推荐**
3. 都没有 → **进第 0 步引导**，不要拿技能目录的示例硬跑

`target.json` 固定读 `~/.workbuddy/daily-job-push/target.json`。

> **设计约束**：技能目录内**不含任何个人数据**，只有 `*.example.json` 格式模板。画像与表格 token 一律放用户级目录——这样技能更新、分享给他人时都不会串数据。

## 第 0 步 · 首次使用：引导（配置缺失时才走）

**判定**：读不到 `profile.json`，或 `directions` / `cities` / `salary_min` / `salary_max` 有空值 → 进引导。

**一次问齐**下面四条（不要一问一答反复打断用户）：

1. **目标方向** —— 想做哪类岗位？2–5 个。写**职能**不写职位名（如"AI 应用落地""流程自动化"，而不是某个具体 JD 标题）
2. **意向城市** —— 哪几个？支持"远程"
3. **薪资范围** —— 期望月薪区间（单位 K），只用于打标不做硬过滤
4. **目标表** —— **仅 feishu 模式问**。已有飞书多维表格吗？有 → 要表格链接；没有 → 按字段规范帮建一张。local 模式跳过此问（结果落本地文件）

可选补充（用户不提就不主动问）：排除词（销售/保险/外包驻场）、经验档位、偏好行业、其他备注。

拿到回答后：
1. 写 `~/.workbuddy/daily-job-push/profile.json`（格式见 `references/profile-template.md`）
2. feishu 模式：写 / 建 `target.json` 与目标表（建表步骤见 `references/onboarding.md`）；local 模式：跳过，直接进主流程
3. **复述一遍配置让用户确认**，确认后再进主流程

引导话术模板、建表命令、token 提取方法 → `references/onboarding.md`

## 主流程（9 步）

### 1. 解析画像

校验必填：`directions`、`cities`、`salary_min`、`salary_max`。缺失就停，走第 0 步引导，**不要猜**。

```bash
PROFILE=$(cat "$PROFILE_FILE")
```

### 2. 准备表格（读已有记录，供第 6 步去重）

**feishu 模式**：

```bash
BASE=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['base_token'])")
TBL=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['table_id'])")

lark-cli base +record-list --base-token $BASE --table-id $TBL \
  --page-size 200 --format ndjson --output existing.ndjson --as user
```

表不存在 → 按 `references/table-schema.md` 的字段规范建（`lark-cli base +create-table`），别从零设计。

**local 模式**：读本地历史，没有就当作空表起步：

```bash
cat jobs-*.ndjson 2>/dev/null > existing.ndjson || : > existing.ndjson
```

### 3. 生成搜索关键词

```bash
python3 scripts/build_keywords.py --profile "$PROFILE_FILE" --out keywords.txt
```

规则：`城市 × 方向` 笛卡尔积 + 通用变体（"AI 应用/Agent/数字化"近义词展开），每平台取前 N 条（默认 8），去重后输出。

### 4. 搜索

用 WebSearch 逐关键词搜 `{城市} {方向} 招聘`。每个关键词至少扫 2 个平台；多关键词并行时一次不超过 3 个，防止结果互相挤占、漏扫。

⚠️ **`site:` 限定不可靠**（实测混入无关域），别依赖它，按结果形态分档：

- 明细页 → 直接收
- 聚合/文库页（`wenku.51job.com` 等）→ 提取「公司+岗位」线索，再定向搜明细页
- 转载站（应届生求职网等，JD 完整）→ 可当明细页用，备注注明来源
- 三档都无 → **链接留空入库**，备注标「线索待补」

完整降级链与实测样本见 `references/platform-rules.md`。**宁可留线索，也不要整轮零产出**；但不得为了凑数编造岗位。

### 5. 筛选（只标注，不淘汰）

对每条结果做两件标注（都不删除结果）：

- `匹配理由`：一句话说明为何与画像相关（≤30 字）
- `岗位要点`：**AI 提炼的 JD 要点**（职责 + 硬性要求，≤60 字）。只写页面上真实存在的内容，抓不到就留空——不许脑补

**不删除任何结果**——低匹配也入库，由人筛。硬排除仅限：已关闭/停招页、非明细页、重复项（第 6 步处理）。

### 6. 去重

```bash
python3 scripts/dedup_keys.py --existing existing.ndjson --candidates candidates.json --out new_jobs.json
```

去重键口径：规范化后的招聘链接（去 query/utm、统一 host）；无链接时退化为 `规范(公司名称)+规范(岗位名称)`。命中已有记录的丢弃，摘要里报"重复 N 条"。

### 7. 写入

**feishu 模式**：

```bash
lark-cli base +record-create --base-token $BASE --table-id $TBL --as user \
  --fields '{"岗位名称":"...","公司名称":"...","招聘链接":"...","薪资范围":"...","工作地点":"...","来源平台":"BOSS直聘","状态":"待投递","匹配理由":"...","岗位要点":"...","备注":"..."}'
```

字段映射严格按 `references/table-schema.md`。**状态一律「待投递」**，`发布日期` 写运行当日，`来源平台` 只能写白名单值，`备注` 记抓取时间与搜索词。

**local 模式**：

```bash
python3 scripts/export_local.py --jobs new_jobs.json --outdir .
```

产出三个文件到当前工作目录：

| 文件 | 内容 |
|---|---|
| `jobs-YYYY-MM-DD.md` | 人读表格，岗位名是超链接 |
| `jobs-YYYY-MM-DD.csv` | 可一键导入飞书多维表格 / Excel / Notion |
| `jobs-YYYY-MM-DD.ndjson` | 机器读，下轮 `--existing` 用它去重（**别删**） |

字段口径与 feishu 模式**完全一致**，别自己另起一套。

### 8. 回读验证

- **feishu**：重新拉一次 record-list，核对新增条数 == 写入条数；抽 3 条核字段完整性（链接可打开、薪资非空）
- **local**：重读两个产出文件，核对行数与写入条数一致，csv 能被正常解析

不一致就重做该步，**不带病收尾**。

### 9. 输出摘要

**feishu 模式**：推送 + 会话内同时输出

```bash
OPEN_ID=$(lark-cli contact +get-user --as user | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['user']['open_id'])")
TABLE_URL=$(python3 -c "import json;print(json.load(open('$HOME/.workbuddy/daily-job-push/target.json'))['table_url'])")

lark-cli im +messages-send --as user --user-id $OPEN_ID --markdown "$(cat summary.md)"
```

收件人也可用「岗位推送」群的 `chat_id`（见 `target.json` 的 `notify.mode`）。

**local 模式**：只在会话里输出摘要，并**明确给出文件绝对路径**，提示"可直接导入飞书多维表格或 Excel"。

摘要格式（两种模式一致）：

```
📩 每日岗位推送 M月D日
今日新增 X 条（重复丢弃 Y 条）｜按匹配度：
高：岗位A @公司A · 薪资 · 平台（理由）
中：…（最多列 8 条，余量提示"详见表格"）
表：<table_url 或 本地文件路径>
```

**当天零新增也要推**，说明已检查过哪些方向——空跑也要有回音，用户才知道流程活着。

## 分享给别人用 / 换个人跑

技能本体不含个人数据，换人只需换配置。

**别人怎么装**

- **WorkBuddy**：目录放到 `~/.workbuddy/skills/daily-job-push/`
- **其他 Agent**（Claude Code / OpenClaw 等）：放到该 Agent 的 skills 目录，或粘贴平台给的安装口令

装完确认 `~/.workbuddy/daily-job-push/` 下**没有** profile.json（有就是前任的，删掉）。

**首次使用**：说一句"帮我搜今天的岗位" → 自动进第 0 步引导，问齐方向/城市/薪资，配好再跑。

**环境差异**（同一份技能，两种活法）

| 对方环境 | 模式 | 结果 |
|---|---|---|
| 有飞书（WorkBuddy + connector 已授权） | feishu | 岗位入库 + 消息推送 |
| 没有飞书（任何 Agent） | local | 产出 md / csv，自行导入 |

飞书授权是账号级的，**不随技能走**——你用不了别人的，别人也用不了你的。

## 踩坑（必读，血泪换来）

详见 `references/platform-rules.md`。速记：拉勾已关停不搜；鱼泡禁用（蓝领向，浪费配额）；猎聘搜索结果页 URL 不是明细页（易混）；BOSS 直聘反爬狠，搜不到就换前程无忧/智联补量；所有"官网"来源必须人工核验域名。

**跨环境坑**：别的 Agent 里可能没有 `lark-cli`、没有 python3、甚至没有网络自由度。
- 没有 `lark-cli` → 走 local 模式，别在第 2 步死等（这是最常见的翻车点）
- 没有 python3 → 脚本用不了，改为**按关键词规则手工生成**搜索词，去重改为人工比对链接（慢但能跑通）
- 搜不动就如实说清楚卡在哪，**不要编造岗位**

## 定时自动化（当前未挂，手动触发）

用户决定：**先手动跑，跑顺了再考虑挂定时**。需要挂时在 WorkBuddy 里建每日 10:00 自动化，prompt 只需一句话：

> 运行 daily-job-push 技能：读取画像 profile.json，执行主流程 9 步，推送摘要到飞书。

画像改动只改 `~/.workbuddy/daily-job-push/profile.json`，不动自动化。
