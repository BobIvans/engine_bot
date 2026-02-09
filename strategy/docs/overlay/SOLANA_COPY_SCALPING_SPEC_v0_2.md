> **Overlay-only**: This document is guidance. **CANON is `vendor/gmee_canon/**` (read-only)**.  
> Do not copy overlay code/queries/DDL into CANON. Implement changes only in `integration/**` and `strategy/**`.

# Solana Copy‑Scalping Strategy Spec (Free‑First) — v0.2

## 0) Цель и принципы
**Цель:** автоматический copy‑scalping мемкоинов в Solana по действиям «успешных» кошельков:

**on‑chain события → нормализация → фичи → (ML опционально) → +EV сигнал → симуляция/paper → метрики.**

**Free‑first:** ядро работает на open‑source и free tiers (или кредиты ≥ 7 дней).  
**Платные ускорители** (private RPC, Jito tips, платные терминалы) — только после доказанного edge.  
Терминалы (BullX/GMGN/Axiom и т.п.) — **не интегрируем** в ядро, максимум для ручного ресёрча.

## 1) Две параллельные дорожки
1) **Data‑track:** история + realtime пишутся в единый формат.  
2) **Bot‑track:** сервисный pipeline (сначала без real‑торговли):  
**Listener → Normalizer → FeatureBuilder → SignalEngine → Simulator → Metrics.**

## 2) Data Map (что и откуда)
### 2.1 Discovery кошельков (seed → profiling → tiering)

**Ключевая фиксация:** BullX/GMGN/Axiom и подобные — это **UI‑терминалы**, а не источник данных.  
Всё, что они показывают, лежит в публичном on‑chain и может быть собрано через наши адаптеры.

**Primary (SQL‑лидерборды → “как BullX/GMGN”, но бесплатно):**
- **Kolscan** — seed‑листы/лидерборды и первичные метрики (free‑first).
- **Dune (curated DEX trades)** — SQL‑отбор по ROI/winrate/trades_count + выгрузки.
- **Flipside (decoded swaps)** — альтернативный слой decoded DEX swaps для независимой выборки и проверки.

**Secondary (indexers/enrichment, только если не становятся SPOF):**
- **SolanaFM API** — быстрые account/tx выборки и декодирование (rate‑limited).
- **Covalent / Moralis** — готовые endpoints “wallet → tx/swaps” (free tiers; строго с кэшем).
- **Birdeye / DexScreener** — обогащение/санити‑чек по ценам/ликвидности (строго с кэшем).

**Optional paid accelerators (НЕ ядро):**
- Solscan Pro API и т.п. — только как ускорители, если уже доказан edge.

**Алгоритм “максимальный охват успешных кошельков”:**
1) `seed_wallets = union(Kolscan лидеры, Dune лидеры, Flipside лидеры)` → дедуп.
2) `label_memecoin_traders` → доля сделок в “мем‑универсуме”, вола/возраст токенов, DEX‑профиль.
3) `score_wallets` → ROI/winrate/median_hold + стабильность (trades_30d, maxDD proxy).
4) `expand_set` → “near‑leader” кошельки: ко‑входы в те же токены в узком окне (граф/кластер).
5) `tiering` → T0/T1/T2 + лимиты realtime (free‑tier friendly).

### 2.2 История сделок (для backtest/ML)
 История сделок (для backtest/ML)
- Dune экспорт / RPC batch (Helius/Alchemy) по Tier‑листу.
- Pump.fun (swaps/launchpad) как дополнительный источник свопов: нормализовать в `trades_norm` (история и realtime).
- (опц.) BigQuery public datasets (если тянем сырые tx).
- Хранилище по умолчанию: **Parquet + DuckDB локально**, (опц.) BigQuery sandbox/free tier как витрина/SQL.

### 2.3 Realtime ingestion
- Helius/Alchemy (free tiers): webhooks/WS/stream → тот же контракт `trades_norm`.

### 2.4 Token/Pool snapshots (фильтры + slippage/TTL)
- Jupiter quote/route (цена/маршрут/slippage‑оценка).
- DEX SDK/API: Raydium/Orca/Meteora (ликвидность/параметры AMM).
- Dexscreener/Birdeye — sanity‑check, **строго с кэшем и лимитами**.

### 2.5 Соц/новости (опционально)
- LLM‑классификация внешнего текста: pump / scam / neutral как контекст‑фича.
- По умолчанию **выключено**; включать только при стабильном источнике и понятной метрике полезности.



### 2.6 Polymarket overlay (optional, free/read‑only)
Polymarket используется как **внешний сентимент/режим рынка** (не как торговая система).

- Источник: публичные read‑only API (Gamma / CLOB snapshot).
- Выход: `risk_regime ∈ [-1; +1]` + набор фич (`pmkt_p_bull`, `pmkt_p_change_1h`, `pmkt_volume_z`, …).
- Использование: динамические пороги (`δ`, `p_model_min`) + масштабирование size + блокировка/разрешение Aggressive Layer.

Важно: список рынков — **конфиг**; оверлей не должен быть SPOF (при деградации → `risk_regime=0`).


## 3) Канонические контракты данных
### 3.1 `trades_norm`
- `ts_block/ts` (UTC), `slot`
- `wallet`, `mint`, `side` (BUY/SELL)
- `qty_token`, `qty_usd` (если нет — пересчёт через snapshot)
- `price` (mid/quote), `platform`, `tx_hash`, `pool_address` (если доступно)

### 3.2 `token_snapshot`
- `ts`, `mint`, `price`
- `liquidity_usd`
- `volume_5m/1h/24h`
- `depth_bps_100/300` (опц.), `spread_bps` (если есть)
- `honeypot_flag` (если считаем)

### 3.3 `wallet_profile` / `wallets`
- `wallet`
- `roi_7d/30d/90d`, `winrate_30d`, `trades_30d`
- `median_hold_sec`, `avg_size_usd`, `preferred_dex`
- `cluster_label/role` (sniper/deployer/follower/arb/…), `tier`

### 3.4 `signals`
- `signal_id`, `ts`, `wallet`, `mint`
- `mode` (U/S/M/L + *_aggr опц.)
- `entry_price`, `limit_price`, `ttl_sec`, `max_slippage_bps`
- `p_model` (если ML), `edge_raw/edge_final`
- `decision` (ENTER/SKIP), `reject_reason`

### 3.5 `sim_fills` / `executions` / `positions_pnl`
- fills: `filled`, `fill_price`, `slippage_bps`, `latency_ms`, `reason`
- positions: `open_ts`, `close_ts`, `entry`, `exit`, `pnl_pct/pnl_usd`, `exit_reason`
- `pnl_daily`: `date`, `roi`, `max_dd`, `winrate`, `fill_rate`, `trades`


### 3.6 `pmkt_snapshots` / `pmkt_features` (optional)
- snapshots: `ts`, `market_id`, `event_id`, `p_yes`, `p_no`, `bid`, `ask`, `volume`, `end_ts`
- features (per ts): `pmkt_p_bull`, `pmkt_p_change_1h`, `pmkt_p_change_24h`, `pmkt_volume_z`, `risk_regime`
- audit trail: `risk_regime` должен попадать в `signals`/`executions` как объяснимый фактор решения


## 4) Universe и базовые гейты
### 4.1 Token universe
- Research‑mode (сбор статистики): `min_liquidity_usd = 2–5k`
- Trade‑safe (входы): `min_liquidity_usd = 15–50k`
- Фильтры: `max_spread_bps = 100–200`, (опц.) `min_volume_24h = 50–100k` (тюнинг по бэктесту)

### 4.2 Wallet universe
Seed → профилирование → tiering.
- Минимальные фильтры старта: `min_trades_30d ≥ 30`, `roi_30d > 0`, `avg_trade_size ≥ 0.2–0.5 SOL`.
- Tier‑1 (входы/paper): `roi_30d ≥ 20–30%`, `winrate_30d ≥ 55–60%`, `min_trades_30d ≥ 50`.

## 5) Feature engineering (v1)
### 5.1 Wallet features
`roi_7d/30d/90d`, `winrate_30d`, `trades_30d`, `median_hold_sec`, `avg_size_usd`, `dex_pref`,
(опц.) `max_dd_30d`, `cluster/role`.

### 5.2 Trade/token features (на событии)
`ret_30s/1m/5m`, `vol_30s/5m`, `liquidity_usd`, `volume_5m/24h`,
`spread_bps` или `slippage_est_bps(size)`, co‑entries/кластерные сигналы (если есть).

### 5.3 Context features (опц.)
LLM‑теги pump/scam/neutral как бинарные признаки.

## 6) Решение ENTER/SKIP и +EV
### 6.1 MVP без ML
Rule‑based входы + симуляция (TP/SL/hold) — чтобы проверить наличие edge.

### 6.2 ML‑версия (опц.)
- Модель: Logistic / XGBoost.
- Label: `roi_after_5m > 0` (или > X%).
- CV: time‑series split.
- Evaluation: **walk‑forward backtest** (rolling train→test windows) + time‑series split to approximate live performance and detect drift.
- Калибровка: Platt/Isotonic.

### 6.3 +EV фильтр
- Базовый порог: `p_model ≥ 0.55–0.60` (калиброванная вероятность).
- Жёсткие запреты: ликвидность ниже минимума, спред выше максимума, кошелёк ниже порогов, honeypot‑флаг.

## 7) Режимы U/S/M/L и исполнение
### 7.1 База по hold‑окну
- **U:** 15–30s (TP/SL порядка ±2–4%)
- **S:** 60–90s (TP/SL порядка ±4–6%)
- **M:** 120–180s (TP/SL порядка ±6–10%)
- **L:** 240–300s (TP/SL порядка ±10–15%)

### 7.2 Execution simulator (обязательные элементы)
- latency‑модель
- slippage‑модель (AMM impact + caps)
- limit + TTL + partial fills
- цель по качеству: `fill_rate ~ 0.70–0.85` (как таргет в симе)

### 7.3 Aggressive режим (*_aggr, опц.)
- включается при быстром импульсе цены за короткое время (по конфигу)
- partial take + trailing после частичной фиксации

## 8) Risk engine (v1)
- Размер позиции: 0.5–2% банка (позже — fractional Kelly)
- Лимиты: max open positions, max exposure per token, max daily loss, max drawdown → kill‑switch
- **Kill‑switch (обязателен):** при превышении `max_daily_loss` или `max_drawdown_total` → остановить новые входы и перейти в режим расследования.
- Cooldown после серии лоссов

## 9) Метрики (что считаем и мониторим)
- ROI, winrate, max drawdown
- fill_rate, slippage, latency
- разбивка по режимам (U/S/M/L), кошелькам, токенам, причинам reject, причинам exit

## 10) Runbook v0.2
### 10.1 1–10 (ядро)
1) Repo‑скелет + конфиги  
2) Контракты таблиц (раздел 3)  
3) DuckDB+Parquet как «истина»  
4) Wallet discovery v1: Kolscan seed‑лист  
5) Dune export v1: wallet metrics → wallets  
6) Нормализатор любых входов → trades_norm  
7) Симулятор fill v1: limit+TTL+простая slippage  
8) Baseline стратегия без ML (правила + гейты)  
9) Метрики ROI/winrate/DD/fill  
10) Paper loop: realtime → signal → simulate → pnl

### 10.2 11–20 (усиление)
11) Token snapshots cache + rate limiting  
12) FeatureBuilder v1 (vol/impulse/liquidity + wallet ctx)  
13) Разметка таргета + TimeSeriesSplit  
14) Модель v1 (logreg/XGB) + калибровка  
15) +EV расчёт: costs+payoff → edge  
16) Honeypot gates v1 + реестр причин reject  
17) Exit logic v1: TP/SL/TIME + трейлинг после partial  
18) Wallet profiling v2: роли/кластеры + граф связей  
19) Walk‑forward backtest + параметр‑лидерборд  
20) Daily report + мониторинг fill/latency, шардирование кошельков по воркерам + rate limiting


---

## 11) Free‑first “Money Filter” + параллельная сборка

Чтобы стратегия оставалась **0$‑friendly** на старте и не зависела от платных провайдеров:

- см. `FREE_FIRST_MONEY_FILTER_AND_PARALLEL_TRACKS.md` — список Green/Amber инструментов (free ≥ 7 дней), правила кэша/лимитов и схема двух треков (Data‑track vs Bot‑track).
- канонический конфиг: `config/params_base.yaml` (v3.0), режимы вынесены в `config/modes.yaml`.

Критично: в неделю 1 **Jito/fee‑гонка = OFF**; моделируем latency/MEV в симуляции и обкатываем risk‑ограничители на истории/paper.


---

## Money-filter and free-first stack (v7)
- Week-1 rule: only free tooling or free tiers/trials ≥ 7 days.
- See `FREE_FIRST_MONEY_FILTER_AND_PARALLEL_TRACKS.md`.
- Canonical GMEE config lives in `config/params_base.yaml`.


---

## Aggressive Layer (“режим ракеты”)

Агрессивный слой — **надстройка** над U/S/M/L (post-entry). Входы/фильтры остаются прежними; меняется ведение позиции: partial → runner → trailing, включается только по safety-filter.

Подробный канон: см. `AGGRESSIVE_LAYER_ROCKET_MODE.md`.


---

## Unified Decision Formula — One‑Formula Strategy

Добавлен канонический алгоритм принятия решения **on‑chain event → ENTER/SKIP → mode → size → execution params** с Polymarket‑оверлеем, +EV‑фильтром и риск‑лимитами.

См. отдельный документ: `UNIFIED_DECISION_FORMULA_ONE_FORMULA.md`.

---

## Operational Addendum (Idempotency / Reorg / Canary / Audit)

Этот блок добавлен, чтобы на масштабе **200 → 1000** было что тюнить и что воспроизводить.

### 1) Nonce / concurrency / idempotency policy (multi‑RPC fanout)
**Цель:** повторный сигнал / ретрай / fanout по нескольким RPC не должен создавать дубль‑сделку и не должен ломать метрики.

Минимум:
- `idempotency_key` на каждую попытку entry/exit (детерминированный hash от chain|wallet|token|pool|signal_time|source|experiment_id).
- Дедуп по `idempotency_key` в окне (например 10 минут).
- Политика ретраев: max_attempts + backoff.
- Политика конкуренции: сериализация по `wallet` (или `wallet,token`) чтобы не ловить гонки.

### 2) Reorg / partial confirmation logic
**Что считать “подтверждением”:**
- Solana: явная policy по commitment (`confirmed`/`finalized`) и обработка “сомнительных” подтверждений.
- EVM: N confirmations + reorg window; при reorg — карантин и корректировка статуса/PnL.

Правило: подозрительные сделки должны уходить в `failure_mode=reorg_suspect` и **не попадать в wallet_agg** до резолва.

### 3) Per‑arm circuit breaking (RPC)
Один плохой RPC‑arm не должен убивать:
- симуляцию,
- метрики,
- routing decision.

Минимум:
- если `fail_rate` > threshold или `p90_latency` > baseline*mult → arm в cooldown на cooldown_sec,
- логировать cooldown решения в must‑log.

### 4) Canary/Testnet E2E replay
Отдельная среда + регулярные smoke прогоны:
- до промоции в paper/live,
- по расписанию (например daily),
- с проверками: monotonic time audit, idempotency, read‑queries, cost gates.

### 5) Signed artifacts / audit trail промоций
Промоция конфига в live должна оставлять “след”:
- `config_hash`, `seed`, окна данных/backfill snapshot,
- `artifact_uri` (метрики + CI/p-value, отчёт canary),
- подпись артефактов (GPG/KMS) + запись “кто дал GO”.

### 6) Governance / Legal / Ethics (минимум)
В README/runbook фиксируем:
- paper‑first и обязательный canary,
- STOP_ALL сценарии,
- уважение ToS провайдеров/лимитов,
- budget gates.

Референс‑скелет (CANON, read-only) находится в `vendor/gmee_canon/`:
- `docs/idempotency_reorg_circuit_breaker.md`
- `docs/governance_legal_ethics.md`
- `ops/runbooks/*`

---
**Implementation note:** MVP offline backtest code (DuckDB/Parquet pipeline) lives **outside CANON**, only in allowed code dirs (`integration/**`, `scripts/**`, `.github/workflows/**`).
