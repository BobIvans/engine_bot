from __future__ import annotations

import os
import re
import uuid
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent



_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+):([A-Za-z0-9_]+)\}")


def _strip_sql_comments(sql: str) -> str:
    # Remove /* ... */ blocks
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    # Remove -- line comments
    sql = re.sub(r"--.*?$", "", sql, flags=re.M)
    return sql


def extract_placeholders(sql: str) -> dict[str, str]:
    """Return {param_name: ch_type} for placeholders in SQL (comments ignored)."""
    s = _strip_sql_comments(sql)
    return {name: typ for name, typ in _PLACEHOLDER_RE.findall(s)}


def _serialize_param(value: Any, ch_type: str) -> str:
    """Serialize python value to ClickHouse HTTP query parameter string."""
    if value is None:
        return ""
    t = ch_type.upper()
    if t == "STRING":
        return str(value)
    if t == "UUID":
        return str(value)
    if t.startswith("UINT") or t.startswith("INT"):
        return str(int(value))
    if t.startswith("FLOAT") or t == "DECIMAL":
        return str(float(value))
    return str(value)


@dataclass
class QueryDef:
    name: str
    sql_path: str
    params: list[str]


class ClickHouseQueryRunner:
    """Minimal ClickHouse HTTP runner (P0).

    Supports:
    - executing registered SQL-by-name from configs/queries.yaml
    - enforcing 1:1 params ↔ placeholders at runtime
    - session_id context (needed for TEMPORARY TABLE flows)
    - inserting JSONEachRow
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        user: str = "default",
        password: str = "",
        database: str = "default",
        timeout_s: int = 30,
        queries_registry_path: str | Path = "configs/queries.yaml",
    ) -> None:
        self.host = host
        self.port = int(port)
        self.user = user
        self.password = password
        self.database = database
        self.timeout_s = int(timeout_s)
        self._registry_path = Path(queries_registry_path)
        if not self._registry_path.is_absolute():
            # Resolve against package repo root to support running from arbitrary CWD.
            self._registry_path = (REPO_ROOT / self._registry_path).resolve()
        # Resolve relative SQL/DDL paths against repo root (parent of configs/)
        try:
            self.repo_root = self._registry_path.resolve().parent.parent
        except Exception:
            self.repo_root = Path.cwd()
        self._registry = self._load_registry(self._registry_path)

    @classmethod
    def from_env(cls, queries_registry_path: str | Path = "configs/queries.yaml") -> "ClickHouseQueryRunner":
        """Build a runner from environment variables.

        Supported env vars:
        - CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE
        - CH_HOST, CH_PORT, CH_USER, CH_PASSWORD, CH_DATABASE (fallback aliases)
        - CLICKHOUSE_USERNAME, CLICKHOUSE_PASS (fallback aliases)
        - CLICKHOUSE_TIMEOUT_S
        - CLICKHOUSE_HTTP_URL / CLICKHOUSE_URL (optional convenience; e.g. http://localhost:8123)

        Precedence:
        - Host/port prefer CLICKHOUSE_HOST/PORT (or CH_HOST/CH_PORT); URL host/port are fallback only.
        - URL credentials (userinfo/query) are always considered as fallback when explicit user/password env vars are unset.
        - If CLICKHOUSE_HOST itself is a URL, parse it with the same fallback rules.
        """

        host_raw = os.getenv("CLICKHOUSE_HOST") or os.getenv("CH_HOST")
        port_s = os.getenv("CLICKHOUSE_PORT") or os.getenv("CH_PORT")
        user = os.getenv("CLICKHOUSE_USER") or os.getenv("CLICKHOUSE_USERNAME") or os.getenv("CH_USER")
        password = os.getenv("CLICKHOUSE_PASSWORD") or os.getenv("CLICKHOUSE_PASS") or os.getenv("CH_PASSWORD")
        database = os.getenv("CLICKHOUSE_DATABASE") or os.getenv("CH_DATABASE") or "default"

        host = host_raw

        # Parse URL-like host env first when provided as full DSN in CLICKHOUSE_HOST.
        url_candidates: list[str] = []
        if host_raw and "://" in host_raw:
            url_candidates.append(host_raw)
            host = None
        http_url = os.getenv("CLICKHOUSE_HTTP_URL") or os.getenv("CLICKHOUSE_URL")
        if http_url:
            url_candidates.append(http_url)

        for url_s in url_candidates:
            try:
                from urllib.parse import parse_qs, urlparse

                u = urlparse(url_s)
                if u.hostname:
                    host = host or u.hostname
                if u.port:
                    port_s = port_s or str(u.port)

                if not user:
                    user = u.username
                if not password:
                    password = u.password

                q = parse_qs(u.query)
                if not user:
                    user = (q.get("user", [None])[0] or q.get("username", [None])[0])
                if not password:
                    password = q.get("password", [None])[0]
            except Exception:
                # best-effort; fall back to defaults below
                pass

        return cls(
            host=host or "localhost",
            port=int(port_s or "8123"),
            user=user or "default",
            password=password or "",
            database=database,
            timeout_s=int(os.getenv("CLICKHOUSE_TIMEOUT_S", "30")),
            queries_registry_path=queries_registry_path,
        )

    def _load_registry(self, path: Path) -> dict[str, QueryDef]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        funcs = raw.get("functions", {}) or {}
        out: dict[str, QueryDef] = {}
        for name, spec in funcs.items():
            out[name] = QueryDef(
                name=name,
                sql_path=str(spec["sql"]),
                params=list(spec.get("params", []) or []),
            )
        return out

    def list_functions(self) -> list[str]:
        return sorted(self._registry.keys())

    def get_query_def(self, name: str) -> QueryDef:
        if name not in self._registry:
            raise KeyError(f"Unknown query function: {name}")
        return self._registry[name]

    def read_sql(self, sql_path: str | Path) -> str:
        p = Path(sql_path)
        if not p.is_absolute():
            p = self.repo_root / p
        return p.read_text(encoding="utf-8")

    @contextmanager
    def session(self, timeout_s: int = 60) -> Iterable[str]:
        session_id = uuid.uuid4().hex
        try:
            yield session_id
        finally:
            # best-effort close (ClickHouse will expire sessions automatically)
            try:
                self.execute_raw("SELECT 1", session_id=session_id, settings={"session_timeout": 1})
            except Exception:
                pass

    def _url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def execute_raw(
        self,
        sql: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        database: Optional[str] = None,
        session_id: Optional[str] = None,
        settings: Optional[Mapping[str, Any]] = None,
        max_retries: int = 3,
        backoff_s: float = 0.25,
    ) -> str:
        """Execute SQL via ClickHouse HTTP interface.

        P0 extras:
        - retry transient transport/5xx/429 errors (best-effort)
        - supports query parameters (param_<name>=...) for {name:Type} placeholders
        """
        settings = dict(settings or {})

        def _is_retryable_http(code: int) -> bool:
            return code in (408, 425, 429, 500, 502, 503, 504)

        last_err: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            qp: dict[str, Any] = {"database": (database or self.database)}
            if self.user:
                qp["user"] = self.user
            if self.password:
                qp["password"] = self.password
            if session_id:
                qp["session_id"] = session_id
                qp.setdefault("session_timeout", settings.pop("session_timeout", 60))
            for k, v in settings.items():
                qp[k] = v

            # ClickHouse query parameters use param_<name>=...
            if params:
                for k, v in params.items():
                    qp[f"param_{k}"] = v

            url = self._url() + "?" + urlencode(qp, doseq=True)
            req = Request(url=url, data=sql.encode("utf-8"), method="POST")
            req.add_header("Content-Type", "text/plain; charset=utf-8")

            try:
                with urlopen(req, timeout=self.timeout_s) as resp:
                    body = resp.read()
                    return body.decode("utf-8", errors="replace")
            except HTTPError as e:
                body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
                # Retry only transient classes; syntax/semantic errors should fail fast.
                if _is_retryable_http(getattr(e, "code", 0)) and attempt < max_retries:
                    last_err = e
                    time.sleep(backoff_s * (2**attempt))
                    continue
                raise RuntimeError(f"ClickHouse error {e.code}: {body[:1000]}") from e
            except URLError as e:
                if attempt < max_retries:
                    last_err = e
                    time.sleep(backoff_s * (2**attempt))
                    continue
                raise RuntimeError(f"ClickHouse connection error: {e}") from e

        # Should be unreachable
        raise RuntimeError(f"ClickHouse request failed after retries: {last_err}") from last_err


    def execute_function(
        self,
        name: str,
        fn_params: Mapping[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> str:
        qd = self.get_query_def(name)
        sql = self.read_sql(qd.sql_path)
        placeholders = extract_placeholders(sql)

        expected = set(placeholders.keys())
        got = set(fn_params.keys())

        missing = expected - got
        extra = got - expected
        if missing or extra:
            raise ValueError(
                f"Param mismatch for {name}: missing={sorted(missing)} extra={sorted(extra)}"
            )

        # Enforce registry params list matches placeholders too (defensive at runtime)
        reg = set(qd.params)
        if reg != expected:
            raise ValueError(
                f"Registry↔SQL drift for {name}: registry={sorted(reg)} sql={sorted(expected)}"
            )

        serialized: dict[str, str] = {}
        for pname, ptype in placeholders.items():
            serialized[pname] = _serialize_param(fn_params[pname], ptype)

        return self.execute_raw(sql, params=serialized, session_id=session_id)

    
    def execute_typed(
        self,
        sql: str,
        params: Mapping[str, Any],
        *,
        session_id: Optional[str] = None,
        settings: Optional[Mapping[str, Any]] = None,
    ) -> str:
        """Execute ad-hoc SQL containing {name:Type} placeholders with strict param matching."""
        placeholders = extract_placeholders(sql)
        expected = set(placeholders.keys())
        got = set(params.keys())
        missing = expected - got
        extra = got - expected
        if missing or extra:
            raise ValueError(f"Param mismatch for ad-hoc SQL: missing={sorted(missing)} extra={sorted(extra)}")
        serialized: dict[str, str] = {}
        for pname, ptype in placeholders.items():
            serialized[pname] = _serialize_param(params[pname], ptype)
        return self.execute_raw(sql, params=serialized, session_id=session_id, settings=settings)

    def select_json_each_row_typed(
        self,
        sql: str,
        params: Mapping[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Run a SELECT ... FORMAT JSONEachRow and parse the result into a list of dicts."""
        out = self.execute_typed(sql, params, session_id=session_id)
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows

    def select_int_typed(
        self,
        sql: str,
        params: Mapping[str, Any],
        *,
        session_id: Optional[str] = None,
    ) -> int:
        out = self.execute_typed(sql, params, session_id=session_id).strip()
        if not out:
            return 0
        return int(out.splitlines()[0].strip())

    def insert_json_each_row(
        self,
        table: str,
        rows: list[Mapping[str, Any]],
        *,
        session_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        """Insert rows using JSONEachRow.

        session_id is supported for TEMPORARY TABLE flows.
        """
        if not rows:
            return
        import json

        cols = list(rows[0].keys())
        for r in rows:
            if list(r.keys()) != cols:
                raise ValueError("All rows must have identical columns ordering")
        header = f"INSERT INTO {table} ({', '.join(cols)}) FORMAT JSONEachRow\n"
        body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
        self.execute_raw(header + body, session_id=session_id, max_retries=max_retries)

    def select_int(
        self,
        sql: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> int:
        out = self.execute_raw(sql, params=params, session_id=session_id).strip()
        if not out:
            return 0
        # ClickHouse may return multi-line, but scalar queries should be single value.
        return int(out.splitlines()[0].strip())

    def insert_row_if_not_exists(
        self,
        table: str,
        row: Mapping[str, Any],
        *,
        exists_sql: str,
        exists_params: Mapping[str, Any],
        session_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> bool:
        """Insert row only if exists_sql returns 0. Returns True if inserted."""
        if self.select_int(exists_sql, params=exists_params, session_id=session_id) > 0:
            return False
        self.insert_json_each_row(table, [row], session_id=session_id, max_retries=max_retries)
        return True

    def insert_json_each_row_idempotent_token(
        self,
        table: str,
        rows: list[Mapping[str, Any]],
        *,
        token_field: str = "idempotency_token",
        session_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> int:
        """Best-effort idempotent insert based on token_field.

        If a row with the same token already exists, insertion is skipped.
        Returns number of inserted rows.
        """
        inserted = 0
        for row in rows:
            tok = row.get(token_field)
            if not tok:
                self.insert_json_each_row(table, [row], session_id=session_id, max_retries=max_retries)
                inserted += 1
                continue
            exists_sql = f"SELECT count() FROM {table} WHERE {token_field} = {{{token_field}:String}}"
            if self.select_int(exists_sql, params={token_field: str(tok)}, session_id=session_id) > 0:
                continue
            self.insert_json_each_row(table, [row], session_id=session_id, max_retries=max_retries)
            inserted += 1
        return inserted
    def query_tsv(
        self,
        sql: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        database: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Run a SELECT and return raw TabSeparated text."""
        sql2 = sql.strip()
        if "FORMAT" not in sql2.upper():
            sql2 += "\nFORMAT TabSeparated"
        return self.execute_raw(sql2, params=params, database=database, session_id=session_id)

    def query_json(
        self,
        sql: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        database: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Run a SELECT and parse JSONEachRow."""
        sql2 = sql.strip()
        if "FORMAT" not in sql2.upper():
            sql2 += "\nFORMAT JSONEachRow"
        out = self.execute_raw(sql2, params=params, database=database, session_id=session_id)
        rows: list[dict[str, Any]] = []
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
        return rows



    def run_sql_file(self, path: str | Path, *, session_id: Optional[str] = None) -> None:
        """Execute a .sql file as multiple statements (naive splitter, OK for P0 SQL)."""
        p = Path(path)
        if not p.is_absolute():
            p = self.repo_root / p
        text = p.read_text(encoding="utf-8").replace("\ufeff", "")
        parts: list[str] = []
        buff: list[str] = []
        for line in text.splitlines():
            buff.append(line)
            if line.strip().endswith(";"):
                stmt = "\n".join(buff).strip()
                buff = []
                if stmt:
                    parts.append(stmt)
        tail = "\n".join(buff).strip()
        if tail:
            parts.append(tail)

        for stmt in parts:
            s = stmt.strip()
            if not s:
                continue
            self.execute_raw(s, session_id=session_id)


# Backwards-compatible alias
ClickHouseClient = ClickHouseQueryRunner
