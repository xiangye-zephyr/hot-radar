#!/usr/bin/env python3
"""把一份简报发到飞书「热点雷达 / 热点简报」：每天一篇文档，早报、午报、晚报依次追加。

用法：python3 tools/publish_brief.py briefs/2026-10-30-早报.md
当天的文档还没有就新建；已经有了就追加到末尾；这一份已经发过（标题已存在）就跳过。
"""

import re
import sys
from pathlib import Path

from feishu import FeishuError, config, lark


def find_daily_doc(cfg, title):
    data = lark(
        "wiki", "+node-list", "--space-id", cfg["space_id"],
        "--parent-node-token", cfg["briefs_node"], "--page-all", "--page-limit", "0",
    )
    for node in data.get("nodes") or []:
        if node.get("title") == title:
            return node.get("obj_token")
    return None


def main(path):
    brief = Path(path)
    m = re.match(r"(\d{4}-\d{2}-\d{2})-(早报|午报|晚报)\.md$", brief.name)
    if not m:
        raise SystemExit("文件名要像 2026-10-30-早报.md")
    content = brief.read_text("utf-8").strip() + "\n"
    heading = content.splitlines()[0].lstrip("# ").strip()
    title = f"{m.group(1)} 热点简报"
    cfg = config()

    doc = find_daily_doc(cfg, title)
    if doc is None:
        data = lark(
            "docs", "+create", "--parent-token", cfg["briefs_node"], "--title", title,
            "--doc-format", "markdown", "--content", "-", stdin=content,
        )
        doc = (data.get("document") or {}).get("document_id") or data.get("document_id") or data.get("doc_token")
        print(f"已新建《{title}》并写入{m.group(2)}")
    else:
        outline = lark("docs", "+fetch", "--doc", doc, "--scope", "outline", "--doc-format", "markdown")
        if heading and heading in str(outline):
            print(f"《{title}》里已经有「{heading}」，跳过")
            return
        lark(
            "docs", "+update", "--doc", doc, "--command", "append",
            "--doc-format", "markdown", "--content", "-", stdin="\n---\n\n" + content,
        )
        print(f"已把{m.group(2)}追加到《{title}》")
    if doc:
        print(f"https://my.feishu.cn/docx/{doc}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        main(sys.argv[1])
    except FeishuError as e:
        print(f"发到飞书失败：{e}", file=sys.stderr)
        sys.exit(1)
