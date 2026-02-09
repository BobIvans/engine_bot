# Chat Bridge Pack (Engine ↔ Strategy)

Purpose: make it easy to connect this GMEE mini-ML engine repo with a separate “strategy chat” (signals, venues, execution steps).

## What you should copy between chats

1) **Strategy Manifest (from the strategy chat)**
- Markets/venues
- Instruments (token/pool/route)
- Execution steps (entry/exit, retries, routing)
- Signals (source list + fields)
- Constraints (latency, cost, risk)
- Success metrics
- Entities besides wallets (pool_id, token_mint, rpc_arm, route, source, ...)

2) **Data Contract Map (create from strategy→engine)
For each strategy item, map:
- Tier-0 table + columns (or JSON keys)
- DataGatherer name(s)
- feature_db entity_type/entity_id
- rule-pack rule(s) that consume the metric
- investigation artifact (bundle/report)

3) **Execution Plan (Codex task list)
- ingestion/writer wiring (Tier-0 ordering)
- which gatherers to enable
- which rule-pack rules to enable
- which CI gates must pass

## One-command investigation workflow
If you already have a `trade_id`:

```bash
python3 tools/one_button_investigate.py --trade-id <TRADE_UUID>
```

It will:
- find trace_id
- export a trace-scope evidence bundle
- validate bundle hashes
- render deterministic HTML report

