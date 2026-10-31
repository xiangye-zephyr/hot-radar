# 热点雷达（hot-radar）

定时抓取全网 21 个热榜（抖音、微博、B站等），记录每条热点的排名变化；Codex 按 [AGENTS.md](AGENTS.md) 从中挑出能做的热点，写成简报。

- **抓取**：GitHub Actions 定时运行 `crawl.py`，不需要服务器，电脑关机也照常抓
- **数据**：抖音用官方热榜接口（免登录，带热度值和话题开始时间），其他平台来自 [newsnow](https://github.com/newsnext/newsnow) 的公开接口
- **分析**：Codex 读数据、出简报、记录发布效果

## 目录

| 路径 | 作用 |
|---|---|
| `crawl.py` | 抓取 → 归档 → 导出，只用 Python 标准库 |
| `sources.json` | 抓哪些平台，增删平台改这里 |
| `data/latest.md` | 最新一次的全量热榜，人和 Agent 都好读 |
| `data/latest.json` | 同上，带全部字段（摘要、链接、排名变化等） |
| `data/daily/YYYY-MM-DD.json` | 每天的归档，记录每条热点每次抓取时的排名 |
| `build_db.py` | 把归档汇总成本地 SQLite（`data/hot.db`），方便跨天查询；不提交到仓库 |
| `AGENTS.md` | Codex 的工作手册：怎么筛、怎么写简报、怎么记录 |
| `tools/refresh.sh` | 出简报前手动触发一次 GitHub 抓取，等跑完再拉到本地 |
| `briefs/` | Codex 出的每份简报，**只存在本地**，同时发到飞书；不上传到这个公开仓库 |
| `tools/push_topics.py` | 把简报里的选题写进飞书「选题与发布」表，一条一行 |
| `tools/topics_summary.py` | 读「选题与发布」表，输出最近 30 天的简短汇总（选中过的选题、选中率、发布效果） |
| `tools/publish_brief.py` | 把简报发到飞书「热点简报」：每天一篇，早午晚依次追加 |
| `feishu.local.json` | 飞书知识库里各个位置的编号，**只存在本地**，不上传 |
| `.github/workflows/crawl.yml` | 定时抓取的配置 |

## 本地运行

```bash
python3 crawl.py
```

## 部署到 GitHub

1. 在 GitHub 新建一个**公开**仓库（比如 `hot-radar`），把这个文件夹推上去。公开仓库的 Actions 免费、不限时长。
2. 打开仓库的 **Actions** 页，选「抓取热榜」→ **Run workflow**，手动跑一次，确认成功。
3. 之后它每小时第 23 分钟尝试运行一次。GitHub 的定时任务经常被跳过或推迟（实测一晚上只跑成了两次），所以 Codex 出简报前会运行 `tools/refresh.sh`，手动触发一次抓取，等它跑完再拉到本地，保证简报用的是最新数据。

## Codex 怎么用

1. 在 Codex（ChatGPT 桌面端）打开这个项目文件夹，它会自动读 `AGENTS.md`。
2. 在 **Scheduled** 里建三个定时任务，项目选这个文件夹：

   | 任务 | 时间 | 提示词 |
   |---|---|---|
   | 早报 | 每天 9:40 | 按 AGENTS.md 出今天的早报 |
   | 午报 | 每天 13:00 | 按 AGENTS.md 出今天的午报 |
   | 晚报 | 每天 18:30 | 按 AGENTS.md 出今天的晚报 |

3. **网络权限**：简报前要 `git pull`、写完要 `git push`，需要联网。Codex 默认的沙箱会拦住联网的命令，需要给这个项目放开网络权限，或者给 git 命令加白名单规则。
4. **抖音热点宝**：判断一个梗在抖音上还有没有人在拍，Codex 会用本机的 `douhot` 工具读抖音热点宝。它要用一个登录了抖音的专用 Chrome，这个 Chrome 由 `~/Documents/Codex/2026-10-15/dou-s/outputs/run_douhot_mcp.sh` 在 Codex 用到时自动在后台无界面启动，平时不用管。抖音登录过期时，简报开头会提示"热点宝：未连接"，这时双击同一个文件夹里的 `热点宝重新登录.command`，扫码后按 ⌘Q 关掉弹出的 Chrome 即可。
5. **注意**：Codex 的定时任务要求电脑开着、ChatGPT 桌面端在运行。电脑关着的时候不会出简报，但抓取在 GitHub 上照常进行，数据不会断。也可以随时在对话里说"出一份简报"。

平时的用法：

- 在飞书知识库「账号规划 / 热点雷达 / 热点简报」里看简报，每天一篇。
- 简报里的推荐、梗、可以试试会自动写进「热点雷达 / 选题与发布」表。打开「今日选题」视图挑选题，把状态改成"选中"；做的时候改"制作中"，发了改"已发布"并填视频链接；发布后 24 小时和 7 天各补一次播放、点赞、评论、分享（「待补数据」视图会列出还没补的）。
- 不是从简报来的视频也加一行，栏目选"自选"。
- Codex 出简报前会读这张表的汇总：选中过的不再推荐，常被选中、效果好的同类往前排。
- 看中哪条想细化，在 Codex 里说"展开第 3 条"。
- 飞书用的是本机的 `lark-cli`（用户身份）。登录失效时，简报照样存在本地，只是发不到飞书、也读写不了选题表。

## 常改的地方

| 想改什么 | 改哪里 |
|---|---|
| 增删平台 | `sources.json`。可用的平台 ID 见 newsnow 的 [sources.json](https://github.com/newsnext/newsnow/blob/main/shared/sources.json)，加之前先用 `python3 crawl.py` 试一下 |
| 抓取频率 | `.github/workflows/crawl.yml` 里的 `cron`（UTC 时间） |
| 筛选规则、简报格式 | `AGENTS.md` |
| 换成自己部署的 newsnow | 设置环境变量 `NEWSNOW_API`，比如 `https://你的域名/api/s` |

## 已知限制

- 快手、36氪在 newsnow 里已停用；小红书、什么值得买没有可用的数据源。
- 抖音官方接口失败时会自动退回 newsnow，那一次就没有热度值和话题开始时间。
- IT之家、AI热点是滚动资讯，不是热榜，所以"新上榜"会比较多。
