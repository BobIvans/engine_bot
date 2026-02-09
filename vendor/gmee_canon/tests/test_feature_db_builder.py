import json
from pathlib import Path
from gmee.feature_db import build_feature_db

def test_build_feature_db(tmp_path: Path):
    snap = tmp_path / "snap"
    snap.mkdir()
    (snap / "manifest.json").write_text(json.dumps({
        "chain": "sol",
        "env": "test",
        "generated_at": "20250101T000000Z",
        "gatherers": [{"name": "g1", "file": "g1.jsonl"}],
    }), encoding="utf-8")
    (snap / "g1.jsonl").write_text('{"entity_type":"x","entity_id":"a","n":1}\n', encoding="utf-8")

    out = tmp_path / "out"
    man = build_feature_db([snap], out)
    assert (out / "manifest.json").exists()
    assert any(e["entity_type"] == "x" for e in man["entities"])
