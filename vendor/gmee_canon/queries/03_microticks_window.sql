/* queries/03_microticks_window.sql
Input:  {chain:String}, {trade_id:UUID}, {window_s:UInt16}
Output: post-entry microticks window
*/
SELECT
  trade_id, chain, t_offset_s, ts, price_usd, liquidity_usd, volume_usd
FROM microticks_1s
WHERE chain = {chain:String}
  AND trade_id = {trade_id:UUID}
  AND t_offset_s <= {window_s:UInt16}
ORDER BY t_offset_s ASC;
