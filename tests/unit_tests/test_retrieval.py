"""Tests for retrieval orchestrator and components."""

from contextseek.retrieval.components import (
    DefaultRecallRoute,
    HeuristicReranker,
    tokens,
)
from contextseek.config.strategies import RetrievalStrategy


class TestTokens:
    def test_basic(self):
        result = tokens("Hello World")
        assert result == ["hello", "world"]

    def test_chinese(self):
        result = tokens("你好世界")
        assert "你好世界" in result


class TestDefaultRecallRoute:
    def test_build_queries(self):
        route = DefaultRecallRoute()
        strategy = RetrievalStrategy()
        queries = route.build_queries("test query", strategy)
        assert len(queries) >= 1
        assert any(q.route_name == "phrase" for q in queries)

    def test_empty_query(self):
        route = DefaultRecallRoute()
        strategy = RetrievalStrategy()
        assert route.build_queries("", strategy) == []


class TestHeuristicReranker:
    def test_rerank_by_score(self):
        reranker = HeuristicReranker()
        candidates = [
            {"content": "low", "score": 0.1},
            {"content": "high", "score": 0.9},
            {"content": "mid", "score": 0.5},
        ]
        result = reranker.rerank(candidates, query="test", strategy=RetrievalStrategy())
        scores = [float(r["_score"]) for r in result]
        assert scores == sorted(scores, reverse=True)
