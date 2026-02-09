"""GMEE P0 SDK (Variant A).

This module is intended as a **drop-in integration package** for a main-repo.

P0 rules:
- Do not edit canonical SQL/DDL/YAML/docs.
- Writer enforces Tier-0 ordering + must-log IDs.
- compute_exit_plan executes queries/04_glue_select.sql (no re-implemented math).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .clickhouse import ClickHouseQueryRunner
from .config import compute_config_hash, glue_select_params_from_cfg, load_engine_config
from .models import ExitPlan, WriterContext
from .planner import compute_exit_plan
from .writer import Tier0Writer
from .runtime import assert_runtime_contracts
from .evidence import export_trade_evidence_bundle
from .replay import replay_trade_evidence_bundle


@dataclass(frozen=True)
class GMEE:
    """Convenience wrapper to wire runner + canonical config + writer."""

    runner: ClickHouseQueryRunner
    ctx: WriterContext
    engine_cfg: Mapping[str, Any]

    @classmethod
    def from_env(
        cls,
        *,
        ctx: WriterContext,
        engine_cfg_path: str = "configs/golden_exit_engine.yaml",
        queries_registry_path: str = "configs/queries.yaml",
        validate_contracts: bool = True,
    ) -> "GMEE":
        runner = ClickHouseQueryRunner.from_env(queries_registry_path=queries_registry_path)
        cfg = load_engine_config(engine_cfg_path)
        if validate_contracts:
            # No DB required. Ensures Codex has a single source of truth at runtime.
            assert_runtime_contracts(
                engine_cfg_path=engine_cfg_path,
                queries_registry_path=queries_registry_path,
                clickhouse_sql_path="schemas/clickhouse.sql",
                config_hash=ctx.config_hash if ctx.config_hash else None,
            )
        # If ctx.config_hash not set by caller, compute from canonical cfg.
        if not ctx.config_hash or str(ctx.config_hash).strip() == "":
            ctx = WriterContext(**{**ctx.__dict__, "config_hash": compute_config_hash(cfg)})
        return cls(runner=runner, ctx=ctx, engine_cfg=cfg)

    def writer(self) -> Tier0Writer:
        return Tier0Writer(self.runner, self.ctx)

    def plan(self, *, chain: str, trade_id: str) -> ExitPlan:
        return compute_exit_plan(chain, trade_id, self.engine_cfg, runner=self.runner)


    def export_evidence_bundle(self, trade_id: str, out_dir: str) -> str:
        """Export deterministic evidence bundle for the given trade_id."""
        p = export_trade_evidence_bundle(self.runner, trade_id, out_dir)
        return str(p)

    def replay_evidence_bundle(self, bundle_dir: str, *, skip_existing: bool = True, verify_hashes: bool = True) -> None:
        """Replay an evidence bundle into the currently configured ClickHouse database."""
        replay_trade_evidence_bundle(self.runner, bundle_dir, skip_existing=skip_existing, verify_hashes=verify_hashes)
