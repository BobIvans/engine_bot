/* queries/04_glue_select.sql — GMEE exit plan "glue" (P0, canonical)

This is a DEBUG/ORACLE query: it computes exit plan fields from:
- trades (entry info),
- wallet_profile_30d (hold quantiles),
- latency_arm_state (epsilon),
- microticks_1s (aggr triggers).

Variant A rule: **all thresholds are parameterized** to avoid YAML↔SQL drift.

Inputs:
  {chain:String}
  {trade_id:UUID}
  {epsilon_pad_ms:UInt32}
  {epsilon_min_ms:UInt32}
  {epsilon_max_ms:UInt32}
  {margin_mult:Float32}
  {min_hold_sec:UInt32}
  {max_hold_sec:UInt32}
  {mode_u_max_sec:UInt32}
  {mode_s_max_sec:UInt32}
  {mode_m_max_sec:UInt32}
  {microticks_window_s:UInt16}
  {aggr_u_window_s:UInt16} {aggr_u_pct:Float32}
  {aggr_s_window_s:UInt16} {aggr_s_pct:Float32}
  {aggr_m_window_s:UInt16} {aggr_m_pct:Float32}
  {aggr_l_window_s:UInt16} {aggr_l_pct:Float32}

Output (stable columns for oracle test):
  trade_id, mode, planned_hold_sec, epsilon_ms, planned_exit_ts, aggr_flag
*/
WITH
t AS (
  SELECT trade_id, chain, traced_wallet, buy_time, buy_price_usd
  FROM trades
  WHERE chain = {chain:String} AND trade_id = {trade_id:UUID}
  LIMIT 1
),
ref AS (
  /* Deterministic reference ts (avoid now()/now64() in oracle query) */
  SELECT ifNull(
    (SELECT buy_time FROM t),
    toDateTime64('1970-01-01 00:00:00', 3, 'UTC')
  ) AS ref_ts
),
p AS (
  SELECT *
  FROM wallet_profile_30d
  WHERE chain = {chain:String} AND wallet = (SELECT traced_wallet FROM t)
  LIMIT 1
),
r AS (
  /* Conservative ε: choose best non-degraded ε if exists else any ε, then pad + clamp */
  SELECT least(
           greatest(
             toUInt32(
               ifNull(
                 minIf(
                   epsilon_ms,
                   degraded = 0
                   AND (cooldown_until IS NULL OR cooldown_until <= (SELECT ref_ts FROM ref))
                 ),
                 ifNull(min(epsilon_ms), 0)
               ) + {epsilon_pad_ms:UInt32}
             ),
             {epsilon_min_ms:UInt32}
           ),
           {epsilon_max_ms:UInt32}
         ) AS epsilon_ms
  FROM (
    SELECT *
    FROM latency_arm_state
    WHERE chain = {chain:String}
    ORDER BY snapshot_ts DESC
    LIMIT 1 BY rpc_arm
  )
),
m AS (
  /* microticks summary for aggr triggers (max price within mode window vs entry price) */
  SELECT
    trade_id,
    argMin(price_usd, t_offset_s) AS entry_price_usd,
    maxIf(price_usd, t_offset_s <= {aggr_u_window_s:UInt16}) AS max_u_price,
    maxIf(price_usd, t_offset_s <= {aggr_s_window_s:UInt16}) AS max_s_price,
    maxIf(price_usd, t_offset_s <= {aggr_m_window_s:UInt16}) AS max_m_price,
    maxIf(price_usd, t_offset_s <= {aggr_l_window_s:UInt16}) AS max_l_price
  FROM microticks_1s
  WHERE chain = {chain:String}
    AND trade_id = {trade_id:UUID}
    AND t_offset_s BETWEEN 0 AND least(
      {microticks_window_s:UInt16},
      greatest(
        {aggr_u_window_s:UInt16},
        {aggr_s_window_s:UInt16},
        {aggr_m_window_s:UInt16},
        {aggr_l_window_s:UInt16}
      )
    )
  GROUP BY trade_id
),
calc AS (
  SELECT
    /* mode from avg_hold_sec; if missing profile -> L */
    multiIf(
      isNull(p.avg_hold_sec), 'L',
      p.avg_hold_sec <= {mode_u_max_sec:UInt32}, 'U',
      p.avg_hold_sec <= {mode_s_max_sec:UInt32}, 'S',
      p.avg_hold_sec <= {mode_m_max_sec:UInt32}, 'M',
      'L'
    ) AS mode,
    /* base quantile mapping is a CONTRACT (asserted in CI) */
    multiIf(
      mode = 'U', toFloat64(ifNull(p.q10_hold_sec, 0)),
      mode = 'S', toFloat64(ifNull(p.q25_hold_sec, 0)),
      mode = 'M', toFloat64(ifNull(p.q40_hold_sec, 0)),
      toFloat64(ifNull(p.median_hold_sec, 0))
    ) AS base_hold_sec
)
SELECT
  t.trade_id AS trade_id,
  calc.mode AS mode,
  least(
    greatest(
      toUInt32(round(calc.base_hold_sec * {margin_mult:Float32})),
      {min_hold_sec:UInt32}
    ),
    {max_hold_sec:UInt32}
  ) AS planned_hold_sec,
  r.epsilon_ms AS epsilon_ms,
  /* planned_exit_ts = buy_time + planned_hold_sec - epsilon_ms */
  addMilliseconds(addSeconds(t.buy_time, planned_hold_sec), -toInt32(epsilon_ms)) AS planned_exit_ts,
  toUInt8(
    (calc.mode = 'U' AND ifNull((m.max_u_price / nullIf(m.entry_price_usd, 0)) - 1, 0) >= {aggr_u_pct:Float32}) OR
    (calc.mode = 'S' AND ifNull((m.max_s_price / nullIf(m.entry_price_usd, 0)) - 1, 0) >= {aggr_s_pct:Float32}) OR
    (calc.mode = 'M' AND ifNull((m.max_m_price / nullIf(m.entry_price_usd, 0)) - 1, 0) >= {aggr_m_pct:Float32}) OR
    (calc.mode = 'L' AND ifNull((m.max_l_price / nullIf(m.entry_price_usd, 0)) - 1, 0) >= {aggr_l_pct:Float32})
  ) AS aggr_flag
FROM t
LEFT JOIN p ON 1
LEFT JOIN r ON 1
LEFT JOIN m ON m.trade_id = t.trade_id
LEFT JOIN calc ON 1;
