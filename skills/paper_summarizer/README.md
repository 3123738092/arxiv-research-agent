# Skill 3 — paper-summarizer

> Daily arXiv Research Briefing Agent · 成员 C
>
> 从 ranked_papers.json 读取 top-N 论文，用 Claude 抽取结构化摘要（一句话总结 / 核心贡献 / 方法 / 关键词），写入 summarized_papers.json。

## 目录结构

```
skill3_paper_summarizer/
├── SKILL.md                    # StudyClawHub 发布规范
├── README.md                   # 本文件
├── requirements.txt            # 依赖
├── summarizer/                 # 核心包
│   ├── __init__.py             # 惰性公共 API
│   ├── __main__.py             # CLI: python -m summarizer
│   ├── config.py               # SummarizerConfig dataclass
│   ├── prompts.py              # system / user prompt 模板（en/zh）
│   ├── schema.py               # 输出字段规范化 + 校验
│   ├── cache.py                # 基于 arxiv_url 的本地结果缓存
│   ├── client.py               # Anthropic 调用封装（重试 + prompt caching + JSON 解析）
│   ├── pdf_loader.py           # PDF 模式：下载 + 文本抽取
│   └── core.py                 # summarize() 主流程
├── tests/                      # pytest 套件（离线、mock Anthropic）
│   ├── conftest.py
│   ├── test_prompts.py
│   ├── test_schema.py
│   ├── test_cache.py
│   ├── test_client_parsing.py
│   └── test_core_integration.py
├── examples/
│   ├── run_on_sample.py        # 用真实 Claude 跑 3 篇 fixture 论文
│   └── evaluate_summaries.py   # 输出质量启发式评估
├── data/
│   ├── fixtures/               # 开发用小样本
│   │   └── ranked_papers_sample.json
│   └── cache/                  # 本地缓存（自动生成，可安全删除）
└── docs/
    ├── ARCHITECTURE.md
    └── INTEGRATION.md          # 如何替换回主 Agent
```

## 快速开始

```bash
cd skill3_paper_summarizer
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."

# 跑离线测试（不花 token）
python -m pytest tests/ -q

# 跑真实 Claude（在 fixture 上）
python examples/run_on_sample.py

# 在主项目的 ranked_papers.json 上跑
python -m summarizer
```

## 关键设计

1. **严格的数据契约**：输出字段和 `TEAM_GUIDE.md §5` 完全一致，下游 Skill 4/5 无需改动即可消费。
2. **Prompt caching**：system prompt 标记为 `cache_control=ephemeral`，同一次运行内多批次只首批付费。
3. **本地缓存**：key = `sha1(arxiv_url + mode + model + language)`，避免重复调用。
4. **容错**：
   - JSON 解析失败的 batch → 用 `empty_summary()` 兜底，不影响其它论文；
   - Anthropic 瞬时错误（429/5xx/网络）→ 指数退避重试，最多 3 次；
   - schema 规范化：`keywords: "rl, robotics"` 这种字符串也会自动转成 list。
5. **两种模式**：
   - `mode="abstract"`（默认）— 只用摘要，快、省；
   - `mode="pdf"` — 下载 PDF 抽全文，信号更强但更慢；需要 `pypdf`。
6. **两种语言**：`language="en"` / `language="zh"`。
7. **惰性导入**：只测 prompt/schema/cache 时不需要安装 `anthropic`。

## 对外 API

```python
from summarizer import summarize, SummarizerConfig

cfg = SummarizerConfig(
    top_n=20,
    batch_size=10,
    language="en",          # or "zh"
    mode="abstract",         # or "pdf"
    enable_prompt_cache=True,
    enable_local_cache=True,
)

result = summarize(ranked_papers, cfg=cfg)
# result[0:top_n] 已附加 one_line_summary / key_contributions / methods / keywords
```

## 质量评估

```bash
python examples/evaluate_summaries.py
```

会打印四个启发式指标，开发中用来检测 prompt / model 改动带来的回归：
- `coverage_rate` — 4 个字段都非空的论文比例
- `method_specificity` — 方法名里非通用词（"transformer" 等被扣分）的比例
- `keyword_abstract_overlap` — 关键词在 abstract 中出现的比例
- `avg_summary_len_words` — 一句话摘要的平均词数，目标 15~30

## 与主项目的集成

见 `docs/INTEGRATION.md`。最简单的做法：

```python
# project/skills/paper_summarizer.py
from skill3_paper_summarizer.summarizer import summarize  # noqa: F401
```

或直接复制 `summarizer/` 包到 `skills/`。
