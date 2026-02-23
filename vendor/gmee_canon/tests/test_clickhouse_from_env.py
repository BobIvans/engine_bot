from __future__ import annotations

from gmee.clickhouse import ClickHouseQueryRunner


def test_from_env_parses_clickhouse_url_credentials(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_HOST", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PORT", raising=False)
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    monkeypatch.setenv("CLICKHOUSE_URL", "http://ci_user:ci_pass@ch.example:18123")

    r = ClickHouseQueryRunner.from_env()

    assert r.host == "ch.example"
    assert r.port == 18123
    assert r.user == "ci_user"
    assert r.password == "ci_pass"


def test_from_env_prefers_explicit_user_password_over_url(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_USER", "explicit_user")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "explicit_pass")
    monkeypatch.setenv("CLICKHOUSE_URL", "http://url_user:url_pass@ch.example:8123")

    r = ClickHouseQueryRunner.from_env()

    assert r.user == "explicit_user"
    assert r.password == "explicit_pass"
