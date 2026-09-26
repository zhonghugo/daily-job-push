#!/bin/bash
# daily-job-push / dedup_keys.py 回归测试（56 条断言，用例 A–L）
# 用法: bash scripts/test_dedup_keys.sh     # 任意 cwd 下都能跑，临时目录固定在 /tmp/dedup_regress
cd "$(dirname "$0")/.." || exit 1
DEDUP="$PWD/scripts/dedup_keys.py"
D=/tmp/dedup_regress; rm -rf $D; mkdir -p $D; cd $D
pass=0; fail=0
chk(){ if [ "$2" = "$3" ]; then echo "  ✅ $1"; pass=$((pass+1)); else echo "  ❌ $1  期望[$3] 实得[$2]"; fail=$((fail+1)); fi; }

echo "═══ 用例A：飞书模式 · 全路径 ═══"
cat > ex.ndjson <<'EOF'
{"record_id":"recCT001","fields":{"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"[查看岗位](https://www.zhipin.com/job_detail/ct001.html)","薪资范围":"1.7-3万","工作地点":"深圳·龙华区","来源平台":["BOSS直聘"],"状态":["待投递"],"备注":"2026-09-20 10:00 · 深圳 AI应用 招聘","发布日期":"2026-09-20 10:00"}}
EOF
cat > cd.json <<'EOF'
[
 {"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"https://www.liepin.com/job/1962222222.shtml","薪资范围":"1.8-3万","工作地点":"深圳·龙华区","来源平台":["猎聘"],"备注":"run"},
 {"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"https://www.zhipin.com/job_detail/ct001.html","薪资范围":"1.7-3万","工作地点":"深圳·龙华区","来源平台":["BOSS直聘"],"备注":"run"},
 {"岗位名称":"AI应用交付经理","公司名称":"大湾区实验室","招聘链接":"https://www.liepin.com/job/1963333333.shtml","薪资范围":"2-3.5万","工作地点":"深圳","来源平台":["猎聘"],"备注":"run"},
 {"岗位名称":"AI应用交付经理","公司名称":"大湾区实验室","招聘链接":"https://www.51job.com/jobs/sz/1963333333.html","薪资范围":"2-3.5万","工作地点":"深圳","来源平台":["前程无忧"],"备注":"run"},
 {"岗位名称":"AI应用工程师","公司名称":"某公司","招聘链接":"https://sou.zhipin.com/web/geek/job?query=AI","来源平台":["BOSS直聘"],"备注":"run"}
]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates cd.json --out n.json --today 2026-09-26)
chk "跨渠道归并（猎聘→BOSS，靠链接键命中）" "$(echo "$out"|grep -c '^  归并:')" "1"
chk "同源重复确认（BOSS 同链接不重复计渠道）" "$(echo "$out"|grep -o '重复确认 [0-9]*'|grep -o '[0-9]*')" "1"
chk "搜索页被丢弃" "$(echo "$out"|grep -o '无效丢弃 [0-9]*'|grep -o '[0-9]*')" "1"
chk "大湾区同批归并为 1 条新岗位" "$(python3 -c "import json;d=json.load(open('n.json'));print(len([r for r in d if r['公司名称']=='大湾区实验室']))")" "1"
chk "大湾区渠道数=2" "$(python3 -c "import json;d=json.load(open('n.json'));print([r['渠道数'] for r in d if r['公司名称']=='大湾区实验室'][0])")" "2"
chk "归并后中国电信渠道数=2" "$(python3 -c "import json;print(json.load(open('n.updates.json'))['update_records']['recCT001']['渠道数'])")" "2"
chk "招聘链接未被改动（仍在 update 体之外）" "$(python3 -c "import json;print('招聘链接' in json.load(open('n.updates.json'))['update_records']['recCT001'])")" "False"
chk "状态未被改动" "$(python3 -c "import json;print('状态' in json.load(open('n.updates.json'))['update_records']['recCT001'])")" "False"
chk "同岗来源保留跨渠道薪资差异" "$(python3 -c "
import json;s=json.load(open('n.updates.json'))['update_records']['recCT001']['同岗来源']
print('1.7-3万' in s and '1.8-3万' in s)")" "True"

echo "═══ 用例B：本地模式往返 + 残留清理 ═══"
rm -rf b && mkdir b && cd b
cat > jobs-2026-09-20.ndjson <<'EOF'
{"岗位名称":"AI应用交付经理","公司名称":"东亚银行","招聘链接":"https://www.liepin.com/job/1961111111.shtml","薪资范围":"2-3.5万","工作地点":"深圳","来源平台":["猎聘"],"状态":["待投递"],"发布日期":"2026-09-20","渠道数":1,"同岗来源":"[2026-09-20] 猎聘 · 2-3.5万 · 深圳 · https://www.liepin.com/job/1961111111.shtml"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"AI应用交付经理","公司名称":"东亚银行","招聘链接":"https://www.zhipin.com/job_detail/yh777.html","薪资范围":"2.2-3.8万","工作地点":"深圳·福田区","来源平台":["BOSS直聘"],"备注":"run"}]
EOF
{ cat jobs-*.ndjson 2>/dev/null; cat merges-*.ndjson 2>/dev/null; } > ex.ndjson
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out o.json --today 2026-09-26)
chk "第1轮产生本地归并日志" "$([ -f merges-2026-09-26.ndjson ] && echo yes)" "yes"
chk "本地模式不产生 updates.json" "$([ -f o.updates.json ] && echo yes || echo no)" "no"
{ cat jobs-*.ndjson 2>/dev/null; cat merges-*.ndjson 2>/dev/null; } > ex.ndjson
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out o.json --today 2026-09-27)
chk "第2轮 last-wins 读到归并后版本（渠道数2）" "$(echo "$out"|grep -o '已有记录 [0-9]* 条（去重键 [0-9]* 个）')" "已有记录 2 条（去重键 2 个）"
chk "第2轮识别为重复确认" "$(echo "$out"|grep -o '重复确认 [0-9]*'|grep -o '[0-9]*')" "1"
chk "第2轮不产生归并产物" "$([ -f o.merges.json ] && echo yes || echo no)" "no"
chk "第2轮不产生新日志" "$([ -f merges-2026-09-27.ndjson ] && echo yes || echo no)" "no"

echo "═══ 用例C：键冲突检测（存量里有重复行） ═══"
cd $D && rm -rf c && mkdir c && cd c
cat > ex.ndjson <<'EOF'
{"record_id":"recA","fields":{"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"[查看岗位](https://www.zhipin.com/job_detail/ct001.html)","来源平台":["BOSS直聘"],"状态":["待投递"],"发布日期":"2026-09-20"}}
{"record_id":"recB","fields":{"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"https://www.liepin.com/job/1962222222.shtml","来源平台":["猎聘"],"状态":["待投递"],"发布日期":"2026-09-21"}}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"https://www.zhipin.com/job_detail/ct001.html","来源平台":["BOSS直聘"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out o.json --today 2026-09-26)
chk "检出键冲突" "$(echo "$out"|grep -c '键冲突')" "1"
chk "键冲突时不写 updates.json（避免误改）" "$([ -f o.updates.json ] && echo yes || echo no)" "no"
chk "重复确认不产生归并计划" "$(echo "$out"|grep -o '归并老岗位 [0-9]*'|grep -o '[0-9]*')" "0"
chk "重复确认不产生 merges.json" "$([ -f o.merges.json ] && echo yes || echo no)" "no"

echo "═══ 用例D：check-link 冒烟（与改动前一致） ═══"
cd $D
chk "猎聘明细页" "$(python3 $DEDUP --check-link 'https://www.liepin.com/job/1961234567.shtml')" "detail"
chk "BOSS搜索页" "$(python3 $DEDUP --check-link 'https://sou.zhipin.com/web/geek/job?query=AI')" "search"
chk "BOSS明细页" "$(python3 $DEDUP --check-link 'https://www.zhipin.com/job_detail/abc123.html')" "detail"
chk "51job 文库页" "$(python3 $DEDUP --check-link 'https://wenku.51job.com/article/12345/')" "search"
chk "markdown 包裹的链接也能判明细页" "$(python3 $DEDUP --check-link '[查看岗位](https://www.liepin.com/job/1961234567.shtml)')" "detail"

echo "═══ 用例E：括号限定词互斥 → 同公司同名也是两个岗位（不猜、不并、不丢） ═══"
cd $D && rm -rf e && mkdir e && cd e
cat > ex.ndjson <<'EOF'
{"record_id":"recTY1","公司名称":"传音控股","岗位名称":"AI产品经理（数据运营方向）","招聘链接":"[查看岗位](https://m.zhipin.com/zhaopin/ed38089f9011e2ef1H163d66Eg~~/)","来源平台":["BOSS直聘"],"状态":["待投递"],"发布日期":"2026-09-13"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"AI产品经理（HR领域）","公司名称":"传音控股","招聘链接":"https://www.liepin.com/job/19998888.shtml","来源平台":["猎聘"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out e.json --today 2026-09-26)
chk "互斥限定词不并入老行（本轮不猜）" "$(echo "$out"|grep -c '^  归并:')" "0"
chk "仍按新岗位入库（不丢岗位）" "$(python3 -c "
import json;d=json.load(open('e.json'))
print([r['岗位名称'] for r in d])")" "['AI产品经理（HR领域）']"
chk "点名「同名不同限定」" "$(echo "$out"|grep -c '❓同名不同限定')" "1"
chk "老行未被污染（不产生写回体）" "$([ -f e.updates.json ] && echo yes || echo no)" "no"

echo "═══ 用例F：无链接候选走退化键（不该标同名待确认） ═══"
cd $D && rm -rf f && mkdir f && cd f
cat > ex.ndjson <<'EOF'
{"record_id":"recZTE","公司名称":"中兴通讯","岗位名称":"数字化业务规划经理","招聘链接":"[查看岗位](https://www.liepin.com/job/1965555555.shtml)","来源平台":["猎聘"],"状态":["待投递"],"发布日期":"2026-09-18"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"数字化业务规划经理","公司名称":"中兴通讯","招聘链接":"","来源平台":["脉脉"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out f.json --today 2026-09-26)
chk "无链接候选仍归并" "$(echo "$out"|grep -c '^  归并:')" "1"
chk "不误标「同名待确认」" "$(echo "$out"|grep -c '同名待确认')" "0"

echo "═══ 用例G：同链接重复行（同一去重键下两条记录） ═══"
cd $D && rm -rf g && mkdir g && cd g
cat > ex.ndjson <<'EOF'
{"record_id":"recDup1","岗位名称":"Automation Engineer（业务落地型）","公司名称":"Century国际货运","招聘链接":"[查看岗位](https://jobs.51job.com/shenzhen/168888888.html)","来源平台":["前程无忧"],"状态":["待投递"],"发布日期":"2026-09-20"}
{"record_id":"recDup2","岗位名称":"Automation Engineer（自动化工程师）","公司名称":"深圳某企业","招聘链接":"https://jobs.51job.com/shenzhen/168888888.html","来源平台":["转载聚合"],"状态":["待投递"],"发布日期":"2026-09-24"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"Automation Engineer","公司名称":"某科技公司","招聘链接":"https://jobs.51job.com/shenzhen/168888888.html?utm_source=x&from=search","来源平台":["脉脉"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out g.json --today 2026-09-26)
chk "同链接重复行也要检出（旧版会被 last-wins 吞掉）" "$(echo "$out"|grep -c '⚠️ 键冲突')" "1"
chk "冲突行名列全（键冲突区+存量体检区各一次）" "$(echo "$out"|grep -E '^      recDup'|wc -l|tr -d ' ')" "4"
chk "存量体检独立报出同链接重复" "$(echo "$out"|grep -c '⚠️ 同链接重复')" "1"
chk "键冲突时不写 updates.json" "$([ -f g.updates.json ] && echo yes || echo no)" "no"

echo "═══ 用例H：本地更正日志不算重复（不该报键冲突） ═══"
cd $D && rm -rf h && mkdir h && cd h
cat > jobs-2026-09-26.ndjson <<'EOF'
{"fields":{"岗位名称":"Ai应用工程师","公司名称":"深圳某科技","招聘链接":"[查看岗位](https://zrc-sme.chinasme.cn/job/6aa467a709732e35ee89e9d1)","薪资范围":"1.3-2.6万","工作地点":"深圳·南山区","来源平台":["转载聚合"],"状态":["待投递"],"发布日期":"2026-09-26","渠道数":1,"同岗来源":"[2026-09-26] 转载聚合 · 1.3-2.6万 · 深圳·南山区 · https://zrc-sme.chinasme.cn/job/6aa467a709732e35ee89e9d1"}}
EOF
cat > merges-2026-09-26.ndjson <<'EOF'
{"fields":{"岗位名称":"Ai应用工程师","公司名称":"深圳某科技","招聘链接":"[查看岗位](https://zrc-sme.chinasme.cn/job/6aa467a709732e35ee89e9d1)","薪资范围":"1.3-2.6万","工作地点":"深圳·南山区","来源平台":["转载聚合"],"状态":["待投递"],"发布日期":"2026-09-26","渠道数":2,"同岗来源":"[2026-09-26] 转载聚合 · 1.3-2.6万 · 深圳·南山区 · https://zrc-sme.chinasme.cn/job/6aa467a709732e35ee89e9d1\n[2026-09-27] 猎聘 · - · - · https://www.liepin.com/job/19777777.shtml"}}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"Ai应用工程师","公司名称":"深圳某科技","招聘链接":"","来源平台":["猎聘"],"备注":"run"}]
EOF
{ find . -maxdepth 1 -name 'jobs-*.ndjson' -exec cat {} + ;
  find . -maxdepth 1 -name 'merges-*.ndjson' -exec cat {} + ; } > ex.ndjson
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out h.json --today 2026-09-28)
chk "更正日志不误报键冲突" "$(echo "$out"|grep -c '⚠️ 键冲突')" "0"
chk "last-wins 读到渠道数2那版且同平台不涨渠道" "$(echo "$out"|grep -c '渠道 2→2 · 来源 2→3 条')" "1"

echo "═══ 用例I：同平台重复见到不涨渠道数，换平台才涨 ═══"
cd $D && rm -rf i && mkdir i && cd i
cat > ex.ndjson <<'EOF'
{"record_id":"recZTE1","岗位名称":"数字化业务规划经理","公司名称":"中兴通讯","招聘链接":"https://m.liepin.com/job/1985054411.shtml","来源平台":["猎聘"],"状态":["待投递"],"发布日期":"2026-09-14","渠道数":1,"同岗来源":"[2026-09-14] 猎聘 · 18-35k · 深圳 · https://m.liepin.com/job/1985054411.shtml"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"数字化业务规划经理","公司名称":"中兴通讯","招聘链接":"","薪资范围":"18-35k","工作地点":"深圳·大冲","来源平台":"猎聘","备注":"猎聘列表页又见到"},
 {"岗位名称":"数字化业务规划经理","公司名称":"中兴通讯","招聘链接":"https://www.zhipin.com/job_detail/abc987654.html","薪资范围":"18-35k","工作地点":"深圳","来源平台":"BOSS直聘","备注":"换平台了"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out i.json --today 2026-09-26)
chk "同平台那条不涨渠道数（若误计会得 3）" "$(python3 -c "import json;print(json.load(open('i.updates.json'))['update_records']['recZTE1']['渠道数'])")" "2"
chk "两条来源行都记下了（猎聘同平台 + BOSS）" "$(python3 -c "
import json
s=json.load(open('i.updates.json'))['update_records']['recZTE1']['同岗来源']
print(len(s.splitlines()))")" "3"
chk "报告把渠道/来源两个数分开写" "$(echo "$out"|grep -c '渠道 1→2 · 来源 1→3 条')" "1"
chk "同平台旧行原文不动（18-35k 那行仍在）" "$(python3 -c "
import json
s=json.load(open('i.updates.json'))['update_records']['recZTE1']['同岗来源']
print('是' if '[2026-09-14] 猎聘 · 18-35k · 深圳 · https://m.liepin.com/job/1985054411.shtml' in s else '否')")" "是"
chk "无括号限定词的跨平台归并不误标待确认" "$(echo "$out"|grep -c '同名待确认')" "0"

echo "═══ 用例J：带限定词的候选归到对应行，裸标题候选只报不并 ═══"
cd $D && rm -rf j && mkdir j && cd j
cat > ex.ndjson <<'EOF'
{"record_id":"recJ1","岗位名称":"AI产品经理(J19661)","公司名称":"传音控股","招聘链接":"https://msearch.51job.com/jobs/shenzhen-lhq/173388063.html","来源平台":["前程无忧"],"状态":["不合适"],"发布日期":"2026-09-20"}
{"record_id":"recJ2","岗位名称":"AI产品经理（HR领域）","公司名称":"传音控股","招聘链接":"https://jobs.51job.com/shenzhen/173421182.html","来源平台":["前程无忧"],"状态":["已投递"],"发布日期":"2026-09-21"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"AI产品经理(J19661)","公司名称":"传音控股","招聘链接":"https://www.liepin.com/job/19990001.shtml","薪资范围":"30-40k","工作地点":"深圳","来源平台":["猎聘"],"备注":"run"},
 {"岗位名称":"AI产品经理","公司名称":"传音控股","招聘链接":"https://www.liepin.com/job/19990002.shtml","来源平台":["猎聘"],"备注":"裸标题，落哪条看不出"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out j.json --today 2026-09-26)
chk "带限定词的候选跨渠道归并（渠道 1→2）" "$(echo "$out"|grep -c '渠道 1→2')" "1"
chk "写回体只含对应那一行" "$(python3 -c "
import json;print(sorted(json.load(open('j.updates.json'))['update_records']))")" "['recJ1']"
chk "裸标题候选只报不改（不猜落在哪一条）" "$(echo "$out"|grep -c '⚠️ 键冲突')" "1"
chk "冲突区带上候选自己的来源行（线索不无声消失）" "$(echo "$out"|grep -c '← 本轮候选')" "1"
chk "本轮不产生新岗位（候选是命中的老岗位）" "$(python3 -c "import json;print(len(json.load(open('j.json'))))")" "0"

echo "═══ 用例K：同批两条互斥限定词的候选 → 各归各的，不互相串键 ═══"
cd $D && rm -rf k && mkdir k && cd k
cat > ex.ndjson <<'EOF'
{"record_id":"recK0","岗位名称":"AI应用工程师","公司名称":"中国电信","招聘链接":"https://www.zhipin.com/job_detail/ct001.html","来源平台":["BOSS直聘"],"状态":["待投递"],"发布日期":"2026-09-20"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"数据分析师（增长）","公司名称":"深圳新样本公司","招聘链接":"https://www.liepin.com/job/19700001.shtml","来源平台":["猎聘"],"备注":"run"},
 {"岗位名称":"数据分析师（风控）","公司名称":"深圳新样本公司","招聘链接":"https://www.zhipin.com/job_detail/fk00002.html","来源平台":["BOSS直聘"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out k.json --today 2026-09-26)
chk "互斥限定词同批也是 2 条新岗位" "$(python3 -c "
import json;d=json.load(open('k.json'))
print(len([r for r in d if r['公司名称']=='深圳新样本公司']))")" "2"
chk "两条各自渠道数=1（未被误并成跨渠道）" "$(python3 -c "
import json;d=json.load(open('k.json'))
print(sorted(r['渠道数'] for r in d))")" "[1, 1]"
chk "同批不产生归并" "$(echo "$out"|grep -c '^  归并:')" "0"

echo "═══ 用例L：L 键只丢追踪参数（岗位 id 在 query 里时不再塌成一个键） ═══"
cd $D && rm -rf l && mkdir l && cd l
SD="$(dirname "$DEDUP")"
chk "追踪参数丢掉、岗位 id 留下（fragment 也丢）" "$(python3 -c "
import sys; sys.path.insert(0, '$SD')
import dedup_keys as d
print(d.norm_link('https://hr.tencent.com/m/jobdesc.html?postId=9&utm_source=a&from=b&_t=1#top'))")" "hr.tencent.com/m/jobdesc.html?postId=9"
chk "参数顺序无关（按参数名排序）" "$(python3 -c "
import sys; sys.path.insert(0, '$SD')
import dedup_keys as d
print(d.norm_link('https://hr.tencent.com/m/jobdesc.html?dept=ai&postId=9'))")" "hr.tencent.com/m/jobdesc.html?dept=ai&postId=9"
chk "BOSS 的 lid/securityId/sessionId 这类会话参数也丢" "$(python3 -c "
import sys; sys.path.insert(0, '$SD')
import dedup_keys as d
print(d.norm_link('https://www.zhipin.com/job_detail/abc123.html?lid=1&securityId=2&sessionId=3'))")" "zhipin.com/job_detail/abc123.html"
cat > ex.ndjson <<'EOF'
{"record_id":"recTX1","岗位名称":"AI提效运营","公司名称":"腾讯","招聘链接":"[查看岗位](https://hr.tencent.com/m/jobdesc.html?postId=11111111)","来源平台":["腾讯招聘官网"],"状态":["待投递"],"发布日期":"2026-09-20","渠道数":1,"同岗来源":"[2026-09-20] 腾讯招聘官网 · - · 深圳 · https://hr.tencent.com/m/jobdesc.html?postId=11111111"}
EOF
cat > c.json <<'EOF'
[{"岗位名称":"AI运营","公司名称":"腾讯","招聘链接":"https://hr.tencent.com/m/jobdesc.html?postId=22222222","来源平台":["猎聘"],"备注":"run"},
 {"岗位名称":"AI提效运营","公司名称":"腾讯","招聘链接":"https://hr.tencent.com/m/jobdesc.html?postId=11111111&utm_source=liepin&from=search","来源平台":["猎聘"],"备注":"run"}]
EOF
out=$(python3 $DEDUP --existing ex.ndjson --candidates c.json --out l.json --today 2026-09-26)
chk "不同 postId 是两个岗位（老版整站塌成一个键，会静默并成一条）" "$(python3 -c "
import json;d=json.load(open('l.json'));print([r['岗位名称'] for r in d])")" "['AI运营']"
chk "带追踪参数的同一 postId 仍认成同一条（重复确认，不新建行）" "$(echo "$out"|grep -o '重复确认 [0-9]*'|grep -o '[0-9]*')" "1"
chk "纯重复确认不产生归并计划" "$(echo "$out"|grep -c '^  归并:')" "0"
chk "纯重复确认不产生写回体（老行不动）" "$([ -f l.updates.json ] && echo yes || echo no)" "no"

echo
echo "══════ 通过 $pass / 失败 $fail ══════"
exit $fail
