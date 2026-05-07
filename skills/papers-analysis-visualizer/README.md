# Papers Analysis Visualizer

将结构化论文分析结果转化为 **Notion 论文知识库** + **交互式 Topic Exploration Dashboard** 的 agent skill。

## 核心理念

> **Notion 负责 paper collection / long-term knowledge management；网页负责 interactive topic exploration / hotspot discovery。**

两条输出链路各司其职——Notion 用来长期积累、检索、管理论文；
网页用来以交互可视化的方式帮助用户更好的了解topics/keywords之间的关联、新兴趋势等等。

## 输入

上游 agent 输出的结构化论文列表（JSON），每篇包含：

| 字段 | 说明 |
|------|------|
| `paper_id` | 唯一标识 |
| `title` | 论文标题 |
| `url` | arXiv / 论文页面链接 |
| `relevance_score` | 相关性分数 (0-10) |
| `novelty_score` | 新颖性分数 (0-10) |
| `one_line_summary` | 一句话概括 |
| `keywords` | 关键词列表 |
| `published_date` | 发布日期 |
| `category` | arXiv 分类 |
| `community_label` | 上游聚类标签 |

详见 [references/input_schema.md](references/input_schema.md)。

## 输出

### 1. Notion 论文库

每篇论文作为一条 database item 写入用户 Notion 空间，包含完整的 properties（分数、关键词、分类、推荐指数等），支持长期积累、检索、人工补注释。

### 2. Topic Exploration Dashboard

自包含的交互式 HTML 页面，以 topic 关系为中心：

| 区域 | 说明 |
|------|------|
| Overview 概览 | 论文总数、最热关键词、最活跃社区、高分论文数 |
| Keyword Network 关键词网络 | 力导向图，节点=关键词，边=共现关系，热点突出，支持拖拽缩放 |
| Topic Detail Panel | 点击关键词后展示：相关论文数、关联关键词、趋势图、推荐论文列表 |
| Linked Papers Preview | 选中 topic 的论文卡片（title、推荐指数、一句话概括、arXiv 链接、Notion 跳转） |

## 技术栈

- 管线：Python 3.11+ + jinja2，通过 Notion API 同步论文库
- 前端：ECharts 5.5+ (CDN)，纯 CSS，数据内嵌至 HTML
- 输出：自包含单一 HTML 文件（浏览器直接打开）+ Notion database

## 项目结构

```
papers-analysis-visualizer/
├── SKILL.md                       # Skill 功能定义
├── README.md                      # 本文件
├── scripts/
│   ├── run_visualizer.py          # 管线总入口
│   ├── compute_analytics.py       # 衍生数据计算（recommendation、关键词频次、共现矩阵、趋势等）
│   ├── build_dashboard_html.py    # HTML 生成（jinja2 渲染 + 数据内嵌）
│   ├── sync_to_notion.py          # Notion API 同步
│   └── utils.py                   # 共享工具
├── templates/
│   ├── dashboard.html             # Jinja2 HTML 骨架
│   └── style.css                  # 仪表盘样式
├── references/
│   ├── input_schema.md            # 输入数据格式
│   ├── output_schema.md           # 输出格式说明
│   └── visualization_rules.md     # 可视化设计细则
├── output/                        # 生成的 dashboard
├── data/                          # 运行时输入数据
└── tests/
    ├── fixtures/
    │   ├── sample_basic.json
    │   ├── sample_missing_fields.json
    │   └── sample_history.json
    └── outputs/
```

## Recommendation Score 公式

```
recommendation = 0.6 × relevance_score + 0.4 × novelty_score
```

简单、可解释，后续可扩展。

## 开发阶段

### 阶段一：数据契约与骨架 ✅

- [x] 项目骨架搭建
- [x] SKILL.md 功能定义
- [x] 输入/输出 schema 确定
- [x] 实现规划定稿
- [x] Notion API 可行性验证

### 阶段二：Analytics Layer ✅

- [x] `scripts/compute_analytics.py` — recommendation、关键词频次、共现矩阵、overview stats
- [x] 无历史数据时的 fallback 逻辑
- [ ] `scripts/utils.py` — JSON 加载、schema 校验、归一化（待补充）

### 阶段三：Dashboard Layer ✅

- [x] `templates/dashboard.html` — 页面骨架 + 内嵌 CSS + ECharts 交互
- [x] `scripts/build_dashboard_html.py` — jinja2 渲染 + 数据内嵌
- [x] Keyword network 交互（zoom/drag/pan/click）
- [x] Topic detail panel 联动
- [x] Linked papers preview（arXiv 链接 + Notion 跳转）

### 阶段四：Notion Sync Layer ✅

- [x] `scripts/sync_to_notion.py` — database 自动创建、paper 去重同步
- [x] Notion API 配置（token + page/database ID，通过 `.env`）
- [x] Dashboard 中 "Open in Notion" 跳转

### 阶段五：CLI 与集成

- [ ] `scripts/run_visualizer.py` — 总入口，串联全流程
- [ ] 命令行参数：`--input`、`--output`、`--history`、`--sync-notion`
- [ ] 与上游 agent 集成

### 阶段六：测试

- [x] 测试 fixtures（3 篇样例论文）
- [ ] 单元测试（计算逻辑、HTML 生成、Notion 同步）
- [ ] 端到端联调

## 运行

```bash
# 同步到 Notion（自动创建数据库 + 去重）
python scripts/sync_to_notion.py --input data/input.json --output data/notion_mapping.json

# 生成 Dashboard（自包含 HTML，浏览器直接打开）
python scripts/build_dashboard_html.py --input data/input.json --output output/dashboard.html

# 运行测试
pytest tests/ -v
```

## 环境变量

```bash
# Notion 集成（可选，仅使用 --sync-notion 时需要）
NOTION_API_TOKEN=your_integration_token
NOTION_DATABASE_ID=your_database_id
```

## 关键约束

1. 所有输出数据必须来自输入，**零编造**
2. 学术术语/关键词 **永远不翻译成中文**
3. 优先用图表呈现信息，避免文字堆砌
4. 输出 HTML 必须自包含，浏览器直接打开可用
5. 三个视图（网络、详情面板、论文预览）必须联动
6. 没有历史数据时，不声称存在时间趋势，降级为当前分布
