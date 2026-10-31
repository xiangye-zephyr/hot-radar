#!/usr/bin/env python3
"""读飞书「选题与发布」表最近 30 天的数据，输出一份简短汇总，供出简报前参考。

只输出汇总和选中过的选题，不把整张表交给 Agent，省 token。
用法：python3 tools/topics_summary.py
"""

import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from feishu import FeishuError, config, lark

BEIJING = timezone(timedelta(hours=8))
DAYS = 30
TAKEN = {"选中", "制作中", "已发布"}  # 算作"被选中"的状态
# 来源里出现这些词就归到对应平台；有好几个时取最先出现的那个
PLATFORMS = {
    "抖音": ["抖音"], "热点宝": ["热点宝", "低粉", "飙升", "内容词"], "微博": ["微博"], "百度": ["百度"],
    "知乎": ["知乎"], "B站": ["B站"], "头条": ["头条"], "贴吧": ["贴吧"], "虎扑": ["虎扑"],
}
FIELDS = ["选题", "状态", "日期", "时段", "栏目", "类型", "内容线", "来源", "发布日期",
          "24小时播放", "7天播放"]


def first(value):
    if isinstance(value, list):
        return first(value[0]) if value else ""
    if isinstance(value, dict):
        return value.get("name") or value.get("text") or ""
    return value if value is not None else ""


def day_of(value):
    value = first(value)
    if isinstance(value, (int, float)) and value:
        return datetime.fromtimestamp(value / 1000, BEIJING).strftime("%m-%d")
    return str(value)[5:10] if value else ""


def number(value):
    value = first(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def platform(source):
    hits = [(str(source).find(w), name) for name, words in PLATFORMS.items() for w in words if w in str(source)]
    return min(hits)[1] if hits else "其他"


def rate(groups):
    return "、".join(f"{k} {v[1]}/{v[0]}" for k, v in sorted(groups.items(), key=lambda x: -x[1][0]) if k)


def load(cfg):
    since = (datetime.now(BEIJING) - timedelta(days=DAYS)).strftime("%Y-%m-%d")
    rows, offset = [], 0
    while True:
        args = ["base", "+record-list", "--base-token", cfg["topics_base"], "--table-id", cfg["topics_table"],
                "--offset", str(offset), "--format", "json",
                "--filter-json", f'{{"logic":"and","conditions":[["日期",">","ExactDate({since})"]]}}']
        for f in FIELDS:
            args += ["--field-id", f]
        data = lark(*args)
        names = data.get("fields") or []
        rows += [dict(zip(names, values)) for values in data.get("data") or []]
        offset += len(data.get("record_id_list") or [])
        if not data.get("has_more"):
            return rows


def main():
    rows = [r for r in load(config()) if first(r.get("选题"))]
    if not rows:
        print("选题与发布表：最近 30 天还没有数据。")
        return
    status = defaultdict(int)
    for r in rows:
        status[first(r.get("状态")) or "待选"] += 1
    taken = [r for r in rows if first(r.get("状态")) in TAKEN]
    print(f"选题与发布表（最近 {DAYS} 天）：共 {len(rows)} 条选题；"
          + "、".join(f"{k} {v}" for k, v in status.items()))

    print("\n## 选中过的选题（已选中、制作中、已发布；不要再重复推荐）")
    if not taken:
        print("- 还没有")
    for r in sorted(taken, key=lambda r: str(first(r.get("日期"))), reverse=True)[:40]:
        plays = [p for p in (number(r.get("24小时播放")), number(r.get("7天播放"))) if p is not None]
        perf = f"｜24小时/7天播放 {' / '.join(f'{p:.0f}' for p in plays)}" if plays else ""
        print(f"- {day_of(r.get('日期'))} {first(r.get('时段'))}｜{first(r.get('选题'))}｜{first(r.get('状态'))}"
              f"｜{first(r.get('内容线'))}｜{first(r.get('类型'))}｜{first(r.get('来源'))}{perf}")

    print("\n## 选中率（被选中 / 推给团队的总数）")
    for label, key in [("栏目", lambda r: first(r.get("栏目"))), ("类型", lambda r: first(r.get("类型"))),
                       ("内容线", lambda r: first(r.get("内容线"))), ("来源", lambda r: platform(first(r.get("来源"))))]:
        groups = defaultdict(lambda: [0, 0])
        for r in rows:
            if first(r.get("栏目")) == "自选":
                continue
            g = groups[key(r)]
            g[0] += 1
            g[1] += first(r.get("状态")) in TAKEN
        print(f"- 按{label}：{rate(groups)}")

    published = [r for r in rows if first(r.get("状态")) == "已发布" and number(r.get("24小时播放")) is not None]
    if published:
        print("\n## 已发布的平均 24 小时播放")
        for label in ["内容线", "类型"]:
            groups = defaultdict(list)
            for r in published:
                groups[first(r.get(label))].append(number(r.get("24小时播放")))
            print(f"- 按{label}：" + "、".join(f"{k} {sum(v) / len(v):.0f}（{len(v)} 条）" for k, v in groups.items() if k))


if __name__ == "__main__":
    try:
        main()
    except FeishuError as e:
        print(f"读取飞书选题表失败：{e}", file=sys.stderr)
        sys.exit(1)
