# Entity maps (non-canonical)

Entity maps let you attach stable metadata to any entity_type/entity_id without schema changes.
Use-cases:
- categorize rpc_arms (provider, region)
- categorize pools (dex, venue)
- categorize signal sources (vendor, strategy)

Format: YAML list of rows with `entity_type`, `entity_id`, and arbitrary attributes.

Example:
```yaml
- entity_type: rpc_arm
  entity_id: helius_a
  provider: helius
  region: us-east
```
