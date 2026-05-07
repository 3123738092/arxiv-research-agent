"""Shared utilities for the data_collector skill."""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

_WORKSPACE_SHARED = os.environ.get("WORKBUDDY_SHARED_DATA")
if _WORKSPACE_SHARED:
    SHARED_DATA = Path(_WORKSPACE_SHARED)          # 优先用环境变量
else:
    SHARED_DATA = Path(__file__).resolve().parents[3] / "shared_data"  # 兜底
    
CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"
LAST_FETCH_FILE = SHARED_DATA / "last_fetch.json"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_arxiv_id(raw):
    """Strip version suffix, return bare arxiv ID e.g. 2301.00001."""
    return raw.split("v")[0] if raw else raw


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def is_weekend(d=None):
    d = d or datetime.now()
    return d.weekday() >= 5  # Saturday=5, Sunday=6


def weekend_window(d=None):
    """If today is weekend, return the last Friday as the effective 'today'."""
    d = d or datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def short_hash(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]


def load_last_fetch():
    if LAST_FETCH_FILE.exists():
        return load_json(LAST_FETCH_FILE)
    return {"seen_ids": [], "last_fetch_time": None, "params": {}}


def save_last_fetch(seen_ids, params):
    save_json(LAST_FETCH_FILE, {
        "last_fetch_time": datetime.now().isoformat(),
        "seen_ids": seen_ids,
        "params": params,
    })
