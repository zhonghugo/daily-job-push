# 脉脉职位通道（可选进阶）

本文件记录脉脉职位数据的可选获取通道，供配置过凭证时使用。**信息来自公开开源项目调研（maimai-cli、Super_Employee、maimai-skill 等），端点与字段需在真实环境验证后使用**；未配置凭证时按 platform-rules.md 走 general_search 常规搜索，不阻塞主流程。

## 通路 A · App API（列表搜索，推荐）

- 主 Host：`open.taou.com/maimai`（另有 maimai.cn/sdk、api.taou.com/sdk）
- 职位搜索端点：`GET search_front/app/job_search`
- 常用参数：`query` · `page` · `count` · `fr` · `sid` · `rn=1` · `use_native_net=1`
- 响应 `data[]` 字段：`position` 岗位 / `salary_info` 薪资 / `company` 公司 / `city` 城市 / `degree` 学历 / `worktime` 经验 / `id` / `ejid`（加密职位 ID）
- 明细与投递均以 `ejid` 为凭证
- 配套端点：`search/job_sugs`（搜索联想）、`search/job_filter`（筛选）、`job/v3/job_sub` / `job_list`（订阅职位）

## 通路 B · Web 详情页（JD 全文）

- 职位详情页：`maimai.cn/article/detail?efid=<加密串>&fid=<数字>`，公开可访问、含 JD 全文；登录墙下未登录可见范围有限
- **已验证（2026-10-05）**：该形态经 general_search 可稳定检索，web_fetch 无需登录即可读取 JD 全文，可作常规收录通道
- 品牌页：`maimai.cn/brand/home/<id>` 聚合在招职位，可作公司维度补充（RPA 等主方向关键词公开索引命中少时优先走品牌页）
- 抓取工具：web_fetch / 浏览器自动化；页面结构以浏览器渲染后 DOM 为准

## 前置条件与合规红线

- 需要 `access_token` + `u`(uid) + 设备参数。**已打通方式（2026-10-12 实测）：maimai-cli `mm login` 短信登录**，无需抓包：
  ```bash
  git clone https://github.com/1013503897/maimai-cli.git && cd maimai-cli && pip install -e .
  cp session.example.json session.local.json   # 设备字段填随机 UUID（各字段不同值，别全填一样的）
  mm login --phone <手机号> --send            # 发验证码，输出 login-token
  mm login --phone <手机号> --code <短信码> --login-token <上一步token>
  ```
  - 登录成功响应里 extractor 常提不出 uid → **从响应 JSON 的 `info.global_content` 缓存 key 前缀取数字串（如 `35494474_xxx`）填进 session 的 `u`/`uid`**，否则 API 报「登录用户不存在」(20001)
  - 验证：`mm jobs "RPA" --count 5` 能出职位即通（实测 RPA/AI运营 均有结果）
  - session.local.json 路径即凭证位置；`mm jobs "<词>" --count N [--page P] [--json]`
- token 会过期，过期重跑 `mm login`；凭证缺失时回退常规搜索并如实说明
- **低频调用、遵守脉脉服务条款**；本 skill 不做自动投递（投递动作由用户执行）

## 收录规则

- App API 通道（`mm jobs`）：明细链接直接用响应里的 `share_url`（形态 `https://maimai.cn/job?ejid=<ejid>&srcu=...`，官方分享链接）；**不要自己拼 `article/detail?efid=`**——ejid ≠ efid，硬拼是死链
- Web 搜索通道：明细页链接优先采用 `article/detail?efid=` 形态；拿不到明细页链接的岗位不收录
- 收录前按 platform-rules.md 执行岗位有效性检查（已下线/停招不收录）

## WAF 风控（2026-10-12 实测定位）

现象：`maimai.cn/article/detail?efid=...` 访问偶发 `418 您的请求疑似攻击行为`（WAF 拦截页，含事件 ID）。

实测定位（服务器侧 curl 对照）：

| 请求方式 | 结果 |
|---|---|
| 带桌面 Chrome UA、无 cookie | **HTTP 200，JD 正文可读** |
| curl/python 默认 UA（无浏览器标识） | **HTTP 418，拦截页** |

结论：**拦的是「请求头没有正常浏览器 UA」的访问**，不要求登录（无 cookie 也能读）；418 也会在**同一 IP 短时间高频访问后临时触发限流**。用户浏览器撞 418 的常见原因：① 在豆包等内置/嵌入式浏览器里打开（请求头不标准）；② 近期频繁访问被临时限流。

处置：

- 链接照常收录，岗位**不降级、不丢弃**；JD 提取一律用带标准浏览器 UA 的请求（curl/WebFetch 配置 UA），**不要**拿 418 页面内容当 JD
- 给用户的摘要提示改为：「脉脉链接请在系统 Chrome/Edge 浏览器里打开（别用内置浏览器）；若还跳 418 是 IP 临时限流，等几分钟或切手机热点再试，无需登录」
- 若 WebFetch/抓取侧开始批量 418（UA 已合规仍被拦），视为该渠道当轮被限流，降频并如实说明，转其他渠道补量

### 品牌主页 `brand/home/<id>` 已关闭公开访问（2026-10-12 补测）

- `maimai.cn/brand/home/<id>` **带桌面 Chrome UA 也返回 418**（article/detail 同测是 200）——品牌页对匿名访问整体关闭，需登录态
- 因此品牌页**不能作为收录链接、也不能作为"主方向补量"的入口**；脉脉渠道只认 `article/detail?efid=` 职位帖形态
- 主方向补量两条路：① App API 通道（本文件通路 A，需 access_token）；② 换其他平台（BOSS/猎聘/前程无忧/官网）找同岗
