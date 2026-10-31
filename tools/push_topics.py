#!/usr/bin/env python3
"""把一份简报的选题写进飞书「选题与发布」表，一条一行，状态默认「待选」。

用法：python3 tools/push_topics.py briefs/2026-10-31-早报.topics.json
JSON 是一个数组，每项：选题、栏目（推荐/梗/可以试试）、类型、内容线、来源、切入角度、结合产品。
同一天同一时段已经写过，就跳过，不会重复。
"""

import json
import re
import sys
from pathlib import Path

from feishu import FeishuError, config, lark

OPTIONS = {
    "栏目": ["推荐", "梗", "可以试试", "自选"],
    "类型": ["事件型", "梗和玩法型", "长线型", "节日"],
    "内容线": ["AIGC", "真人出镜", "短剧"],
}
TEXT_FIELDS = ["选题", "来源", "切入角度", "结合产品"]


def pick(field, value):
    """单选字段只接受已有选项；值里包含哪个选项就用哪个（比如"长线型｜换季穿搭"→"长线型"）。"""
    for option in OPTIONS[field]:
        if option in str(value or ""):
            return [option]
    return None


def already_pushed(cfg, day, slot):
    data = lark(
        "base", "+record-list", "--base-token", cfg["topics_base"], "--table-id", cfg["topics_table"],
        "--field-id", "选题", "--limit", "1", "--format", "json",
        "--filter-json", json.dumps({"logic": "and", "conditions": [
            ["日期", "==", f"ExactDate({day})"], ["时段", "intersects", [slot]],
        ]}, ensure_ascii=False),
    )
    return bool(data.get("record_id_list"))


def main(path):
    file = Path(path)
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(早报|午报|晚报)\.topics\.json$", file.name)
    if not m:
        raise SystemExit("文件名要像 2026-10-31-早报.topics.json")
    day, slot = m.groups()
    items = json.loads(file.read_text("utf-8"))
    cfg = config()
    if already_pushed(cfg, day, slot):
        print(f"{day} {slot}的选题已经写进表里了，跳过")
        return

    records = []
    for item in items:
        if not str(item.get("选题") or "").strip():
            continue
        record = {"日期": f"{day} 00:00", "时段": [slot], "状态": ["待选"]}
        for field in TEXT_FIELDS:
            if item.get(field):
                record[field] = str(item[field]).strip()
        for field in OPTIONS:
            chosen = pick(field, item.get(field))
            if chosen:
                record[field] = chosen
        records.append(record)
    if not records:
        print("没有可写的选题")
        return
    for start in range(0, len(records), 200):
        lark(
            "base", "+record-batch-create", "--base-token", cfg["topics_base"],
            "--table-id", cfg["topics_table"],
            "--json", json.dumps({"create_records": records[start:start + 200]}, ensure_ascii=False),
        )
    print(f"已把 {len(records)} 条选题写进「选题与发布」表（{day} {slot}）")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        main(sys.argv[1])
    except FeishuError as e:
        print(f"写入飞书选题表失败：{e}", file=sys.stderr)
        sys.exit(1)
