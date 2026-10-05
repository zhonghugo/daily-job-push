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

- 需要 `access_token` + 设备参数：一次抓包（Reqable / Charles / mitmproxy）从已登录脉脉 App 获取，或用 maimai-cli 的 `mm login` 短信登录自动签发
- token 会过期，过期需更新；凭证缺失时回退常规搜索并如实说明
- **低频调用、遵守脉脉服务条款**；本 skill 不做自动投递（投递动作由用户执行）

## 收录规则

- 明细页链接优先采用 `article/detail?efid=` 形态；拿不到明细页链接的岗位不收录
- 收录前按 platform-rules.md 执行岗位有效性检查（已下线/停招不收录）
