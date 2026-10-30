#!/bin/bash
# 出简报前用：让 GitHub 立刻抓一次热榜，等它跑完再拉到本地。
# GitHub 的定时任务经常被跳过或推迟，这样能保证简报用的是最新数据。
# 失败了也不中断，退回仓库里现有的数据。
set -u
cd "$(dirname "$0")/.." || exit 1
GH="${GH:-$HOME/.local/bin/gh}"
REPO="xiangye-zephyr/hot-radar"

latest() {
  python3 -c "import json; print('数据时间：' + json.load(open('data/latest.json'))['crawl_time'])"
}

if ! "$GH" workflow run crawl.yml --repo "$REPO" >/dev/null 2>&1; then
  echo "没能触发抓取（gh 没登录或网络问题），用仓库里现有的数据"
  git pull -q
  latest
  exit 0
fi

# 等刚触发的那次运行出现，然后等它跑完
RUN=""
for _ in $(seq 1 20); do
  sleep 3
  RUN=$("$GH" run list --repo "$REPO" --workflow crawl.yml --event workflow_dispatch --limit 1 \
    --json databaseId,status --jq '.[0] | select(.status != "completed") | .databaseId')
  [ -n "$RUN" ] && break
done
if [ -n "$RUN" ] && ! "$GH" run watch "$RUN" --repo "$REPO" --exit-status --interval 10 >/dev/null 2>&1; then
  echo "这次抓取没成功，用仓库里现有的数据"
fi
git pull -q
latest
