---
name: papers-analysis-visualizer
description: >
  Build a research dashboard and visual analytics summary from structured paper data, focusing on paper recommendation, keyword network visualization and topic trend exploration.
author: RuipengYu
version: 1.0.0

---

# Paper Analysis Visualizer

## Purpose

Use this skill to transform a ranked paper list into two interactive visualization modules:
1. An interactive research database/dashboard for organized paper collection and convenient human browsing in Notion via provided API;
2. Interactive visualizations of macro information, including topic structures, keywords correlations and trends of certain topics.

This skill focuses on:
- receiving structured paper data from the upstream agent (search / summarization pipeline)
- guiding users to set up Notion connections with this agent
- presenting papers in a notion database via user provided API
- highlighting recommended papers with concise, visual-first signals
- showing keyword/topic structure through an interactive keyword network
- showing topic-level trends when historical data is available

This skill is designed for users who want to quickly understand:
- which papers are most worth reading in user's interested direction
- what is the key takeaway of each paper
- what topics are currently the hottest
- which keywords are central or potentially emerging
- how these keywords/topics correlate with others
- how a topic evolves over time 

---

## Use this skill when

Use this skill when the user asks for any of the following (or similar request):

- a collection of recommended papers
- a paper dashboard/database
- a notion paper database
- an interactive paper browser
- keyword network visualization
- topic hotspot overview
- topic trend analysis
- a visual summary of ranked papers
- a clickable interface for browsing paper results

Typical requests include:
- “帮我整理这些paper”
- “帮我把这些 paper 整理进notion数据库”
- “给我在Notion建一个论文整理库”
- “展示关键词网络和热点主题”
- “整理这个主题/关键词相关的主题/关键词”
- “点开关键词后可以看趋势”
- “把这些论文整理做成可交互可浏览的图形界面”

---

## Do not use this skill for

Do not use this skill for:
- fetching papers from arXiv
- generating paper summaries from raw abstracts
- writing the final daily report narrative
- making claims with hallucinations that require information not present in the input data
- setting up Notion Inner Connection or fetch API

This skill does **not**:
- set up Notion Inner Connection or fetch API for users
- infer facts not supported by the input sources
- perform deep full-paper analysis
- fabricate author relations, topic evolution, or novelty claims
- translate academic keywords such as CV, Agent, Skill into Chinese

---

## User Setup（notion集成前置配置）

**每次启动本 skill 时，主动询问用户是否需要 Notion 同步。** 用对应语言向用户提问，等他回复。

<div data-language="zh">
🔗 是否需要将这批论文同步到你的 Notion 论文库？（可以长期积累、随时检索）

- 如果 **需要**：请先完成 3 步配置 →
- 如果 **不需要**：直接生成 Dashboard，跳过 Notion

---

**配置步骤（一次性，3 min）：**

**第 1 步：创建 Notion Integration**
1. 打开 https://www.notion.so/my-integrations
2. 点击「新建集成」→ 名称填 `Papers Analysis` → 选择你的工作区 → 提交
3. 复制 `Internal Integration Secret`

**第 2 步：准备父页面并授权**
1. 在 Notion 中新建或选择一个页面作为论文库
2. 点右上角 `⋯` → 「连接」→ 添加 `Papers Analysis`
3. 复制页面 URL 中的 ID（32 位字符串）

**第 3 步：写入配置**
在项目根目录的 `.env` 文件中写入：
```
NOTION_API_TOKEN=你的_token
NOTION_PARENT_PAGE_ID=你的_页面_ID
```

完成后告诉我，我先帮你验证连通性。
</div>

<div data-language="en">
🔗 Do you want to sync these papers to your Notion database for long-term management?

- **Yes**: I'll guide you through a one-time 3-step setup
- **No**: I'll skip Notion and only generate the dashboard

---

**Setup (one-time, ~3 min):**

**Step 1: Create Notion Integration**
1. Go to https://www.notion.so/my-integrations
2. Click "New Integration" → name it `Papers Analysis` → select workspace → Submit
3. Copy the `Internal Integration Secret`

**Step 2: Prepare parent page and grant access**
1. Create or choose a page in Notion as your paper database home
2. Click `⋯` → "Connections" → add `Papers Analysis`
3. Copy the page ID from the URL (32-char string)

**Step 3: Write config**
Add to `.env` in project root:
```
NOTION_API_TOKEN=your_token
NOTION_PARENT_PAGE_ID=your_page_id
```

Reply "done" and I'll verify the connection for you.
</div>
Your Notion workspace hasn't been connected yet. 3 steps:

**Step 1: Create a Notion Integration**
1. Open https://www.notion.so/my-integrations
2. Click "New Integration"
3. Name it `Papers Analysis`, select your workspace
4. Submit and copy the `Internal Integration Secret` (starts with `ntn_` or `secret_`)

**Step 2: Prepare a Notion page and grant access**
1. Create or use an existing page in Notion as the parent page for your paper database
2. Open the page → top-right `⋯` → "Connections" → search and add `Papers Analysis`
3. Copy the page ID from the URL (`https://www.notion.so/xxxxxxxxxxxxxxxx?v=...` — the 32-char `xxxxxxxx` part)

**Step 3: Configure the project**
In the project's `.env` file, add:
```
NOTION_API_TOKEN=your_internal_integration_secret
NOTION_PARENT_PAGE_ID=your_page_id
```

Reply "done" and I'll verify the connection for you.
</div>

If the user reports issues during setup, assist with troubleshooting (check token format, verify Connections, confirm page ID).
If the user chooses not to set up Notion, proceed with dashboard-only mode (skip Notion sync).

---

## Inputs

### Required Inputs

Input must include: 

1. User's Notion Connection setup information:
  - NOTION_API_TOKEN
  - NOTION_PARENT_PAGE_ID or NOTION_DATABASE_ID

2. A ranked paper list:

  Each paper entry should contain at least the following information:
  - 'paper_id'
  - 'title'
  - 'url'
  - 'relevance_score'
  - 'novelty_score'
  - 'one_line_summary'
  - 'keywords'

  Recommended additional fields:
  - 'authors'
  - 'published_date'
  - 'category'
  - 'community_label'

  Example input schema: 
  ```/references/input_schema.md```

### Input Adaptation（llm驱动）

上游（paper_summarizer）输出的 `shared_data/summarized_papers.json` 格式与本 skill 期望格式有差异。agent 在传入脚本前，需按以下规则就地转换：

**1. 解包信封**：如果输入是 `{count, papers: [...]}` 结构 → 只取 `papers` 数组。

**2. 字段映射**：
| 上游字段 | 目标字段 | 转换规则 |
|---------|---------|---------|
| `arxiv_url` | `url` | 直接复制 |
| `arxiv_id`（如 `2308.08155`） | `paper_id` | 加前缀 `arxiv:` → `arxiv:2308.08155` |
| （缺失） | `published_date` | 留空字符串 `""` |
| （缺失） | `category` | 留空字符串 `""` |
| （缺失） | `community_label` | 留空字符串 `""` |

**3. 保留已有字段**：`title`、`relevance_score`、`novelty_score`、`one_line_summary`、`keywords` 字段名一致，原样保留。

转换后的 `[{paper_id, url, ...}]` 数组写入临时 JSON，再传入 `--input`。

### Optional Inputs

Historical data may be provided for real trend analysis.

Accepted optional historical inputs include:
- archived paper lists from previous days/weeks
- keyword frequency time series
- topic-level daily/weekly counts

If historical data is not available:
- trend charts must fall back to current-batch topic distribution only
- “emerging keywords” must be treated as heuristic candidates rather than factual trend claims

## Outputs

### 1. Notion 论文库

A Notion database created under the user's specified page. Each paper becomes a database item with the following properties:

| Property | Type | Source |
|---|---|---|
| Title | title | `title` |
| URL | url | `url` |
| Paper ID | rich_text | `paper_id` |
| Relevance | number | `relevance_score` |
| Novelty | number | `novelty_score` |
| Recommendation | number | computed by `compute_analytics.py` |
| Summary | rich_text | `one_line_summary` |
| Keywords | multi_select | `keywords` |
| Category | select | `category` |
| Community | select | `community_label` |
| Published Date | date | `published_date` |
| Status | select | default `Unread` |

Output file: `data/notion_mapping.json` — `paper_id → notion_url` 映射，供 dashboard 做 "Open in Notion" 跳转。

### 2. Topic Exploration Dashboard

自包含的 HTML 文件 (`output/dashboard.html`)，浏览器直接打开。页面包含：

- **Overview**：论文总数、最热关键词、最活跃社区、高分论文数
- **Keyword Network**：力导向共现网络，节点大小 = 频次，边 = 共现关系，支持 zoom / drag / pan / click
- **Topic Detail Panel**：点击关键词后展示相关论文数、关联关键词、趋势图、推荐论文列表
- **Linked Papers Preview**：选中 topic 的论文卡片（title、推荐指数、一句话概括、arXiv 链接、Notion 跳转按钮）

### 3. Machine-readable Output

- `data/analytics_summary.json` — 总览统计 + 关键词频次 + 共现图数据

---

## Available Tools

本 skill 由两个tool脚本支持实现，agent 根据用户请求选择调用：

### Tool A: `sync_to_notion.py` — Notion 论文同步

**触发条件**：用户提到"同步到 Notion""归档论文""创建论文库""保存到 Notion""整理进notion"等。

**前置条件**：`.env` 中已配置 `NOTION_API_TOKEN` + `NOTION_PARENT_PAGE_ID` 或 `NOTION_DATABASE_ID`。未配置时先执行 User Setup 流程。

**输入**：论文 JSON 文件路径（`--input`）

**行为**：在 Notion 创建/更新数据库条目，按 `paper_id` 去重（已存在则更新，不存在则新建）。若 `NOTION_DATABASE_ID` 未设置，自动在父页面下创建数据库。

**数据库命名**：根据用户原始 query 推断一个简短的中文标题，通过 `--db-title` 传入。例如：
- 用户说"我想了解 LLM Agent 相关论文" → `--db-title "LLM Agent 论文"`
- 用户说"帮我看 MCP 的 paper" → `--db-title "MCP 论文"`
- 未指定主题 → 默认 `"论文库"`

**输出**：`data/notion_mapping.json`（`--output`）

**CLI**：
```bash
python scripts/sync_to_notion.py --input data/input.json --output data/notion_mapping.json --db-title "LLM Agent 论文"
```

### Tool B: `build_dashboard_html.py` — 交互式 Topic Dashboard

**触发条件**：用户提到"可视化""关键词网络""趋势图""dashboard""探索""浏览论文""图形界面"等。

**输入**：论文 JSON + 可选历史数据 + 可选 `notion_mapping.json`（有则渲染 Notion 跳转按钮）

**输出**：`output/dashboard.html`（自包含，浏览器直接打开）

**CLI**：
```bash
python scripts/build_dashboard_html.py --input data/input.json --output output/dashboard.html
```

### Arrangement Rules

```
上游论文 JSON
  → compute_analytics.enrich_papers()  ← 计算 recommendation 等衍生字段
    ├─ sync_to_notion.py               ← 用户要求同步时执行
    └─ build_dashboard_html.py         ← 用户要求可视化时执行
```

Agent 根据用户的一句话请求决定执行哪个（或两者都跑）：
- "帮我梳理这些论文" → 两者都跑
- "归档/同步到 Notion" → 只跑 Tool A
- "给我看关键词网络" → 只跑 Tool B

---

## Style Requirements

- visual-first presentation: don't give too many complex literal presentation 
- dominant UI text should follow the user's most recent language (example: use Chinese UI text if the user prompts in Chinese)
- UI text should be concise and clear
- academic terms, paper keywords, and topic names must remain in original English wording
- avoid dense paragraphs
- prioritize charts, cards, badges, and compact labels over long narrative text
- the overall dashboard should support quick scanning and exploration

---

## Interaction Requirements

### 1. Paper interactions
- each paper entry must be clickable
- clicking a paper opens the original paper link

### 2. Keyword network interactions
- support zoom
- support drag
- support pan
- support hover or click for keyword inspection
- once clicking a keyword, switch the keyword bubble to center peek page to show its related papers and topic trend

### 3. Topic trend interactions
- clicking a keyword should update or reveal the corresponding topic trend section
- when possible, related papers under the selected topic should also be shown

---

## Language Policy

- overall interface language: Follow the user's most recent input language
- academic keywords, research topics, and paper terms: keep original wording
- paper titles: keep original wording
- concise UI labels may be written in Chinese

---

## Constraints

### Data constraints
- do not fabricate unsupported facts
- all displayed information must come directly from input fields or be computed from them
- do not introduce hidden metadata not present in the input

### Content constraints
- do not overload the page with large text blocks 
- do not output verbose paper-by-paper essays inside the dashboard
- do not translate academic terms such as CV, Agent, Skill into Chinese

### UX constraints
- keep text concise
- keep visual hierarchy clear
- prioritize readability and interactivity over - decorative complexity


---

## Failure/Fallback

### 数据质量问题
- 论文字段缺失：跳过不支持的图表元素，保留其余 dashboard
- 历史数据缺失：禁用真实时间序列模式，降级为当前 topic 分布
- 关键词数据过于稀疏：展示简化关键词摘要，不渲染密集网络

### Notion API 异常
- Token 无效或过期：提示用户检查 `.env` 中的 `NOTION_API_TOKEN`
- Integration 未关联父页面：提示用户检查页面 Connections 设置
- API 限流 (429)：自动重试 3 次，间隔递增（1s / 3s / 5s）；仍失败则跳过该条目继续后续
- 网络超时：打印错误信息，继续处理剩余论文，最后汇总失败条目

### 通用降级原则
- 任一 Tool 失败不影响另一 Tool（sync 失败不阻止 dashboard 生成，反之亦然）
- 所有错误输出到 stderr，不影响 stdout 的 pipeline 串联

---

## Dependency

- Python 3.11+
- `requests` — Notion API 调用
- `python-dotenv` — 读取 `.env` 凭据
- `jinja2` — HTML 模板渲染
- `pytest` — 测试

```bash
pip install requests python-dotenv jinja2 pytest
```

---

## Recommended Workflow

### 首次使用（用户侧一次性配置）

1. 创建 Notion Integration → 获取 token
2. 准备 Notion 父页面 → 添加 integration 到 Connections
3. 将 token 和页面 ID 写入 `.env`

### 每次使用（Agent 自动执行）

```
1. 上游 agent 产出论文 JSON
2. compute_analytics.enrich_papers() 计算衍生字段
3. sync_to_notion.py 同步到 Notion（用户要求时）
4. build_dashboard_html.py 生成 dashboard.html（用户要求时）
5. 用户浏览器打开 dashboard.html 探索
```

### 日常使用

- 每日论文 batch 追加同步到同一 Notion 数据库（`paper_id` 自动去重）
- Dashboard 每次生成最新的独立 HTML
- `notion_mapping.json` 随每次 sync 更新，dashboard 自动读取最新的 Notion 链接