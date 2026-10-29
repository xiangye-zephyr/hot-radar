#!/usr/bin/env python3
"""hot-radar：抓取全网热榜 → 归档排名历史 → 导出给 Agent 读的 latest.json / latest.md。

数据来自 newsnow（https://github.com/newsnext/newsnow）的公开接口；抖音直接用官方热榜接口
（多 20 条、带热度值和话题开始时间），失败时退回 newsnow。只用 Python 标准库。
平台列表在 sources.json。运行：python3 crawl.py
"""

import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DAILY_DIR = DATA_DIR / "daily"
TZ = ZoneInfo("Asia/Shanghai")

# 想换成自己部署的 newsnow，设置环境变量 NEWSNOW_API 即可
API_URL = os.environ.get("NEWSNOW_API", "https://newsnow.busiyi.world/api/s")
DOUYIN_API = (
    "https://www.douyin.com/aweme/v1/web/hot/search/list/"
    "?device_platform=webapp&aid=6383&channel=channel_pc_web&detail_list=1"
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
REQUEST_INTERVAL = 1.5  # 秒，两个平台之间的间隔，别对公共接口太猛
RETRIES = 2
CARRY_OVER_HOURS = 12  # 跨天时，昨天还在榜、且离现在不超过这么久的热点，算同一次上榜
HOVER_MAX = 120  # 平台给的摘要截断长度
TRAJECTORY_POINTS = 6  # 轨迹显示最近几次抓取（每 2 小时一次，约 12 小时）


def load_sources():
    return json.loads((ROOT / "sources.json").read_text("utf-8"))


def http_json(url, headers=None):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        # 部分平台（如爱奇艺）的返回里有未转义的控制字符，strict=False 才能解析
        return json.loads(resp.read().decode("utf-8"), strict=False)


def fetch_newsnow(source_id):
    data = http_json(f"{API_URL}?id={source_id}&latest")
    if data.get("status") not in ("success", "cache"):
        raise ValueError(f"status={data.get('status')}")
    return data.get("items") or []


_douyin_board = {}


def douyin_board():
    """抖音官方热榜接口（免登录）。主榜和"实时上升热点"在同一个响应里，一次运行只请求一次。"""
    if "data" not in _douyin_board:
        _douyin_board["data"] = http_json(DOUYIN_API, {"Referer": "https://www.douyin.com/"})["data"]
    return _douyin_board["data"]


def douyin_items(rows):
    """把抖音官方接口的条目转成 newsnow 的格式；id 用 sentence_id，和 newsnow 的抖音编号一致。"""
    items = []
    for row in rows:
        word = (row.get("word") or "").strip()
        if not word:
            continue
        sid = row.get("sentence_id")
        hot = row.get("hot_value") or 0
        items.append({
            "id": str(sid or word),
            "title": word,
            "url": f"https://www.douyin.com/hot/{sid}" if sid else f"https://www.douyin.com/search/{quote(word)}",
            "extra": {"info": f"{hot / 10000:.0f}万热度" if hot else "", "topic_start": row.get("event_time")},
        })
    return items


def fetch_douyin(source_id):
    try:
        return douyin_items(douyin_board()["word_list"])
    except Exception as e:
        print(f"  抖音官方接口失败（{e}），改用 newsnow")
        return fetch_newsnow(source_id)


def fetch_douyin_rising(_source_id):
    return douyin_items(douyin_board().get("trending_list") or [])


FETCHERS = {"douyin": fetch_douyin, "douyin-rising": fetch_douyin_rising}


def fetch(src):
    """请求一个平台的热榜，失败会重试，返回 newsnow 格式的 items 列表。"""
    getter = FETCHERS.get(src.get("fetcher"), fetch_newsnow)
    error = None
    for attempt in range(RETRIES + 1):
        if attempt:
            time.sleep(3 * attempt)
        try:
            items = getter(src["id"])
            if not items:
                raise ValueError("没有数据")
            return items
        except Exception as e:  # 任何错误都记下来，不影响其他平台
            error = e
    raise RuntimeError(str(error))


# ---------- 每日归档：data/daily/YYYY-MM-DD.json ----------

def daily_path(day):
    return DAILY_DIR / f"{day.isoformat()}.json"


def load_daily(day):
    path = daily_path(day)
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return {"date": day.isoformat(), "crawls": [], "items": {}}


def dump_one_per_line(head, sections):
    """一条记录一行写 JSON：git 每次只记变动的行，仓库长得慢，人和 Agent 也好读。

    sections 是 [(字段名, 每行文本, 是否对象)]；对象的每行形如 "key": value。
    """
    text = json.dumps(head, ensure_ascii=False)[:-1]  # 去掉结尾的 }，后面接列表字段
    for name, rows, is_object in sections:
        open_, close = "{}" if is_object else "[]"
        text += f',\n"{name}": {open_}\n' + ",\n".join(rows) + f"\n{close}"
    return text + "}\n"


def save_daily(daily):
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    crawls = [json.dumps(c, ensure_ascii=False) for c in daily["crawls"]]
    items = [
        f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v, ensure_ascii=False)}"
        for k, v in daily["items"].items()
    ]
    text = dump_one_per_line({"date": daily["date"]}, [("crawls", crawls, False), ("items", items, True)])
    daily_path(datetime.fromisoformat(daily["date"]).date()).write_text(text, "utf-8")


def carry_over(prev, now):
    """昨天的同一条热点如果是连着在榜的，沿用它的首次上榜时间和最高排名。"""
    if not prev or now - datetime.fromisoformat(prev["last_seen"]) > timedelta(hours=CARRY_OVER_HOURS):
        return None
    keep = ("platform", "first_seen", "last_seen", "last_rank", "peak_rank")
    return {**{k: prev[k] for k in keep}, "ranks": []}


def update_item(daily, prev_daily, src, rank, raw, now, crawl_time, prev_crawl_time):
    """把这次抓到的一条热点写进当天归档，返回给 latest 用的扁平记录。"""
    key = f"{src['id']}:{raw.get('id') or raw['title']}"
    item = daily["items"].get(key) or carry_over(prev_daily["items"].get(key), now)
    if item and item.get("last_seen") == crawl_time:
        return None  # 同一个榜单里重复出现，只记第一次

    if item is None:
        # 第一次运行没有上一轮可比，标成 first，不算"新上榜"
        status, change = ("new" if prev_crawl_time else "first"), None
        item = {"platform": src["id"], "first_seen": crawl_time, "peak_rank": rank, "ranks": []}
    elif item["last_seen"] == prev_crawl_time:
        change = item["last_rank"] - rank  # 正数 = 排名上升
        status = "up" if change > 0 else "down" if change < 0 else "same"
    else:
        status, change = "back", None  # 之前上过榜，中间掉了，又回来

    extra = raw.get("extra") or {}
    item.update(
        title=raw["title"].strip(),
        url=raw.get("url") or raw.get("mobileUrl") or "",
        info=extra.get("info") if isinstance(extra.get("info"), str) else "",
        hover=(extra.get("hover") or "")[:HOVER_MAX] if isinstance(extra.get("hover"), str) else "",
        last_seen=crawl_time,
        last_rank=rank,
        peak_rank=min(item["peak_rank"], rank),
    )
    start = extra.get("topic_start")
    if isinstance(start, (int, float)) and start > 0:
        # 平台自己记录的话题开始时间（目前只有抖音有），比我们第一次抓到的时间更准
        item["topic_start"] = datetime.fromtimestamp(start, TZ).isoformat(timespec="minutes")
    item["ranks"].append([now.strftime("%H:%M"), rank])
    daily["items"][key] = item

    hours = (now - datetime.fromisoformat(item["first_seen"])).total_seconds() / 3600
    return {
        "key": key,
        "platform": src["id"],
        "platform_name": src["name"],
        "group": src["group"],
        "rank": rank,
        "title": item["title"],
        "url": item["url"],
        "info": item["info"],
        "hover": item["hover"],
        "status": status,
        "change": change,
        "peak_rank": item["peak_rank"],
        "first_seen": item["first_seen"],
        "hours_on_list": round(hours, 1),
        "topic_start": item.get("topic_start", ""),
    }


def trajectory(key, daily, prev_daily, recent_times):
    """最近几次抓取的排名，0 表示那次不在榜；上榜之前的 0 去掉。"""
    ranks = {}
    for d in (prev_daily, daily):
        item = d["items"].get(key)
        if item:
            ranks.update((f"{d['date']}T{t}", r) for t, r in item["ranks"])
    points = [[t[11:], ranks.get(t, 0)] for t in recent_times]
    while points and points[0][1] == 0:
        points.pop(0)
    return points


# ---------- 导出：data/latest.json / data/latest.md ----------

def save_latest_json(latest):
    head = {k: v for k, v in latest.items() if k not in ("failed_sources", "items")}
    failed = [json.dumps(f, ensure_ascii=False) for f in latest["failed_sources"]]
    items = [json.dumps(it, ensure_ascii=False) for it in latest["items"]]
    text = dump_one_per_line(head, [("failed_sources", failed, False), ("items", items, False)])
    (DATA_DIR / "latest.json").write_text(text, "utf-8")


def mark(it):
    if it["status"] == "new":
        return "🆕"
    if it["status"] == "back":
        return "↩回榜"
    if it["change"]:
        return f"↑{it['change']}" if it["change"] > 0 else f"↓{-it['change']}"
    return ""


def save_latest_md(latest, sources):
    t = datetime.fromisoformat(latest["crawl_time"])
    lines = [
        f"# 全网热榜 · {t:%Y-%m-%d %H:%M}",
        "",
        f"共 {len(sources) - len(latest['failed_sources'])} 个平台、{len(latest['items'])} 条"
        + (f"｜抓取失败：{'、'.join(f['name'] for f in latest['failed_sources'])}" if latest["failed_sources"] else ""),
        "",
        "标记：🆕 新上榜 · ↑↓ 和上次抓取相比的排名变化 · ↩回榜 之前上过榜又回来 · "
        "轨迹 = 最近几次抓取的排名（约 2 小时一次），0 表示那次不在榜 · "
        "在榜 = 首次上榜至今的小时数 · 最高 = 上榜以来的最高排名 · 始于 = 抖音记录的话题开始时间",
    ]
    by_platform = {}
    for it in latest["items"]:
        by_platform.setdefault(it["platform"], []).append(it)

    group = None
    for src in sources:
        rows = by_platform.get(src["id"])
        if not rows:
            continue
        if src["group"] != group:
            group = src["group"]
            lines += ["", f"## {group}"]
        lines += ["", f"### {src['name']}"]
        for it in rows:
            text = f"{it['rank']}. {it['title']}"
            if it["info"]:
                text += f"（{it['info']}）"
            tags = [mark(it)] if mark(it) else []
            if len(it["trajectory"]) >= 2:
                tags.append("轨迹 " + "→".join(str(r) for _, r in it["trajectory"]))
            if it["status"] not in ("new", "first"):
                tags += [f"在榜 {it['hours_on_list']:g}h", f"最高 #{it['peak_rank']}"]
            if it["topic_start"]:
                tags.append(f"始于 {datetime.fromisoformat(it['topic_start']):%m-%d %H:%M}")
            lines.append(text + (" · " + " · ".join(tags) if tags else ""))
    (DATA_DIR / "latest.md").write_text("\n".join(lines) + "\n", "utf-8")


def main():
    now = datetime.now(TZ).replace(second=0, microsecond=0)
    crawl_time = now.isoformat(timespec="minutes")
    daily = load_daily(now.date())
    prev_daily = load_daily(now.date() - timedelta(days=1))
    if daily["crawls"] and daily["crawls"][-1]["time"] == crawl_time:
        print("这一分钟已经抓过了，跳过")
        return
    last_crawls = daily["crawls"] or prev_daily["crawls"]
    prev_crawl_time = last_crawls[-1]["time"] if last_crawls else None

    sources = load_sources()
    items, failed = [], []
    for i, src in enumerate(sources):
        if i:
            time.sleep(REQUEST_INTERVAL)
        try:
            raw_items = fetch(src)
        except RuntimeError as e:
            failed.append({"id": src["id"], "name": src["name"], "error": str(e)[:200]})
            print(f"✗ {src['name']}：{e}")
            continue
        print(f"✓ {src['name']}：{len(raw_items)} 条")
        for rank, raw in enumerate(raw_items, 1):
            row = update_item(daily, prev_daily, src, rank, raw, now, crawl_time, prev_crawl_time)
            if row:
                items.append(row)

    if not items:
        raise SystemExit("所有平台都抓取失败，这次不写入数据")

    recent_times = [c["time"][:16] for c in prev_daily["crawls"] + daily["crawls"]] + [crawl_time[:16]]
    for row in items:
        row["trajectory"] = trajectory(row["key"], daily, prev_daily, recent_times[-TRAJECTORY_POINTS:])

    daily["crawls"].append({"time": crawl_time, "failed": [f["id"] for f in failed]})
    save_daily(daily)
    latest = {
        "crawl_time": crawl_time,
        "previous_crawl_time": prev_crawl_time,
        "failed_sources": failed,
        "items": items,
    }
    save_latest_json(latest)
    save_latest_md(latest, sources)
    print(f"完成：{len(items)} 条，失败 {len(failed)} 个平台")


if __name__ == "__main__":
    main()
