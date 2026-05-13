"""对上游论文数据做加工和统计：推荐指数、关键词频次、共现矩阵等。"""
import json
from collections import Counter


def compute_recommendation(paper: dict) -> float:
    """计算单篇论文的推荐指数。"""
    return round(0.6 * paper["relevance_score"] + 0.4 * paper["novelty_score"], 1)


def enrich_papers(papers: list[dict]) -> list[dict]:
    """给每篇论文补充 computed 字段（recommendation 等），返回新的 enriched 列表。"""
    enriched = []
    for paper in papers:
        enriched.append({
            **paper,
            "recommendation_score": compute_recommendation(paper),
        })
    return enriched


def compute_keyword_frequencies(papers: list[dict]) -> dict[str, int]:
    """统计所有关键词的出现频次。"""
    counter = Counter()
    for paper in papers:
        for kw in paper.get("keywords", []):
            counter[kw] += 1
    return dict(counter.most_common())


def compute_cooccurrence(papers: list[dict]) -> list[dict]:
    """计算关键词共现关系，返回 [{source, target, weight}, ...]。"""
    edges = Counter()
    for paper in papers:
        kws = paper.get("keywords", [])
        for i in range(len(kws)):
            for j in range(i + 1, len(kws)):
                # 按字母排序确保 source/target 唯一
                a, b = sorted([kws[i], kws[j]])
                edges[(a, b)] += 1
    return [{"source": a, "target": b, "weight": w} for (a, b), w in edges.items()]


def compute_overview(papers: list[dict]) -> dict:
    """生成总览统计。"""
    all_keywords = [kw for p in papers for kw in p.get("keywords", [])]
    keyword_freq = Counter(all_keywords)
    community_freq = Counter(p.get("community_label", "Unknown") for p in papers)

    high_both = sum(
        1 for p in papers
        if p.get("relevance_score", 0) >= 7 and p.get("novelty_score", 0) >= 7
    )

    return {
        "total_papers": len(papers),
        "hottest_keyword": keyword_freq.most_common(1)[0][0] if keyword_freq else "N/A",
        "most_active_community": community_freq.most_common(1)[0][0] if community_freq else "N/A",
        "high_quality_count": high_both,
        "keyword_count": len(keyword_freq),
        "community_count": len(community_freq),
    }


if __name__ == "__main__":
    # 简单自测
    import sys
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        papers = json.load(f)

    enriched = enrich_papers(papers)
    print("=== Enriched Papers ===")
    for p in enriched:
        print(f"  {p['title'][:50]}... → recommendation={p['recommendation_score']}")

    print("\n=== Keyword Frequencies ===")
    for kw, freq in compute_keyword_frequencies(papers).items():
        print(f"  {kw}: {freq}")

    print("\n=== Co-occurrence ===")
    for edge in compute_cooccurrence(papers):
        print(f"  {edge['source']} ↔ {edge['target']}: {edge['weight']}")

    print("\n=== Overview ===")
    for k, v in compute_overview(papers).items():
        print(f"  {k}: {v}")
