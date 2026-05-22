"""Tests for strategy configuration."""

from contextseek.config.strategies import (
    EvolutionStrategy,
    RetrievalStrategy,
    StrategyConfig,
    CanaryRule,
    StrategyRouter,
    default_strategy_config,
)


class TestStrategyConfig:
    def test_defaults(self):
        config = default_strategy_config()
        assert config.version == "v1"
        assert config.retrieval.default_k == 20
        assert config.evolution.semantic_merge_threshold == 0.72

    def test_evolution_strategy(self):
        evo = EvolutionStrategy(decay_half_life_days=14.0)
        assert evo.decay_half_life_days == 14.0
        assert evo.dedupe_by_hash is True

    def test_canary_routing(self):
        v1 = StrategyConfig(version="v1")
        v2 = StrategyConfig(version="v2", retrieval=RetrievalStrategy(default_k=50))
        router = StrategyRouter(
            strategies={"v1": v1, "v2": v2},
            rules=(CanaryRule(version="v2", tenant_ids=("acme",)),),
        )
        resolved = router.resolve(tenant_id="acme")
        assert resolved.retrieval.default_k == 50

        resolved_default = router.resolve(tenant_id="other")
        assert resolved_default.retrieval.default_k == 20
