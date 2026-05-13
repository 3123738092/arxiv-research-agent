"""Shared utilities for the data_collector skill."""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta


def _find_project_root():
    """向上遍历找到项目根（有 .claude/ 或 CLAUDE.md 的目录）。"""
    cur = Path(__file__).resolve().parent
    for _ in range(10):
        if (cur / ".claude").is_dir() or (cur / "CLAUDE.md").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    # 兜底：假设 skills/ 在项目根下两层
    return Path(__file__).resolve().parents[4]


PROJECT_ROOT = _find_project_root()


def resolve_shared_data(override=None):
    """Resolve shared_data path.

    Priority: CLI arg > WORKBUDDY_SHARED_DATA env > <project_root>/shared_data.
    Auto-creates the directory if it does not exist.
    """
    if override:
        path = Path(override)
    elif os.environ.get("WORKBUDDY_SHARED_DATA"):
        path = Path(os.environ["WORKBUDDY_SHARED_DATA"])
    else:
        path = PROJECT_ROOT / "shared_data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def set_shared_data(path):
    """Set the module-global SHARED_DATA and LAST_FETCH_FILE at runtime."""
    global SHARED_DATA, LAST_FETCH_FILE
    SHARED_DATA = Path(path)
    SHARED_DATA.mkdir(parents=True, exist_ok=True)
    LAST_FETCH_FILE = SHARED_DATA / "last_fetch.json"


# 模块初始化
_INITIAL = resolve_shared_data()
set_shared_data(_INITIAL)


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
    return d.weekday() >= 5


def weekend_window(d=None):
    """If today is weekend, return the last Friday as the effective 'today'."""
    d = d or datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def short_hash(s):
    return hashlib.md5(s.encode()).hexdigest()[:8]
