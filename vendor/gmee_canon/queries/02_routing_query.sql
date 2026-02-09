/* queries/02_routing_query.sql
Input:  {chain:String}
Output: latest per-arm snapshot for routing (epsilon/priors/breaker)
*/
SELECT
  chain, rpc_arm, snapshot_ts,
  q90_latency_ms, ewma_mean_ms, ewma_var_ms2,
  epsilon_ms, a_success, b_success,
  degraded, cooldown_until, reason, config_hash
FROM latency_arm_state
WHERE chain = {chain:String}
ORDER BY snapshot_ts DESC
LIMIT 1 BY rpc_arm;
