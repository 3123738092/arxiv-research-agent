"""测试 sync_to_notion：用样例数据同步到 Notion。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    result = subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "sync_to_notion.py"),
        "--input", str(ROOT / "tests" / "fixtures" / "summarized_papers_sample.json"),
        "--output", str(ROOT / "data" / "notion_mapping.json"),
    ])
    sys.exit(result.returncode)
