#!/usr/bin/env python3
"""把 data/daily/*.json 汇总成本地 SQLite（data/hot.db），方便跨天查询趋势。

hot.db 不提交到仓库，每次运行都从归档重建：python3 build_db.py
"""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "hot.db"

SCHEMA = """
CREATE TABLE crawls (time TEXT PRIMARY KEY, failed TEXT);
CREATE TABLE items (
    date TEXT, key TEXT, platform TEXT, title TEXT, url TEXT, info TEXT,
    first_seen TEXT, last_seen TEXT, peak_rank INTEGER,
    PRIMARY KEY (date, key)
);
CREATE TABLE ranks (date TEXT, key TEXT, time TEXT, rank INTEGER);
CREATE INDEX idx_ranks_key ON ranks (key);
CREATE INDEX idx_items_title ON items (title);
"""


def main():
    DB_PATH.unlink(missing_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    days = sorted((ROOT / "data" / "daily").glob("*.json"))
    for path in days:
        daily = json.loads(path.read_text("utf-8"))
        date = daily["date"]
        con.executemany(
            "INSERT INTO crawls VALUES (?, ?)",
            [(c["time"], ",".join(c["failed"])) for c in daily["crawls"]],
        )
        for key, it in daily["items"].items():
            con.execute(
                "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (date, key, it["platform"], it["title"], it["url"], it.get("info", ""),
                 it["first_seen"], it["last_seen"], it["peak_rank"]),
            )
            con.executemany(
                "INSERT INTO ranks VALUES (?, ?, ?, ?)",
                [(date, key, t, r) for t, r in it["ranks"]],
            )
    con.commit()
    con.close()
    print(f"已从 {len(days)} 天的归档重建 {DB_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
