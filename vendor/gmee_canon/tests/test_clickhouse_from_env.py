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


def test_from_env_supports_clickhouse_url_query_credentials(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    monkeypatch.setenv("CLICKHOUSE_URL", "http://ch.example:8123/?user=q_user&password=q_pass")

    r = ClickHouseQueryRunner.from_env()

    assert r.user == "q_user"
    assert r.password == "q_pass"


def test_from_env_supports_username_pass_aliases(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_USERNAME", "alias_user")
    monkeypatch.setenv("CLICKHOUSE_PASS", "alias_pass")

    r = ClickHouseQueryRunner.from_env()

    assert r.user == "alias_user"
    assert r.password == "alias_pass"


def test_from_env_uses_url_credentials_even_when_host_port_set(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_HOST", "host-from-env")
    monkeypatch.setenv("CLICKHOUSE_PORT", "9000")
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    monkeypatch.setenv("CLICKHOUSE_URL", "http://url_user:url_pass@ch.example:8123")

    r = ClickHouseQueryRunner.from_env()

    assert r.host == "host-from-env"
    assert r.port == 9000
    assert r.user == "url_user"
    assert r.password == "url_pass"


def test_from_env_parses_url_in_clickhouse_host(monkeypatch):
    monkeypatch.setenv("CLICKHOUSE_HOST", "http://h_user:h_pass@host-in-var:18123/?user=ignored")
    monkeypatch.delenv("CLICKHOUSE_PORT", raising=False)
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    monkeypatch.delenv("CLICKHOUSE_URL", raising=False)
    monkeypatch.delenv("CLICKHOUSE_HTTP_URL", raising=False)

    r = ClickHouseQueryRunner.from_env()

    assert r.host == "host-in-var"
    assert r.port == 18123
    assert r.user == "h_user"
    assert r.password == "h_pass"
