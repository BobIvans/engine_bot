-- schemas/postgres.sql — GMEE reproducibility/audit (P0, canonical)

CREATE TABLE IF NOT EXISTS config_store (
  config_hash TEXT PRIMARY KEY,
  config_yaml TEXT NOT NULL,              -- normalized YAML
  created_by  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  parent_hash TEXT
);

CREATE TABLE IF NOT EXISTS experiment_registry (
  experiment_id TEXT PRIMARY KEY,
  config_hash   TEXT NOT NULL REFERENCES config_store(config_hash),
  env           TEXT NOT NULL,            -- sim|paper|live|canary|testnet
  seed          BIGINT NOT NULL,
  dataset_snapshot_id TEXT,
  start_ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
  end_ts        TIMESTAMPTZ,
  artifact_uri  TEXT,
  metrics_summary_json JSONB,
  bootstrap_lb  DOUBLE PRECISION,
  permutation_p DOUBLE PRECISION,
  notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_experiment_end_ts ON experiment_registry(end_ts DESC);
CREATE INDEX IF NOT EXISTS idx_experiment_config_hash ON experiment_registry(config_hash);
CREATE INDEX IF NOT EXISTS idx_experiment_env_end_ts ON experiment_registry(env, end_ts DESC);

CREATE TABLE IF NOT EXISTS promotions_audit (
  promotion_id TEXT PRIMARY KEY,
  from_config_hash TEXT,
  to_config_hash   TEXT NOT NULL REFERENCES config_store(config_hash),
  env        TEXT NOT NULL,               -- paper|live|...
  decision   TEXT NOT NULL,               -- GO|NO_GO|ROLLBACK
  decided_by TEXT,
  decided_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  reason     TEXT,
  signed_snapshot_uri TEXT,
  related_experiment_id TEXT REFERENCES experiment_registry(experiment_id)
);

CREATE INDEX IF NOT EXISTS idx_promotions_env_ts ON promotions_audit(env, decided_at DESC);
CREATE INDEX IF NOT EXISTS idx_promotions_to_hash ON promotions_audit(to_config_hash);
