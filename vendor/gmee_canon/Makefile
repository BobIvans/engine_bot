.PHONY: deps ch-up ch-down ddl explain canary oracle writer-guard determinism gates ci

# Local "one button" runner for the same gates as CI.
#
# P0 scope: do NOT change canon (docs/configs/schemas/queries/scripts).

# Backstop for running repo scripts without installing as a package.
# (CI scripts also include a sys.path shim; this keeps local runs uniform.)
export PYTHONPATH := .

CH_HTTP ?= http://localhost:8123

deps:
	python3 -m pip install --upgrade pip >/dev/null
	python3 -m pip install pyyaml >/dev/null

ch-up:
	docker compose up -d clickhouse

ch-down:
	docker compose down -v

ddl: ch-up
	docker exec -i clickhouse clickhouse-client --multiquery < schemas/clickhouse.sql

explain: ch-up
	# CI/local must use the same execution path as the engine (HTTP named params),
	# not sed/regex templating.
	CLICKHOUSE_HTTP_URL=$(CH_HTTP) CLICKHOUSE_DATABASE=default python3 ci/explain_syntax_gate.py

canary: ch-up
	docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_golden_trace.sql
	docker exec -i clickhouse clickhouse-client --multiquery < scripts/canary_checks.sql

determinism:
	python3 ci/check_wallet_profile_determinism.py

oracle:
	CLICKHOUSE_HTTP_URL=$(CH_HTTP) CLICKHOUSE_DATABASE=default python3 ci/oracle_glue_select_gate.py

writer-guard:
	CLICKHOUSE_HTTP_URL=$(CH_HTTP) CLICKHOUSE_DATABASE=default GMEE_ORDERING_MODE=hard \
		python3 ci/check_writer_ordering_db_asserts.py

gates: deps ddl
	python3 scripts/assert_no_drift.py
	python3 ci/yaml_literal_ban_guard.py
	$(MAKE) determinism
	$(MAKE) explain
	$(MAKE) canary
	$(MAKE) oracle
	$(MAKE) writer-guard

ci: gates
	@echo "OK: all P0 gates passed"
