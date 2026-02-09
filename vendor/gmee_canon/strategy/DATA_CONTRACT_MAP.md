# Data Contract Map (Repo Artifact)

Translate strategy → storage contracts → QA checks.

For each provider_id / source, document:

1) **Where raw events land** (which Tier-0 table + which ids)
2) **Which normalized variables are produced** (universal keys)
3) **Which checks are mandatory** (null rates, drift, suspect/reorg handling)
4) **Which rule-pack rules depend on them** (rule id linkage)

## Template

### provider_id: <id>
- raw_events:
  - table: signals_raw|rpc_events|...
    required_ids: [trace_id, trade_id...]
    fields: [...]...
- normalized_variables:
  - entity_type: ...
    entity_id: ...
    key: ...
    value_type: ...
- qa:
  - check_id: ...
    type: null_rate|range|drift|join_coverage
- rulepack:
  - rule_id: ...
    triggers_on: [key1, key2]
