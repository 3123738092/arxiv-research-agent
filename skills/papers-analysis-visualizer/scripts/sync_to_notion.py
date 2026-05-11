"""
此工具支持：
- 将上游整理出的论文数据归档到 Notion 数据库
- 在给定页面自动创建新数据库 或 连接现有数据库
- paper_id 去重更新
"""
import os
import sys
import json
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

# 添加 scripts 目录到路径，方便导入同级模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compute_analytics import enrich_papers

# ── 路径自修复：向上查找 .env 文件 ────────────────────────────
# 搜索链：scripts/ → visualizer/ → skills/ → ~/.workbuddy/ → cwd/
_script_dir = Path(__file__).resolve().parents  # tuple of parent dirs
_search_paths = [
    Path.cwd() / ".env",                        # 从调用时的工作目录
    _script_dir[0] / ".env",                    # visualizer/ 目录
    _script_dir[1] / ".env",                    # skills/ 目录
    Path.home() / ".workbuddy" / ".env",        # ~/.workbuddy/
]
for _p in _search_paths:
    if _p.exists():
        load_dotenv(_p)
        print(f"[Env] 已加载: {_p}")
        break
else:
    print("[Env] 未找到 .env 文件，将依赖环境变量或命令行参数")
# ──────────────────────────────────────────────────────────────

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")      # optional：已有数据库则直接用
PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID")       # optional：自动创建数据库时使用

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

BASE_URL = "https://api.notion.com/v1"


# 数据库管理
def create_paper_database(title="论文库"):
    """在父页面下创建论文数据库，返回 database_id。"""
    url = f"{BASE_URL}/databases"
    payload = {
        "parent": {"type": "page_id", "page_id": PARENT_PAGE_ID},
        "title": [{"text": {"content": title}}],
        "properties": {
            "Title": {"title": {}},
            "URL": {"url": {}},
            "Paper ID": {"rich_text": {}},
            "Relevance": {"number": {"format": "number"}},
            "Novelty": {"number": {"format": "number"}},
            "Recommendation": {"number": {"format": "number"}},
            "Summary": {"rich_text": {}},
            "Keywords": {"multi_select": {}},
            "Category": {"select": {}},
            "Community": {"select": {}},
            "Published Date": {"date": {}},
            "Status": {
                "select": {
                    "options": [
                        {"name": "Unread", "color": "gray"},
                        {"name": "Reading", "color": "blue"},
                        {"name": "Done", "color": "green"},
                    ]
                }
            },
        },
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        raise RuntimeError(f"创建数据库失败: {resp.status_code} {resp.text}")
    data = resp.json()
    db_id = data["id"]
    print(f"[DB] 已创建数据库: {data['url']}")
    return db_id


def get_or_create_database(title="论文库"):
    """获取数据库 ID：已有则直接用，否则自动创建。"""

    if NOTION_DATABASE_ID:
        print(f"[DB] 使用已有数据库: {NOTION_DATABASE_ID}")
        return NOTION_DATABASE_ID
    if PARENT_PAGE_ID:
        print(f"[DB] 未检测到 NOTION_DATABASE_ID，将在父页面下自动创建数据库「{title}」...")
        db_id = create_paper_database(title=title)
        print(f"[DB] 创建成功！请将以下内容加入 .env 以便复用：")
        print(f"     NOTION_DATABASE_ID={db_id}")
        return db_id
    raise RuntimeError(
        "请配置 .env：已有数据库设置 NOTION_DATABASE_ID，"
        "需要自动创建则设置 NOTION_PARENT_PAGE_ID"
    )


# 查询 & 去重

def find_existing_page(database_id, paper_id):
    """
    按 Paper ID 查询数据库中是否已有该论文;
    return page_id or None。
    """
    url = f"{BASE_URL}/databases/{database_id}/query"
    payload = {
        "filter": {
            "property": "Paper ID",
            "rich_text": {"equals": paper_id},
        }
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if not resp.ok:
        print(f"  [WARN] 查询 paper_id={paper_id} 失败: {resp.status_code}")
        return None
    results = resp.json().get("results", [])
    return results[0]["id"] if results else None


# 属性构建

def build_properties(paper):
    """
    将论文数据转换为 Notion page properties。纯格式映射，不做业务计算。
    """
    return {
        "Title": {
            "title": [{"text": {"content": paper["title"]}}]
        },
        "URL": {"url": paper.get("url", "")},
        "Paper ID": {
            "rich_text": [{"text": {"content": paper["paper_id"]}}]
        },
        "Relevance": {"number": paper["relevance_score"]},
        "Novelty": {"number": paper["novelty_score"]},
        "Recommendation": {"number": paper["recommendation_score"]},
        "Summary": {
            "rich_text": [{"text": {"content": paper.get("one_line_summary", "")}}]
        },
        "Keywords": {
            "multi_select": [{"name": kw} for kw in paper.get("keywords", [])]
        },
        "Category": {
            "select": {"name": paper["category"]} if paper.get("category") else None
        },
        "Community": {
            "select": {"name": paper["community_label"]} if paper.get("community_label") else None
        },
        "Published Date": {
            "date": {"start": paper["published_date"]} if paper.get("published_date") else None
        },
        "Status": {"select": {"name": "Unread"}},
    }


# 同步

def sync_paper(database_id, paper):
    """
    同步单篇论文：已存在则更新，不存在则创建。
    return (action, notion_url)。
    """
    paper_id = paper["paper_id"]
    existing_page_id = find_existing_page(database_id, paper_id)
    properties = build_properties(paper)

    if existing_page_id:
        # 更新已有页面
        url = f"{BASE_URL}/pages/{existing_page_id}"
        payload = {"properties": properties}
        resp = requests.patch(url, headers=HEADERS, json=payload)
        if resp.ok:
            page_url = resp.json().get("url", "")
            return "updated", page_url
        else:
            print(f"  [ERROR] 更新失败 {paper_id}: {resp.status_code} {resp.text}")
            return None, None
    else:
        # 创建新页面
        url = f"{BASE_URL}/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
        }
        resp = requests.post(url, headers=HEADERS, json=payload)
        if resp.ok:
            page_url = resp.json().get("url", "")
            return "created", page_url
        else:
            print(f"  [ERROR] 创建失败 {paper_id}: {resp.status_code} {resp.text}")
            return None, None


def sync_papers(database_id, papers):
    """同步所有论文，返回 paper_id → notion_url 映射。"""
    mapping = {}
    stats = {"created": 0, "updated": 0, "failed": 0}

    for i, paper in enumerate(papers):
        title = paper.get("title", "?")[:60]
        print(f"  [{i+1}/{len(papers)}] {title}...")

        action, notion_url = sync_paper(database_id, paper)
        if action:
            stats[action] += 1
            mapping[paper["paper_id"]] = notion_url
        else:
            stats["failed"] += 1

    print(f"\n[Sync] 完成: 新建 {stats['created']}, 更新 {stats['updated']}, 失败 {stats['failed']}")
    return mapping


# ── CLI 入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="同步论文数据到 Notion 数据库")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--output", default="data/notion_mapping.json",
                        help="输出 paper_id→notion_url 映射文件路径")
    parser.add_argument("--db-title", default=None,
                        help="Notion 数据库标题（不传则默认为「论文库」）")
    args = parser.parse_args()

    # 加载论文数据
    with open(args.input, "r", encoding="utf-8") as f:
        raw_papers = json.load(f)
    papers = enrich_papers(raw_papers)  # 计算 recommendation 等衍生字段
    print(f"[Load] 加载 {len(papers)} 篇论文（已加工）")

    # 确定数据库标题
    db_title = args.db_title or "论文库"

    # 获取或创建数据库
    database_id = get_or_create_database(title=db_title)

    # 同步
    mapping = sync_papers(database_id, papers)

    # 输出映射文件（供 dashboard 使用）
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
    print(f"[File] 映射文件已保存: {args.output}")


if __name__ == "__main__":
    main()
