import yaml
from gmee.suggestions import SuggestionEngine

def test_suggestion_engine_smoke():
    cfg = yaml.safe_load(open("configs/golden_exit_engine.yaml", "r", encoding="utf-8"))
    eng = SuggestionEngine(cfg)
    out = eng.run({"rpc_arm_stats": [{"latency_p90_ms": 500}], "token_pool_regime": [{"avg_max_drawdown": -0.2}]})
    assert isinstance(out, list)
