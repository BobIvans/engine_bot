> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# STRATEGY → Universal Variables mapping (GMEE capture)

Этот документ связывает **Strategy Spec (Free‑First)** с тем, как данные должны выглядеть в **GMEE “Universal Variables”** (`uv.jsonl`) из capture pipeline (v22+).

Цель: любые источники (free/paid, временные trial) приводим к одному формату → потом **join‑им к сделкам/трейсам** и строим фичи/лейблы.

---

## 1) Формат UV (`uv.jsonl`) — что ожидаем

Каждая строка — одно наблюдение:

- `entity_type`: `"wallet"` / `"token"` / `"pool"` / `"route"` / `"market"`
- `entity_id`: идентификатор сущности (например, wallet address или token mint)
- `ts`: ISO‑8601 UTC
- `bucket_1s`, `bucket_1m`, `bucket_5m`: округления `ts` (для быстрых join‑ов)
- `var_name`: стабильное имя переменной (см. раздел 2)
- `value`: число (float/int)
- `unit`: `"usd"`, `"bps"`, `"sec"`, `"count"`, `"ratio"` и т.п.
- `confidence`: `0..1` (если источник приблизительный)
- `source_provider`: `"dune"`, `"jupiter"`, `"dexscreener"`, `"raydium_sdk"`, …
- `source_ref`: ссылка на RAW (например `raw_sha256`)

> Принцип: **все внешние источники заменяемы**. UV — “контракт между миром данных и стратегией”.

---

## 2) Нейминг `var_name` (стабильные префиксы)

Рекомендуемая схема:

- `wallet.*` — метрики кошельков (профилирование/тiering)
- `token.*` — метрики токена (цена/ликвидность/спред/объём/глубина)
- `pool.*` — метрики конкретного пула/AMM (если есть `pool_address`)
- `route.*` — метрики маршрута/квоты (Jupiter quote/route)
- `market.*` — “общий фон” (например congestion, base fees, if any)

Примеры:

- `wallet.roi_30d`, `wallet.winrate_30d`, `wallet.trades_30d`
- `token.price_usd`, `token.liquidity_usd`, `token.spread_bps`, `token.volume_5m`
- `route.slippage_est_bps`, `route.out_amount_usd`, `route.price_impact_bps`

---

## 3) Маппинг из Strategy Spec (контракты данных) в UV

### 3.1 `wallet_profile` → UV

| Strategy field | UV entity_type | UV var_name | unit |
|---|---|---|---|
| `roi_7d` | `wallet` | `wallet.roi_7d` | `ratio` |
| `roi_30d` | `wallet` | `wallet.roi_30d` | `ratio` |
| `roi_90d` | `wallet` | `wallet.roi_90d` | `ratio` |
| `winrate_30d` | `wallet` | `wallet.winrate_30d` | `ratio` |
| `trades_30d` | `wallet` | `wallet.trades_30d` | `count` |
| `median_hold_sec` | `wallet` | `wallet.median_hold_sec` | `sec` |
| `avg_size_usd` | `wallet` | `wallet.avg_size_usd` | `usd` |
| `tier` (категория) | `wallet` | `wallet.tier` | `category` |
| `role` (категория) | `wallet` | `wallet.role` | `category` |
| `preferred_dex` (категория) | `wallet` | `wallet.dex_pref_*` | `ratio` |

**entity_id:** Solana wallet address.

**ts:** время расчёта профиля (например daily snapshot).

---

### 3.2 `token_snapshot` → UV

| Strategy field | UV entity_type | UV var_name | unit |
|---|---|---|---|
| `price` | `token` | `token.price_usd` | `usd` |
| `liquidity_usd` | `token` | `token.liquidity_usd` | `usd` |
| `volume_5m` | `token` | `token.volume_5m_usd` | `usd` |
| `volume_30m` | `token` | `token.volume_30m_usd` | `usd` |
| `volume_1h` | `token` | `token.volume_1h_usd` | `usd` |
| `volume_24h` | `token` | `token.volume_24h_usd` | `usd` |
| `depth_bps_100` | `token` | `token.depth_bps_100` | `bps` |
| `depth_bps_300` | `token` | `token.depth_bps_300` | `bps` |
| `spread_bps` | `token` | `token.spread_bps` | `bps` |
| `top10_holders_pct` | `token` | `token.top10_holders_pct` | `pct` |
| `single_holder_pct` | `token` | `token.max_holder_pct` | `pct` |
| `honeypot_flag` | `token` | `token.honeypot_flag` | `bool` (0/1) |

**entity_id:** token mint.

**ts:** timestamp наблюдения (quote tick / snapshot tick).


#### Примечание по depth: `depth_1pct` / `depth_5pct`

- Если в стратегии/снапшотах вы храните **USD‑глубину** на ±1%/±5%, используйте:
  - `token.depth_1pct_usd` (unit `usd`)
  - `token.depth_5pct_usd` (unit `usd`)
- Если же вы храните **глубину как bps‑метрику** (как в ранних черновиках), то эквиваленты:
  - `depth_1pct` ↔ `token.depth_bps_100`
  - `depth_5pct` ↔ `token.depth_bps_500`

---

### 3.3 `trades_norm` (on‑chain события) → UV (опционально)

В стратегии `trades_norm` — это “event stream”. В GMEE это обычно отдельные таблицы/логи,
но если вы хотите держать “след лидера” как UV:

| Strategy field | UV entity_type | UV var_name | unit |
|---|---|---|---|
| `qty_usd` | `wallet` | `wallet.last_trade_size_usd` | `usd` |
| `side` | `wallet` | `wallet.last_trade_is_buy` | `bool` (0/1) |
| `platform` | `wallet` | `wallet.last_trade_platform_*` | `bool` (0/1) |

> Обычно полезнее хранить raw swaps отдельно, а в UV держать **аггрегаты/снэпшоты**.

---

### 3.4 `route_quote` / `execution quote` → UV

| Source | UV entity_type | UV var_name | unit |
|---|---|---|---|
| Jupiter quote | `route` | `route.slippage_est_bps` | `bps` |
| Jupiter quote | `route` | `route.price_impact_bps` | `bps` |
| Jupiter quote | `route` | `route.out_amount_usd` | `usd` |
| DEX SDK | `pool` | `pool.liquidity_usd` | `usd` |

**entity_id (route):** стабильный `route_id` (например hash от `in_mint,out_mint,amount,programs`).

---

## 4) Как это “склеивается” с GMEE

### 4.1 Snapshot → trade bundle (v23 glue)

- `out/capture/snapshots/<snapshot_id>/snapshot_manifest.json` фиксирует observed range и sha256 артефактов.
- v23 glue матчится по `trades.buy_time ∈ observed_range` (+ optional slack) и кладёт refs в bundle.

### 4.2 Join UV → trade (features per trade)

Для feature building обычно делаем:

- ключ сущности: `token_mint` (и/или `wallet`)
- окно по времени вокруг `buy_time`, например:
  - token snapshots: `[-60s, +5s]`
  - wallet profile snapshots: `[t_day_start, t_day_end]` или `[-24h, +0h]`

---

## 5) Минимальный “UV набор” для copy‑scalping v0.2

Чтобы стратегия работала без paid deps, достаточно:

1) **wallet_profile** (daily): `wallet.roi_30d`, `wallet.winrate_30d`, `wallet.trades_30d`, `wallet.median_hold_sec`
2) **token_snapshot** (near‑real‑time): `token.price_usd`, `token.liquidity_usd`, `token.spread_bps`, `token.volume_5m_usd`
3) **route quote** (optional but useful): `route.slippage_est_bps`, `route.price_impact_bps`

---

## 6) Пример провайдер‑маппинга (идея)

Ниже — “как должно выглядеть” (псевдо‑пример), чтобы внешний CSV/JSONL превратить в UV:

```yaml
# configs/providers/mappings/dune_wallet_profile.yaml (пример)
provider_id: dune_wallet_profile
entity_type: wallet
entity_id_field: wallet
timestamp_field: snapshot_ts
fields:
  roi_30d:
    var_name: wallet.roi_30d
    unit: ratio
  winrate_30d:
    var_name: wallet.winrate_30d
    unit: ratio
  trades_30d:
    var_name: wallet.trades_30d
    unit: count
```

Идея: любой источник → RAW snapshot → UV normalize → (далее join/labels).


---

### 3.5 `risk_regime` / overlay → UV

| Strategy field | UV entity_type | UV var_name | unit |
|---|---|---|---|
| `risk_score` (скаляр [-1..+1]) | `market` | `market.risk_score` | `score` |
| `risk_regime` (risk_on/risk_off/neutral) | `market` | `market.risk_regime` | `category` |

**entity_id:** `"solana"` или `"solana_memecoins"` (одна строка на рынок/сегмент).

**ts:** время пересчёта режима (например, раз в минуту).


---

## Aggressive layer state (Position-level UV)

Эти UV полезны для отладки и обучения “режима ракеты” (post-entry):

- `mode_base` (string): базовый режим позиции (`"U"|"S"|"M"|"L"`)
- `mode_active` (string): активный режим (`"U_base"`, `"U_aggr"`, …)
- `partial_taken` (bool): был ли сделан partial exit
- `partial_size_pct` (float): доля позиции, закрытая partial’ом (0–100)
- `peak_price` (float): максимальная цена с момента входа (для trailing)
- `trail_stop_pct_from_peak` (float): активный trailing параметр (если применимо)
- `aggr_locked_out_reason` (string): причина запрета агрессии (wallet/token/regime/risk)

Рекомендуемый `entity_type`: `"position"`, `entity_id`: `position_id`.


---

## Polymarket overlay + regime scalar (new UVs)

### Inputs (raw snapshot `P(t)`)
Рекомендуемый `entity_type`: `"pmkt"`, `entity_id`: `"global"` (или `market_id` для per‑market).

- `pmkt_p_bull` ∈ [0..1] — агрегированная bullish‑вероятность по выбранным рынкам (mid)
- `pmkt_p_change_1h` (float) — изменение bullish‑вероятности за 1 час
- `pmkt_p_change_24h` (float) — изменение bullish‑вероятности за 24 часа
- `pmkt_volume_z` (float) — z‑score всплеска объёма (по связанным рынкам)
- `pmkt_event_risk` ∈ [0..1] — (опц.) “шторм/resolve” (risk‑off фактор)
- `pmkt_data_quality` (категория) — ok / stale / missing

### Derived
- `regime_r` ∈ [-1..+1] — скаляр режима рынка (risk‑on / risk‑off)

Один из канонических вариантов агрегации:
- `regime_r = clip(tanh(w·z), -1, +1)`
- где `z = [pmkt_p_change_1h, pmkt_p_change_24h, pmkt_volume_z, -pmkt_event_risk]`

### How it is used (decision UVs)
- `p_min(regime_r)` — динамический порог модели (risk‑off → выше)
- `delta_ev(regime_r)` — минимальный EV/edge для входа (risk‑off → выше)
- `size_pct(regime_r)` — regime‑зависимый размер позиции
- `max_open_positions(regime_r)` — regime‑зависимый лимит параллельных позиций
- `aggr_allowed(regime_r)` — разрешение Aggressive Layer

### Where it plugs in code (for Codex)
- snapshot collector → `pmkt_snapshots`
- feature builder → `pmkt_features` / `regime_r`
- thresholds & sizing: `SignalEngine` + `RiskEngine`

