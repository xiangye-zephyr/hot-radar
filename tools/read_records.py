#!/usr/bin/env python3
"""读飞书「热点雷达 / 发布记录」多维表格，打印成 Markdown 表格，供出简报前参考。

用法：python3 tools/read_records.py
"""

import sys
from datetime import datetime, timezone, timedelta

from feishu import FeishuError, config, lark

COLUMNS = [
    "发布日期", "视频标题", "内容线", "对应热点",
    "24小时播放", "24小时点赞", "24小时评论", "24小时分享",
    "7天播放", "7天点赞", "7天评论", "7天分享", "备注",
]
BEIJING = timezone(timedelta(hours=8))


def cell(value, column):
    if value in (None, "", []):
        return ""
    if column == "发布日期" and isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, BEIJING).strftime("%Y-%m-%d")
    if column == "发布日期" and isinstance(value, str):
        return value[:10]
    if isinstance(value, list):
        return "、".join(cell(v, column) for v in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or value.get("link") or "")
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).replace("|", "/").replace("\n", " ")


def main():
    cfg = config()
    rows, offset = [], 0
    while True:
        data = lark(
            "base", "+record-list", "--base-token", cfg["records_base"],
            "--table-id", cfg["records_table"], "--offset", str(offset), "--format", "json",
        )
        fields = data.get("fields") or []
        for values in data.get("data") or []:
            record = dict(zip(fields, values))
            if any(v not in (None, "", []) for v in record.values()):
                rows.append(record)
        offset += len(data.get("record_id_list") or [])
        if not data.get("has_more"):
            break
    if not rows:
        print("发布记录：表里还没有数据。")
        return
    rows.sort(key=lambda r: cell(r.get("发布日期"), "发布日期"), reverse=True)
    print(f"发布记录：共 {len(rows)} 条（按发布日期从新到旧；空格子表示还没填）\n")
    print("| " + " | ".join(COLUMNS) + " |")
    print("|" + "---|" * len(COLUMNS))
    for r in rows:
        print("| " + " | ".join(cell(r.get(c), c) for c in COLUMNS) + " |")


if __name__ == "__main__":
    try:
        main()
    except FeishuError as e:
        print(f"读取飞书发布记录失败：{e}", file=sys.stderr)
        sys.exit(1)
