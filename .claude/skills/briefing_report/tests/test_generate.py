import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from skills.briefing_report.generate import run_briefing_report  # noqa: E402


class TestBriefingReport(unittest.TestCase):
    def test_writes_briefing_and_hooks(self):
        papers = [
            {
                "arxiv_id": "2301.00001",
                "title": "LoRA adapters for efficient vision transformers",
                "abstract": "We study low-rank adaptation LoRA for CV models.",
                "categories": ["cs.CV", "cs.LG"],
                "primary_category": "cs.CV",
                "published": "2026-05-04T00:00:00",
                "source": "arxiv",
                "citation_count": 3,
            },
            {
                "arxiv_id": "2301.00002",
                "title": "Diffusion models for image super-resolution",
                "abstract": "Diffusion and denoising for high resolution images.",
                "categories": ["cs.CV"],
                "primary_category": "cs.CV",
                "published": "2026-05-04T00:00:00",
                "source": "arxiv",
                "citation_count": 10,
            },
        ]
        manifest = {
            "timestamp": "2026-05-04T12:00:00",
            "params": {"keywords": ["LoRA"], "date_range": {"start": "2026-05-04", "end": "2026-05-04"}},
            "counts": {"after_dedup": 2},
        }
        rankings = [
            {"arxiv_id": "2301.00002", "pagerank_score": 0.5, "interest_score": 0.1, "rank": 1},
            {"arxiv_id": "2301.00001", "pagerank_score": 0.2, "interest_score": 0.2, "rank": 2},
        ]
        communities = [
            {"community_id": "c0", "label": "Vision team A", "size": 4, "members": ["a1"]},
        ]

        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "edges").mkdir(parents=True, exist_ok=True)
            (d / "embeddings").mkdir(parents=True, exist_ok=True)
            (d / "papers.json").write_text(json.dumps(papers), encoding="utf-8")
            (d / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (d / "edges/citations.json").write_text(json.dumps([]), encoding="utf-8")
            (d / "rankings.json").write_text(json.dumps(rankings), encoding="utf-8")
            (d / "communities.json").write_text(json.dumps(communities), encoding="utf-8")
            # Minimal embeddings: skipped if missing — create tiny vecs for novelty path
            import numpy as np

            idx = {"2301.00001": 0, "2301.00002": 1}
            vecs = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
            np.save(d / "embeddings/paper_vecs.npy", vecs)
            (d / "embeddings/index.json").write_text(json.dumps(idx), encoding="utf-8")

            out = run_briefing_report(
                data_dir=d,
                interest_query="LoRA fine-tuning",
                trend_category_prefix="cs.CV",
            )
            self.assertTrue(out.exists())
            text = out.read_text(encoding="utf-8")
            self.assertIn("## Trend Summary", text)
            self.assertIn("## Personalized Recommendations", text)
            self.assertIn("## Idea Generator", text)
            self.assertIn("Suggested Reading Plan", text)

            hook = d / "briefing.hooks.json"
            self.assertTrue(hook.exists())
            data = json.loads(hook.read_text(encoding="utf-8"))
            self.assertIn("follow_up_prompts", data)


if __name__ == "__main__":
    unittest.main()
