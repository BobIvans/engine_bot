/* queries/01_profile_query.sql
Input:  {chain:String}, {wallet:String}
Output: wallet_profile window summary (30d anchored to max(day))
*/
SELECT
  chain,
  wallet AS traced_wallet,
  trades_n,
  win_rate,
  q10_hold_sec,
  q25_hold_sec,
  q40_hold_sec,
  median_hold_sec,
  avg_hold_sec,
  hold_var_sec2,
  avg_roi,
  roi_var,
  now64(3) AS profile_ts
FROM wallet_profile_30d
WHERE chain = {chain:String} AND wallet = {wallet:String}
LIMIT 1;
