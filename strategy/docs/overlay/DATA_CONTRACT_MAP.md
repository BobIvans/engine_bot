# DATA_CONTRACT_MAP (strategy → CANON tables)

Этот файл **связывает** стратегию “copy-scalp” с уже существующими таблицами CANON (ClickHouse).
Он нужен агентам, чтобы **не придумывать новые таблицы** и писать ровно в разрешённые writer’ы.

> Детальная P0-карта таблиц и инварианты: `docs/data_contract_map.md` (корневые доки репо).

## Сущности стратегии → таблицы

| Entity (стратегия) | Поля (минимум) | Куда пишем (CANON) | Какой writer |
|---|---|---|---|
| Signal (entry) | `ts, chain, env, trace_id, source, token_mint, side, mode, p_model, reasons_json` | `signals_raw` | `integration/write_signal.py` |
| Wallet score / tier | `ts, chain, env, wallet, tier, roi_30d, winrate_30d, trades_30d, features_json` | `wallet_score` | `integration/write_wallet_score.py` |
| Allowlist version | `ts, chain, env, path, wallets_count, allowlist_hash` | `forensics_events` (`kind=allowlist_version`) | `integration/write_signal.py` (опционально) |
| Config version | `ts, chain, env, path, strategy_name, version, config_hash` | `forensics_events` (`kind=config_version`) | `integration/paper_pipeline.py` (новый) |
| Runner meta | `ts, chain, env, git_sha?, run_id, notes` | `forensics_events` (`kind=run_meta`) | любой runner |
| Execution attempts (paper/sim) | `attempt_id, trace_id, venue, order_type, ttl_sec, slippage_bps, status` | `execution_attempts` (если используется) | (опционально позже) |
| Fills / simulated trades | `trade_id, attempt_id, fill_px, fill_qty, fees, pnl` | `trades_fills` / `trades_sim` (если используется) | (опционально позже) |

## Нормализация входного trade-event (минимум)

Единый формат входа в pipeline (для JSONL/стрима), поля:
`ts, wallet, token_mint, side, size_token, size_usd, platform, tx_hash, pool_address`.

- Data-track должен писать это в parquet/duckdb.
- Bot-track должен принимать это как “сырьё” и дальше enrich’ить.

## Запреты (чтобы не сломать CANON)
- Не добавляем новые SQL/схемы вне `vendor/gmee_canon/**`.
- Не пишем напрямую в таблицы — только через существующие integration writer’ы.
