# PR-PM.3 — Event Risk Aggregator

**Stage:** Event Risk Detection  
**Owner:** Risk Layer  
**Status:** Active  
**Last Updated:** 2025-02-07

---

## Overview

Detects high-risk calendar events from Polymarket snapshots and calculates event risk metrics. Events are classified by type (election, ETF, regulatory, etc.) and flagged as high-risk when critical events are within 7 days of resolution.

## Event Type Classification

Event types are determined by keyword matching in the `question` field (case-insensitive, word boundaries):

| Event Type | Keywords | Critical |
|------------|----------|----------|
| `election` | `election`, `vote`, `president`, `Trump`, `Harris`, `ballot` | ✅ Yes |
| `etf` | `ETF`, `spot ETF`, `Bitcoin ETF`, `Ethereum ETF`, `approve ETF` | ✅ Yes |
| `regulatory` | `SEC`, `regulation`, `ban`, `approve`, `reject`, `lawsuit`, `compliance` | ✅ Yes |
| `fed` | `Fed`, `FOMC`, `interest rate`, `Powell`, `monetary policy` | ❌ No |
| `macro` | `recession`, `inflation`, `GDP`, `unemployment` | ❌ No |
| `other` | Fallback for unclassified events | ❌ No |

### Classification Priority

Types are checked in order: `election > etf > regulatory > fed > macro > other`. First match wins.

## High Risk Threshold

```
high_event_risk = (event_type ∈ {election, etf, regulatory}) 
                  AND (days_to_resolution ≤ 7) 
                  AND (days_to_resolution ≥ 0)
```

**Conditions:**
1. Event type must be critical (election, ETF, or regulatory)
2. Event must be within 7 days (inclusive)
3. Event must not have already passed (days ≥ 0)

## Days Calculation

```
days_to_resolution = floor((event_date_unix_ms - now_ts_ms) / (24 * 3600 * 1000))
```

- **Positive value:** Future event
- **Zero:** Event resolves today
- **Negative value:** Event has already passed

## Aggregation Rule

When multiple events exist in a snapshot, the **closest event by absolute time** is selected:

```
selected_event = argmin(abs(days_to_resolution))
```

This ensures the most temporally relevant event is flagged, regardless of whether it's upcoming or recently passed.

## Output Schema

| Field | Type | Description |
|-------|------|-------------|
| `ts` | integer | Snapshot timestamp (milliseconds since epoch) |
| `high_event_risk` | boolean | True if critical event within 7 days |
| `days_to_resolution` | integer | Days until event resolution |
| `event_type` | string | Classification: election, etf, regulatory, fed, macro, other |
| `event_name` | string | Truncated question (max 80 chars) |
| `source_snapshot_id` | string | Market ID from source snapshot |

## Pipeline Interface

### CLI

```bash
python3 -m ingestion.pipelines.event_risk_pipeline \
    --input polymarket_snapshots.parquet \
    --output event_risk_timeline.parquet \
    --fixed-now-ts=1738945200000 \
    --dry-run \
    --summary-json
```

### Parameters

| Parameter | Required | Description |
|-----------|---------|-------------|
| `--input` | Yes | Path to input parquet or JSON file |
| `--output` | No | Output parquet path (default: `event_risk_timeline.parquet`) |
| `--fixed-now-ts` | No | Fixed timestamp for deterministic output |
| `--dry-run` | No | Skip parquet export |
| `--summary-json` | No | Output single-line JSON to stdout |

### Summary JSON Output

When `--summary-json` is set, stdout contains exactly:

```json
{
  "high_event_risk": true,
  "days_to_resolution": 7,
  "event_type": "regulatory",
  "ts": 1738945200000,
  "schema_version": "1.0.0"
}
```

All other logs are written to stderr.

## Integration

### Optional Stage Flag

```bash
python3 -m integration.wallet_discovery --skip-event-risk
```

When `--skip-event-risk` is set, the event risk stage is bypassed without error.

### Data Flow

```
polymarket_snapshots.parquet
    ↓
[EventRiskPipeline]
    ↓
event_risk_timeline.parquet
```

## Test Fixtures

### Deterministic Test Case

**Fixed timestamp:** `1738945200000` (2025-02-07)

| Market ID | Question | Event Date | Days | Type | High Risk |
|-----------|----------|------------|------|------|-----------|
| election-2024-trump | Will Trump win 2024 election? | 1733644800000 | -61 | election | ❌ (passed) |
| etf-eth-march15 | Will spot ETH ETF be approved by SEC before March 15, 2025? | 1742054400000 | 36 | etf | ❌ (days > 7) |
| regulatory-sol-feb14 | Will SEC approve spot SOL ETF by February 14, 2025? | 1739577600000 | 7 | regulatory | ✅ |
| fed-march2025 | Will Fed cut rates in March 2025? | 1741046400000 | 25 | fed | ❌ (non-critical) |
| btc-150k-april | Will Bitcoin hit $150K before April 2025? | 1743465600000 | 55 | other | ❌ (non-critical) |

**Expected Result:** `high_event_risk=True`, `days_to_resolution=7`, `event_type="regulatory"`

## Smoke Test

```bash
bash scripts/event_risk_smoke.sh
```

Expected output:
```
[overlay_lint] running event_risk smoke...
[event_risk_smoke] detected high_event_risk=True (regulatory, 7 days to resolution)
[event_risk_smoke] OK
```

## Edge Cases

| Scenario | Expected Result |
|----------|-----------------|
| Event through 8 days | `high_event_risk=false` |
| Event type "macro" through 3 days | `high_event_risk=false` (non-critical type) |
| All events passed | `high_event_risk=false`, closest negative `days_to_resolution` |
| No events with valid dates | `high_event_risk=false`, empty fields |
| Empty input | `high_event_risk=false`, empty fields |

## Files

| Path | Purpose |
|------|---------|
| `analysis/event_risk.py` | Pure functions for event detection and risk calculation |
| `ingestion/pipelines/event_risk_pipeline.py` | Pipeline orchestrator |
| `integration/fixtures/sentiment/polymarket_sample_events.json` | Deterministic test fixture |
| `scripts/event_risk_smoke.sh` | Smoke test script |
| `strategy/schemas/event_risk_timeline_schema.json` | Output schema definition |

## Schema Compliance

Output must validate against `event_risk_timeline_schema.json`:

```json
{
  "type": "object",
  "properties": {
    "ts": {"type": "integer", "minimum": 0},
    "high_event_risk": {"type": "boolean"},
    "days_to_resolution": {"type": "integer", "minimum": -365, "maximum": 365},
    "event_type": {"type": "string", "enum": ["election", "etf", "regulatory", "fed", "macro", "other"]},
    "event_name": {"type": "string", "minLength": 1},
    "source_snapshot_id": {"type": "string"}
  },
  "required": ["ts", "high_event_risk", "days_to_resolution", "event_type", "event_name", "source_snapshot_id"]
}
```
