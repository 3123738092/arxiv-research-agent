---
name: arxiv-research-agent
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

  This skill orchestrates 5 sub-skills (data-collector, paper-ranker, paper-summarizer,
  papers-analysis-visualizer, briefing-report) — see AGENTS.md for the skill inventory and
  shared-data contract. Skill 3 (summarization) is performed BY YOU, the host LLM, in-context;
  no external LLM API is called.
version: 1.1.0
author: Han
tags: [arxiv, agent, research, briefing, daily-digest, social-network-analysis, pagerank, llm]
agent: arxiv-research-agent
---

# arXiv Research Briefing Agent — Entry Point

You are the host LLM driving the **arXiv Research Briefing Agent**. This file is the **agent-level entry point**: when a user asks for a daily research briefing, follow the recipe below to drive the 5 sub-skills end-to-end.

> **Reference:** `AGENTS.md` (same directory) lists the 5 sub-skills, their `shared_data/` outputs, and the data-flow contract. Read it once if you need to understand the full system; do not duplicate that information here.

---

## When to invoke this skill

Activate this entry point when the user's request matches any of:

- "Daily / today's arxiv briefing" (any language)
- "Top papers on `<topic>` today / this week"
- "Build a research digest for `<topic>`"
- "Summarize today's NLP / agent / LLM papers"

If the user asks for a **single sub-task** (e.g. "just rank these papers", "build the dashboard from existing data"), do NOT activate this skill — invoke the relevant sub-skill directly (`paper-ranker`, `papers-analysis-visualizer`, etc.).

---

## Parameters to extract from the user

Before running the recipe, parse the user's request into:

| Parameter | Default | How to extract |
|-----------|---------|----------------|
| `categories` | `cs.CL cs.LG cs.CV cs.AI cs.MA` | If user names a field (e.g. "NLP" → `cs.CL`, "vision" → `cs.CV`); else default |
| `keywords` | `agent skill "tool use" LLM "language model"` | If user names a topic (e.g. "diffusion models" → `["diffusion", "generative"]`); else default |
| `interest` | space-joined `keywords` | The natural-language phrasing of the user's interest |
| `top-n` | `10` | If user says "top 5" / "top 20", override |
| `language` | `en` | If user writes Chinese, use `zh` |

If the user gives a generic request ("today's briefing"), use defaults across the board.

---

## Pipeline recipe (7 steps)

Run each step from the **repo root** (the directory containing this `SKILL.md`). All commands use `python arxiv_agent.py <subcommand>`. The orchestrator + sub-skill commands are documented in `AGENTS.md` § "Orchestrator Commands".

### Step 1 — Data Collector (Skill 1)

```bash
python arxiv_agent.py fetch \
  --categories cs.CL cs.LG cs.CV cs.AI cs.MA \
  --keywords agent skill "tool use" LLM "language model"
```

Substitute `<categories>` / `<keywords>` with the parsed parameters. This writes
`shared_data/papers.json`, `authors.json`, `edges/*.json`, `embeddings/*`, and `manifest.json`.

**Stop conditions:**
- If `manifest.json.errors` is non-empty → abort, report errors to user.
- If `manifest.json.counts.after_dedup == 0` → tell user "no new papers today" and stop.

### Step 2 — Paper Ranker (Skill 2)

```bash
python arxiv_agent.py rank --interest "<interest text from user>"
```

Writes `shared_data/rankings.json` and `shared_data/ranked_papers.json`. The interest text is a natural-language phrasing of what the user cares about (e.g. `"agent skill tool use LLM language model"`).

### Step 3 — Paper Summarizer: prepare (Skill 3, part 1)

```bash
python arxiv_agent.py summarize --top-n 10 --language en
```

Substitute `--top-n` / `--language` with the parsed parameters. This writes `shared_data/summarize_request.json` containing the system prompt, user prompt, output schema, and the top-N papers selected by `relevance_score + novelty_score`.

### Step 4 — Host LLM summarization (in-context, YOU do this)

**This step has no shell command — you, the host LLM, perform it directly.**

1. Read `shared_data/summarize_request.json`.
2. For each paper in `request.papers`, generate the four required fields:
   - `one_line_summary` — single sentence, ≤ 30 words
   - `key_contributions` — 2–3 bullet items
   - `methods` — list of methods/techniques used
   - `keywords` — 3–5 short keywords
3. Follow the `system_prompt`, `user_prompt`, and `output_schema` from the request file exactly.
4. Write the result to `shared_data/summarized_papers.json` as either:
   - A bare list of paper objects (each with the four fields + `arxiv_id`), or
   - The canonical envelope `{count, summarized_count, model, mode, language, papers: [...]}`

`finalize.py` (next step) tolerates both shapes.

### Step 5 — Paper Summarizer: finalize (Skill 3, part 2)

```bash
python arxiv_agent.py finalize-summary
```

Validates your output, normalizes the four summary fields, merges upstream metadata back in, and re-emits `shared_data/summarized_papers.json` as the canonical envelope. Reports any papers you missed.

### Step 6 — Visualizer (Skill 5)

```bash
python arxiv_agent.py viz --skip-notion
```

Adapts `ranked_papers.json` + `summarized_papers.json` into `shared_data/visualizer_input.json`, then renders `output/dashboard.html`. Drop `--skip-notion` only if `NOTION_API_TOKEN` is set in the environment.

### Step 7 — Briefing Report (Skill 4)

```bash
python arxiv_agent.py report
```

Writes `shared_data/briefing.md` — the daily Markdown briefing with top-N papers, summaries, and links.

---

## Final output to user

After all 7 steps, present the user with:

1. A short prose summary (3–5 sentences): how many papers fetched, top theme, headline paper.
2. The top 3 paper titles with `one_line_summary` from your Step 4 output.
3. File paths for deeper inspection:
   - `shared_data/briefing.md` — full Markdown briefing
   - `output/dashboard.html` — interactive HTML dashboard
   - `shared_data/manifest.json` — run metadata

Do **not** dump the full briefing into the chat — point to the file.

---

## Fast path (when summaries aren't needed)

If the user explicitly says "skip summaries" or "just show me the ranking", you can short-circuit:

```bash
python arxiv_agent.py daily   # runs 1 → 2 → 3-prepare → 5 → 4 without the host-LLM mid-step
```

This produces a briefing without rich summaries (the four summary fields will be empty placeholders). Only use this when the user explicitly asks for speed over depth.

---

## Single-skill invocations

If the user asks for one specific stage, jump straight to it — do NOT run the full pipeline:

| User intent | Command |
|-------------|---------|
| "Just fetch papers on `<X>`" | `python arxiv_agent.py fetch --categories ... --keywords ...` |
| "Rank what I already have" | `python arxiv_agent.py rank --interest "..."` |
| "Rebuild the dashboard" | `python arxiv_agent.py viz --skip-notion` |
| "Regenerate the briefing" | `python arxiv_agent.py report` |
| "What's the current state?" | `python arxiv_agent.py status` |

---

## Failure handling

- **Skill 1 returns 0 papers:** report "no new papers in date range" and stop. Do not run downstream skills.
- **Skill 1 has errors in `manifest.json.errors`:** report errors verbatim, ask user whether to retry.
- **Step 4 (your summarization) — paper without abstract:** skip that paper, note it in `summarized_count`.
- **Step 5 (viz) — `dashboard.html` not produced:** report file path that should exist; show the underlying error from the subprocess.
- **`last_fetch.json` blocks re-runs (cross-date dedup ate everything):** rename `shared_data/last_fetch.json` to `last_fetch.json.bak` and rerun Step 1.

Always surface failures to the user — never silently swallow.

---

## Constraints (do NOT violate)

- **No external LLM API calls.** Step 4 is performed by you in-context. Do not call Anthropic / OpenAI APIs from inside the agent.
- **No skill-to-skill Python imports.** All inter-skill data flows through `shared_data/` JSON files.
- **No emoji in briefing output** unless the user asks for them.
- **Idempotent.** Re-running any step overwrites its own outputs; do not append.
