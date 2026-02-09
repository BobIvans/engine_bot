# PR labels (repo contract)

This repo uses a **machine-readable** Source of Truth (SoT): `strategy/docs/overlay/pr_labels.v1.json`.

## Allowed labels (v1)

### Scope (exactly one)
- `agent_scope:tiny`
- `agent_scope:small`
- `agent_scope:medium`
- `agent_scope:large`

### Priority (exactly one)
- `agent_priority:P0`
- `agent_priority:P1`
- `agent_priority:P2`
- `agent_priority:P3`

### Type (exactly one)
- `agent_type:code`
- `agent_type:docs`
- `agent_type:fixtures`
- `agent_type:ci`

### Layer (exactly one)
- `agent_layer:integration`
- `agent_layer:features`
- `agent_layer:tools`
- `agent_layer:strategy_docs`
- `agent_layer:scripts`

## Rules

For every PR/task, pick **exactly one** label from each group:

1) `agent_scope:*`
2) `agent_priority:*`
3) `agent_type:*`
4) `agent_layer:*`
