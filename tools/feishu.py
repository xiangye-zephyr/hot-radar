"""调用本机 lark-cli 的公共部分：读本地配置、执行命令、解析 JSON 输出。"""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LARK = os.environ.get("LARK_CLI", str(Path.home() / ".local/bin/lark-cli"))


class FeishuError(RuntimeError):
    pass


def config():
    path = ROOT / "feishu.local.json"
    if not path.exists():
        raise FeishuError(f"缺少 {path.name}（飞书知识库位置配置，只存在本地）")
    return json.loads(path.read_text("utf-8"))


def lark(*args, stdin=None):
    """执行 lark-cli，返回 data 部分；失败时抛 FeishuError。"""
    proc = subprocess.run(
        [LARK, *args, "--as", "user"], input=stdin, capture_output=True, text=True, timeout=120
    )
    out = proc.stdout + proc.stderr
    start = out.find("{")
    try:
        body = json.loads(out[start:]) if start >= 0 else {}
    except json.JSONDecodeError:
        body = {}
    if proc.returncode != 0 or not body.get("ok"):
        error = body.get("error") or {}
        raise FeishuError(error.get("message") or out.strip()[-300:] or f"lark-cli 退出码 {proc.returncode}")
    return body.get("data") or {}
