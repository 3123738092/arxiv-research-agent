"""快速测试 Notion API：自动创建数据库 + 写入测试条目。"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()  # 读取 .env 文件，注入环境变量

NOTION_TOKEN = os.getenv("NOTION_API_TOKEN")
PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID")

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",  # Notion API v2 统一用 Bearer token 鉴权
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",             # API 版本号，不写会报错
}

BASE_URL = "https://api.notion.com/v1"


def create_paper_database():
    """在父页面下创建论文数据库，包含完整的 property schema。返回 database_id。"""
    url = f"{BASE_URL}/databases"

    payload = {
        "parent": {
            "type": "page_id",
            "page_id": PARENT_PAGE_ID,  # 数据库创建在这个页面下
        },
        "title": [{"text": {"content": "论文库"}}],
        "properties": {
            # title 类型 — 论文标题（每个 database 必须有一个 title 列）
            "Title": {"title": {}},
            # url 类型 — 直接存链接字符串
            "URL": {"url": {}},
            # rich_text 类型 — 支持富文本分段
            "Paper ID": {"rich_text": {}},
            # number 类型 — 小数
            "Relevance": {"number": {"format": "number"}},
            "Novelty": {"number": {"format": "number"}},
            "Recommendation": {"number": {"format": "number"}},
            # rich_text 类型
            "Summary": {"rich_text": {}},
            # multi_select 类型 — 每个选项是 {"name": "..."}，新选项自动创建
            "Keywords": {"multi_select": {}},
            # select 类型 — 单选，新值自动创建
            "Category": {"select": {}},
            "Community": {"select": {}},
            # date 类型 — 只用到 start，不需要 end
            "Published Date": {"date": {}},
            # select 类型 — 预设三个选项，管理阅读状态
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
    print(f"POST database → {resp.status_code}")

    if resp.ok:
        data = resp.json()
        db_id = data["id"]
        print(f"  数据库名: {data['title'][0]['plain_text']}")
        print(f"  数据库 ID: {db_id}")
        print(f"  数据库 URL: {data['url']}")
        return db_id
    else:
        print(f"  错误: {resp.text}")
        return None


def create_page(database_id, title_text="测试论文标题"):
    """在指定数据库中创建一条论文条目。"""
    url = f"{BASE_URL}/pages"

    payload = {
        "parent": {"database_id": database_id},  # 指定写入哪个数据库
        "properties": {
            "Title": {
                # title 类型值的结构：数组，每个元素是一段 rich text
                "title": [{"text": {"content": title_text}}]
            },
        },
    }

    resp = requests.post(url, headers=HEADERS, json=payload)
    print(f"POST page → {resp.status_code}")
    if resp.ok:
        data = resp.json()
        print(f"  页面 ID: {data['id']}")
        print(f"  页面 URL: {data.get('url', 'N/A')}")
    else:
        print(f"  错误: {resp.text}")
    return resp.ok


if __name__ == "__main__":
    print(f"Token: {'已设置' if NOTION_TOKEN else '❌ 未设置'}")
    print(f"Parent Page ID: {'已设置' if PARENT_PAGE_ID else '❌ 未设置'}")
    print()

    if not NOTION_TOKEN or not PARENT_PAGE_ID:
        print("请先配置 .env 文件，然后重试。")
        exit(1)

    print("=== 测试 1: 自动创建数据库 ===")
    db_id = create_paper_database()
    if not db_id:
        print("\n创建失败，请检查:")
        print("  1. NOTION_API_TOKEN 是否正确")
        print("  2. 是否已把 integration 关联到父页面（Connections）")
        exit(1)

    print(f"\n创建成功！把以下内容复制到 .env：")
    print(f"NOTION_DATABASE_ID={db_id}")
    print()

    print("=== 测试 2: 写入测试条目 ===")
    create_page(db_id, "【测试】Agentic Skill Discovery for LLMs")
    print("\n去 Notion 检查数据库里是否出现了这条记录。")
