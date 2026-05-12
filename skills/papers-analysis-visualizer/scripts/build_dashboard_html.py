"""生成自包含的 Topic Exploration Dashboard HTML。"""
import os
import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compute_analytics import enrich_papers, compute_keyword_frequencies, compute_cooccurrence, compute_overview

from jinja2 import Environment, FileSystemLoader


def build_graph_data(papers: list[dict]) -> dict:
    """构建关键词网络图数据（nodes + edges），供 ECharts force graph 使用。"""
    freq = compute_keyword_frequencies(papers)
    cooc = compute_cooccurrence(papers)

    # 只取频次 ≥ 2 的关键词作为节点，避免图太密
    nodes = [{"name": kw, "value": f} for kw, f in freq.items() if f >= 1]
    node_names = {n["name"] for n in nodes}
    edges = [e for e in cooc if e["source"] in node_names and e["target"] in node_names]

    return {"nodes": nodes, "edges": edges}


def load_optional_json(path: str) -> dict:
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(description="生成 Topic Exploration Dashboard HTML")
    parser.add_argument("--input", required=True, help="论文 JSON 文件路径")
    parser.add_argument("--output", default=None, help="输出 HTML 路径（默认: <data-dir>/output/dashboard.html）")
    parser.add_argument("--data-dir", default=None, help="workspace 根目录（用于解析相对路径）")
    parser.add_argument("--history", default=None, help="可选：历史趋势数据 JSON")
    parser.add_argument("--notion-mapping", default=None,
                        help="paper_id → notion_url 映射文件（默认: <data-dir>/data/notion_mapping.json）")
    args = parser.parse_args()

    # 解析 data-dir 作为基准路径
    base_dir = Path(args.data_dir) if args.data_dir else Path.cwd()
    base_dir = base_dir.resolve()

    # 解析 input 路径（优先绝对路径）
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = base_dir / input_path

    # 解析 output 路径
    output_default = base_dir / "output" / "dashboard.html"
    output_path = Path(args.output) if args.output else output_default
    if not output_path.is_absolute():
        output_path = base_dir / output_path

    # 解析 notion-mapping 路径
    notion_default = base_dir / "data" / "notion_mapping.json"
    notion_path = Path(args.notion_mapping) if args.notion_mapping else notion_default
    if not notion_path.is_absolute():
        notion_path = base_dir / notion_path

    # 加载 & 加工论文
    with open(input_path, "r", encoding="utf-8") as f:
        raw_papers = json.load(f)
    papers = enrich_papers(raw_papers)
    print(f"[Load] {len(papers)} 篇论文（已计算 recommendation）")

    # 图数据 + 总览
    graph_data = build_graph_data(papers)
    overview = compute_overview(papers)
    # 补充高推荐论文数（relevance + novelty 均 ≥ 7 且 recommendation ≥ 7）
    overview["high_quality_count"] = sum(
        1 for p in papers if p.get("recommendation_score", 0) >= 7
    )

    # 可选数据
    notion_map = load_optional_json(str(notion_path))
    trends = load_optional_json(args.history)

    print(f"[Data] 关键词节点: {len(graph_data['nodes'])} 个, 边: {len(graph_data['edges'])} 条")
    print(f"[Data] Notion 映射: {len(notion_map)} 条, 历史趋势: {'有' if trends else '无'}")

    # 渲染模板
    template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template("dashboard.html")

    html = template.render(
        papers=papers,
        graph_data=graph_data,
        overview=overview,
        notion_map=notion_map,
        trends=trends,
    )

    # 写输出
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[File] Dashboard 已保存: {output_path}")
    print(f"       浏览器直接打开即可 (file:///{str(output_path).replace(os.sep, '/')})")


if __name__ == "__main__":
    main()
