"""Shared utilities for the data_collector skill."""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

# 路径解析函数 — 支持运行时动态修改
def resolve_shared_data(override=None):
    """Resolve shared_data path.

    Priority: CLI arg > WORKBUDDY_SHARED_DATA env > ~/.workbuddy/shared_data (fallback).
    """
    if override:
        return Path(override)
    env = os.environ.get("WORKBUDDY_SHARED_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[3] / "shared_data"


def set_shared_data(path):
    """Set the module-global SHARED_DATA and LAST_FETCH_FILE at runtime.

    Can be called multiple times to switch output directory mid-process.
    """
    global SHARED_DATA, LAST_FETCH_FILE
    SHARED_DATA = Path(path)
    LAST_FETCH_FILE = SHARED_DATA / "last_fetch.json"


# 模块级全局变量 — 首次导入时解析（之后可通过 set_shared_data 动态修改）
_WORKBUDDY_SHARED = os.environ.get("WORKBUDDY_SHARED_DATA")
if _WORKBUDDY_SHARED:
    _INITIAL = Path(_WORKBUDDY_SHARED)
else:
    _INITIAL = Path(__file__).resolve().parents[3] / "shared_data"

set_shared_data(_INITIAL)

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts"


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


