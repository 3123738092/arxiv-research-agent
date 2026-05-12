---
name: router
description: |
  Daily arXiv research briefing agent. Fetches today's papers from arXiv (cs.CL/cs.LG/cs.CV/cs.AI/cs.MA),
  ranks them by PageRank + user interest + novelty, summarizes the top-N in-context, builds an interactive
  HTML dashboard, and renders a Markdown briefing. Use this skill for ANY request that asks for a curated
  daily research summary across multiple papers.

  Trigger phrases include:
  - "今日 arxiv 简报" / "今天的 arxiv" / "抓今天的论文" / "做个论文简报"
  - "daily arxiv briefing" / "today's papers on X" / "what's new on arxiv today"
  - "arxiv research digest" / "morning research digest" / "summarize today's papers"
  - "build a research briefing for <topic>" / "give me the top papers on <topic>"

  This skill is a ROUTER. It does not run code itself — it activates 5 sub-skills in order via
  the Skill tool. Each sub-skill owns its own execution details (paths, env vars, commands).
  Skill 3 (summarization) is performed BY YOU, the host LLM, in-context; no external LLM API is called.
  The 5 sub-skills live alongside this one in the same skills/ directory.
version: 2.1.0
author: Han
tags: [arxiv, agent, research, briefing, daily-digest, social-network-analysis, pagerank, llm, router]
agent: router
---

# arXiv Research Briefing Agent — Router

You are the host LLM driving the **arXiv Research Briefing Agent**. This file is a **router**: it tells you *which sub-skill to activate next*, in what order, and with what inputs. Each sub-skill's own `SKILL.md` owns the implementation details — paths, commands, environment setup. Do NOT run Python directly from this file; always delegate via the `Skill` tool.

All sub-skills live in the same `skills/` directory as this router, so they are invoked by simple name (no prefix needed).

> **Reference:** `AGENTS.md` (project root) lists the 5 sub-skills, their `shared_data/` outputs, and the data-flow contract. Read it once if you need the full system view.

---

## When to invoke this router

Activate this entry point when the user's request matches any of:

- "Daily / today's arxiv briefing" (any language)
- "Top papers on `<topic>` today / this week"
- "Build a research digest for `<topic>`"
- "Summarize today's NLP / agent / LLM papers"

If the user asks for a **single sub-task** (e.g. "just rank these papers", "rebuild the dashboard"), do NOT activate this router — invoke the relevant sub-skill directly via `Skill(skill="<sub-skill name>")`.

---

## Parameters to extract from the user

Before activating any sub-skill, parse the user's request into these parameters. Pass them as natural-language inputs to each sub-skill via the `Skill` tool's `args` field.

| Parameter | Default | How to extract |
|-----------|---------|----------------|
| `categories` | `cs.CL cs.LG cs.CV cs.AI cs.MA` | If user names a field (e.g. "NLP" → `cs.CL`, "vision" → `cs.CV`); else default |
| `keywords` | `agent skill "tool use" LLM "language model"` | If user names a topic (e.g. "diffusion models" → `["diffusion", "generative"]`); else default. **Pass `[]` to fetch all papers in the category — never omit.** |
| `interest` | space-joined `keywords` | Natural-language phrasing of the user's interest |
| `top-n` | `10` | If user says "top 5" / "top 20", override |
| `language` | `en` | If user writes Chinese, use `zh` |

If the user gives a generic request ("today's briefing"), use defaults across the board.

---

## Sub-skill registry

Each step below activates a sub-skill by **name**. The names match the `name:` field in each sub-skill's `SKILL.md` frontmatter:

| Step | Sub-skill name | Role |
|------|---------------|------|
| 1 | `data_collector` | Fetch papers, build graph edges, compute embeddings |
| 2 | `paper_ranker` | PageRank + interest match + novelty scoring |
| 3 | `paper_summarizer` | Prepare top-N for host-LLM summarization, then finalize |
| 4 | `briefing_report` | Render Markdown briefing |
| 5 | `papers-analysis-visualizer` | Render interactive HTML dashboard |

Activate each one with `Skill(skill="<name>", args="<parameters in natural language>")`. Each sub-skill's `SKILL.md` documents the exact inputs it expects — read the sub-skill's bootstrap section before running it.

---

## Pipeline recipe (5 stages, sequential)

**Path configuration — RECOMMENDED approach: set `WORKBUDDY_SHARED_DATA` once before running any stage.**

```bash
# Windows (Git Bash)
export WORKBUDDY_SHARED_DATA="C:/Users/31237/WorkBuddy/2026-05-12-task-29/shared_data"

# 然后所有 5 个 stage 无需额外路径参数，自动读写同一目录
```

**`--data-dir` vs `--shared-data` argument semantics per stage:**

| Stage | Recommended argument | What it points to |
|-------|---------------------|-------------------|
| Stage 1 `data_collector` | `--shared-data` | Full `shared_data/` directory |
| Stage 2 `paper_ranker` | `--data-dir` (auto-resolves workspace root → `shared_data/`) | Either workspace root or `shared_data/` directly |
| Stage 3 `paper_summarizer` | `--shared-data` | `shared_data/` directory |
| Stage 4 `briefing_report` | `--data-dir` | Either workspace root or `shared_data/` directly |
| Stage 5 `papers-analysis-visualizer` | `--workspace` (for .env) + `--data-dir` (for paths) | Workspace root |

### Stage 1 — Activate `data_collector`

> **Windows 兼容性**：不要直接传内联 JSON（PowerShell 转义复杂，容易失败）。正确做法是先写入临时配置文件：
> ```bash
> # 写 config 文件
> python -c "import json; ..."
> # 然后用 --config 指向文件
> python scripts/pipeline.py --shared-data "..." --config /path/to/config.json
> ```

Pass the parsed `categories`, `keywords`, and `date_range` (today's date by default).

```
Skill(skill="data_collector",
      args="categories: <cats>; keywords: <kws>; date_range: today (<YYYY-MM-DD>); workspace: <path/to/workspace>")
```

**Path:** Uses `--shared-data` argument internally. If `WORKBUDDY_SHARED_DATA` env is set, uses it directly.

**Expected outputs:** `shared_data/papers.json`, `authors.json`, `edges/*.json`, `embeddings/*`, `manifest.json`.

**Stop conditions:**
- `manifest.json.errors` non-empty → abort, report errors verbatim, ask user whether to retry.
- `manifest.json.counts.after_dedup == 0` → tell user "no new papers today" and stop.

### Stage 2 — Activate `paper_ranker`

Pass the user's `interest` text and workspace path.

```
Skill(skill="paper_ranker",
      args="interest: <natural-language interest text>; workspace: <path/to/workspace>")
```

**Path:** Reads from `<workspace>/shared_data/`. Supports `WORKBUDDY_SHARED_DATA` env var and `--data-dir` argument. **Tip: `--data-dir` can point to workspace root — it auto-detects `shared_data/` subdirectory.**

**Expected outputs:** `shared_data/rankings.json`, `shared_data/ranked_papers.json`.

### Stage 3 — Activate `paper_summarizer` (two parts with host-LLM step in between)

This sub-skill has a **prepare → host-LLM → finalize** flow. Activate it once; the sub-skill's own `SKILL.md` walks you through:

```
Skill(skill="paper_summarizer",
      args="top-n: <N>; language: <en|zh>; workspace: <path/to/workspace>")
```

**Path:** Both `prepare` and `finalize` scripts support `--shared-data`. Falls back to `WORKBUDDY_SHARED_DATA` env.

The sub-skill will:
1. Run its `prepare` script → writes `shared_data/summarize_request.json`.
2. Hand control back to you (the host LLM) to read that file and write `shared_data/summarized_papers.json` in-context. The required output schema and prompt are inside `summarize_request.json` — follow them exactly.
3. Run its `finalize` script → normalizes your output into the canonical envelope.

**Your in-context responsibility (between prepare and finalize):**
For each paper in `request.papers`, generate:
- `one_line_summary` — single sentence, ≤ 30 words
- `key_contributions` — 2–3 bullet items
- `methods` — list of methods/techniques used
- `keywords` — 3–5 short keywords

Write either a bare list or the canonical envelope `{count, summarized_count, model, mode, language, papers}` to `shared_data/summarized_papers.json`. `finalize` tolerates both shapes.

### Stage 4 — Activate `briefing_report`

```
Skill(skill="briefing_report",
      args="language: <en|zh>; workspace: <path/to/workspace>")
```

**Path:** Reads from `<workspace>/shared_data/`. Supports `WORKBUDDY_SHARED_DATA` env and `--data-dir` argument.

**Expected output:** `shared_data/briefing.md`.

### Stage 5 — Activate `papers-analysis-visualizer`

**Before invoking, ask the user about Notion.** You MUST do this — do not skip.

1. Read `.env` in the project root. If `NOTION_API_TOKEN` is set → invoke the skill directly with workspace path:
   ```
   Skill(skill="papers-analysis-visualizer",
         args="workspace: <path/to/workspace>")
   ```

2. If `NOTION_API_TOKEN` is NOT set, **stop and ask the user** in their language:
   > "Would you like to sync papers to your Notion database? This requires a free Notion integration (3-minute setup). If you skip, only the HTML dashboard will be generated. [Y/n]"

   - **If YES**: show the 3-step setup guide below (stop and wait — do not proceed):

     **Step 1 — Create Integration:** Go to https://www.notion.so/my-integrations → New Integration → name it `Papers Analysis` → copy the `Internal Integration Secret` (starts with `ntn_` or `secret_`).

     **Step 2 — Grant access:** In Notion, open the page where you want the paper database → top-right `⋯` → Connections → add `Papers Analysis`. Copy the page ID from the URL (the 32-char part before `?`).

     **Step 3 — Configure:** Add to `.env`:
     ```
     NOTION_API_TOKEN=your_secret
     NOTION_PARENT_PAGE_ID=your_page_id
     ```
     Reply "done" after completing the setup, then invoke with workspace:
     ```
     Skill(skill="papers-analysis-visualizer",
           args="workspace: <path/to/workspace>")
     ```

   - **If NO**: invoke directly with workspace path:
     ```
     Skill(skill="papers-analysis-visualizer",
           args="workspace: <path/to/workspace>")
     ```

**Path:** Both `sync_to_notion` and `build_dashboard_html` scripts support `--data-dir` for resolving relative paths (`--input`, `--output`).

**Expected outputs:** `<workspace>/output/dashboard.html` (+ `<workspace>/data/notion_mapping.json` if user opted into Notion sync).

---

## Final output to user

After all 5 stages, present the user with:

1. A short prose summary (3–5 sentences): how many papers fetched, top theme, headline paper.
2. The top 3 paper titles with `one_line_summary` from your Stage 3 output.
3. File paths for deeper inspection:
   - `shared_data/briefing.md` — full Markdown briefing
   - `output/dashboard.html` — interactive HTML dashboard
   - `shared_data/manifest.json` — run metadata

Do **not** dump the full briefing into the chat — point to the file.

---

## Single-skill invocations (skip the router)

If the user asks for ONE specific stage, do NOT run this router. Activate the sub-skill directly:

| User intent | Sub-skill to activate |
|-------------|----------------------|
| "Just fetch papers on `<X>`" | `Skill(skill="data_collector", args="...")` |
| "Rank what I already have" | `Skill(skill="paper_ranker", args="...")` |
| "Summarize the top papers" | `Skill(skill="paper_summarizer", args="...")` |
| "Rebuild the dashboard" | `Skill(skill="papers-analysis-visualizer", args="...")` |
| "Regenerate the briefing" | `Skill(skill="briefing_report", args="...")` |

---

## Failure handling

- **Stage 1 returns 0 papers:** report "no new papers in date range" and stop. Do not run downstream stages.
- **Any stage's `manifest.json.errors` is non-empty:** report errors verbatim, ask user whether to retry that stage.
- **Stage 3 (your in-context summarization) — paper without abstract:** skip that paper, note it in `summarized_count`.
- **Stage 5 — `dashboard.html` not produced:** report the file path that should exist and surface the underlying error from the sub-skill.
Always surface failures to the user — never silently swallow.

---

## Constraints (do NOT violate)

- **Router-only.** This file does NOT run shell commands, Python, or `arxiv_agent.py`. All execution happens inside the activated sub-skills.
- **No external LLM API calls.** Stage 3's middle step is performed by you in-context. Do not call Anthropic / OpenAI APIs.
- **No skill-to-skill Python imports.** All inter-skill data flows through `shared_data/` JSON files — each sub-skill reads/writes its own contract.
- **Sequential, not parallel.** Each stage depends on the previous stage's `shared_data/` outputs. Never activate two stages in parallel.
- **No emoji in briefing output** unless the user explicitly asks for them.
- **Idempotent.** Re-running any stage overwrites its own outputs; never append.
