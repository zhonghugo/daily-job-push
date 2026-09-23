# 首次使用引导（onboarding）

配置缺失时（读不到 `~/.workbuddy/daily-job-push/profile.json`，或必填项为空）走本流程。
目标：**逐题引导**把配置补全并跑通第一轮。首次用户没有画像可依赖，一条消息甩四个问题会把人问懵——一问一答推进，每题附示例。

## 1. 逐题话术（照抄改）

**问 1/4 · 目标方向**

> 先问第一个问题：你想做哪类岗位？给 2–5 个。
> 写「职能」就行，比如"AI 应用落地 / 流程自动化 / 数字化转型"——别写具体职位名（如"AI 产品经理"），职位名会让搜索词太窄、捞不到周边岗位。

（用户答完）一句话复述理解，确认后继续：

> 明白，你的方向是 A、B、C。接下来第二个问题——

**问 2/4 · 意向城市**

> 在哪些城市找？支持「远程」。

**问 3/4 · 薪资范围**

> 期望月薪区间大概多少？（单位 K）
> 说明一下：薪资只用来给岗位打标，不会拿来硬过滤——合适的岗位低一点也会推给你看。

**问 4/4 · 投递表**（仅 feishu 模式；local 模式改为告知"结果会整理成本地表格文件"，跳过）

> 最后一件：你有自己的飞书多维表格吗？
> 有 → 把表格链接发我；没有 → 我按 12 个字段的规范帮你建一张「岗位机会」表。

可选项（用户不主动提就别问）：排除词、经验档位、偏好行业、其他备注。

**节奏规则**：

- 一条消息只问一件事；用户答完先复述理解再问下一条
- 用户答得笼统（"都行""你看着办"）→ 给建议值请他点头，不空转
- 用户明显不耐烦 → 一次问完剩余项，不再坚持逐题
- 四题问完 → 汇总复述全部配置，用户点头 → 写 profile.json → 进建表/主流程

## 2. 写画像

落盘到 `~/.workbuddy/daily-job-push/profile.json`，字段语义见 `profile-template.md`。

```bash
mkdir -p ~/.workbuddy/daily-job-push
```

注意：
- `directions` 写**职能**不写职位名——搜索词生成器会把职能和城市做笛卡尔积，写"AI 产品经理"会让关键词过窄
- `salary_min/max` 只影响匹配打标，**不做硬过滤**（用户可能愿意为合适机会让步）
- 排除词是"打标不删除"，不是过滤器

## 3. 准备目标表

### 情况 A：用户已有表

1. 让用户给表格链接，形如 `https://xxx.feishu.cn/base/<BASE_TOKEN>?table=<TABLE_ID>`
2. 拆出 `base_token` 与 `table_id`
3. 拉一次字段确认结构够用：

```bash
lark-cli base +field-list --base-token $BASE --table-id $TBL --as user
```

4. 缺字段就补（表内字段名必须与 `table-schema.md` 一致，否则写入失败）：

```bash
lark-cli base +field-create --base-token $BASE --table-id $TBL --as user \
  --fields '[{"name":"投递反馈","type":"text"}]'
```

### 情况 B：用户没有表 → 新建

一次建好 base + 首表 + 12 字段（`--base-create` 支持首表 schema）：

```bash
lark-cli base +base-create --as user --name "岗位机会" --table-name "岗位机会" \
  --time-zone Asia/Shanghai \
  --fields '[{"name":"岗位名称","type":"text"},{"name":"公司名称","type":"text"},{"name":"招聘链接","type":"text"},{"name":"薪资范围","type":"text"},{"name":"工作地点","type":"text"},{"name":"来源平台","type":"select","options":[{"name":"BOSS直聘"},{"name":"猎聘"},{"name":"前程无忧"},{"name":"智联招聘"},{"name":"官网"}]},{"name":"状态","type":"select","options":[{"name":"待投递"},{"name":"已投递"},{"name":"待跟进"},{"name":"不合适"},{"name":"已关闭"}]},{"name":"匹配理由","type":"text"},{"name":"备注","type":"text"},{"name":"发布日期","type":"date"},{"name":"岗位要点","type":"text"},{"name":"投递反馈","type":"text"}]'
```

> 字段 JSON 形状以 `+field-create` 为准；若报类型错误，先 `lark-cli skills read lark-base` 查 field schema，别自己猜属性。

拿新建 base 的 token：从返回里取 `app_token`（即 base token）与首表 `table_id`。

### 情况 C：在已有 base 里加表

```bash
lark-cli base +table-create --base-token $BASE --as user \
  --name "岗位机会" --fields '[ ...同上字段数组... ]'
```

## 4. 写 target.json

```bash
cat > ~/.workbuddy/daily-job-push/target.json <<'EOF'
{
  "base_token": "填 base token",
  "table_id": "填 table id",
  "table_url": "填完整表格链接",
  "notify": { "mode": "user", "open_id": "", "chat_id": "" }
}
EOF
```

取自己的 `open_id`（用于推送）：

```bash
lark-cli contact +get-user --as user
# → data.user.open_id
```

想推给一个群就设 `notify.mode = "chat"` 并填 `chat_id`。

## 5. 授权检查

`lark-cli` 必须是**已登录**状态，否则第 2/7/9 步全失败：

```bash
lark-cli auth status
```

未登录 → 引导用户完成飞书授权（这是使用者自己的账号，不随技能分发）。

## 6. 复述确认 → 开跑

配置写完后，把三行摘要复述给用户确认，再进主流程第 1 步：

```
画像：方向 [A/B/C] ｜ 城市 [X/Y] ｜ 薪资 N–M K ｜ 排除 [..]
目标表：岗位机会（已建 / 复用）→ <table_url>
推送：飞书私聊 / 群
```

**不要跳过确认**——画像反推容易错，城市和方向错了整轮搜索都白跑。
