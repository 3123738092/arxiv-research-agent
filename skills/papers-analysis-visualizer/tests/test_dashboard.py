"""测试 build_dashboard_html：用样例数据生成 dashboard。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    result = subprocess.run([
        sys.executable,
        str(ROOT / "scripts" / "build_dashboard_html.py"),
        "--input", str(ROOT / "tests" / "fixtures" / "summarized_papers_sample.json"),
        "--output", str(ROOT / "output" / "dashboard.html"),
    ])
    sys.exit(result.returncode)
