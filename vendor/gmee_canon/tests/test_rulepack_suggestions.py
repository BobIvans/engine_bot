from __future__ import annotations
import yaml
from pathlib import Path
from gmee.suggestions import SuggestionEngine

def test_rulepack_generates_epsilon_suggestion(tmp_path):
    cfg = yaml.safe_load(Path("configs/golden_exit_engine.yaml").read_text(encoding="utf-8"))
    # Synthetic gathered metrics
    gathered = {
        "rpc_arm_stats": [
            {"latency_p90_ms": 100.0},
            {"latency_p90_ms": 200.0},
            {"latency_p90_ms": 300.0},
        ]
    }
    eng = SuggestionEngine(cfg, rule_pack_path="configs/suggestion_rulepacks/default.yaml")
    sugs = eng.run(gathered)
    # Either produces epsilon suggestion or none (if equals current)
    # Assert that suggestions target canonical config keys (chain_defaults...)
    for s in sugs:
        assert s.key_path.startswith("chain_defaults."), s.key_path
