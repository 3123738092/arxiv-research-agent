"""Run the summarizer via an Anthropic-compatible gateway.

Reads credentials from env or prompts interactively (hidden input):
- ANTHROPIC_AUTH_TOKEN  (preferred for gateways; sent as Bearer)
  or ANTHROPIC_API_KEY  (standard Anthropic)
- ANTHROPIC_BASE_URL    (the gateway root, e.g. https://your-gateway/anthropic)

The token is NEVER written to disk, logs, or printed.

    python examples/run_on_sample_gateway.py
"""

from __future__ import annotations

import getpass
import json
import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, ROOT)

# Show INFO logs so token usage from summarizer.client is printed each batch.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from summarizer import summarize, SummarizerConfig  # noqa: E402


def _prompt_hidden(label: str) -> str:
    try:
        return getpass.getpass(f"{label} (input hidden): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def main() -> int:
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    if not base_url:
        base_url = input("Enter ANTHROPIC_BASE_URL: ").strip()
    if not base_url:
        print("No ANTHROPIC_BASE_URL provided. Aborting.", file=sys.stderr)
        return 2

    # Prefer explicit key in env; otherwise rely on AUTH_TOKEN picked up by SDK;
    # otherwise ask the user (hidden).
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    has_auth_token = bool(os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip())
    if not api_key and not has_auth_token:
        entered = _prompt_hidden("Enter ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY")
        if not entered:
            print("No credential provided. Aborting.", file=sys.stderr)
            return 2
        # Treat as AUTH_TOKEN by default (gateways expect Bearer).
        os.environ["ANTHROPIC_AUTH_TOKEN"] = entered

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    fixture_path = os.path.join(ROOT, "data", "fixtures", "ranked_papers_sample.json")
    with open(fixture_path) as f:
        data = json.load(f)

    cfg = SummarizerConfig(
        base_url=base_url,
        model=model,
        api_key=api_key,  # may be "" — SDK will fall back to AUTH_TOKEN env
        top_n=3,
        batch_size=3,
        enable_local_cache=False,
    )
    cfg.shared_data_dir = os.path.join(ROOT, "data")
    cfg.output_filename = "summarized_papers_sample_gateway.json"

    print(f"model: {model} | base_url: {base_url}")
    print(f"Summarizing {len(data['papers'])} fixture papers...")

    result = summarize(data["papers"], cfg=cfg)
    for p in result:
        print(f"\n{p['title']}")
        print(f"  one_line_summary : {p.get('one_line_summary', '')}")
        print(f"  key_contributions: {p.get('key_contributions', [])}")
        print(f"  methods          : {p.get('methods', [])}")
        print(f"  keywords         : {p.get('keywords', [])}")

    out = os.path.join(cfg.shared_data_dir, cfg.output_filename)
    print(f"\nWrote: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
