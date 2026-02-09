# Backlog (Iteration-2): Free‑First Copy‑Trading Infrastructure

**Next up (Variant A):** PR-4A.3 Mode registry + metrics-by-mode
(`strategy/docs/overlay/PR_MODES.md`, tracked in `strategy/docs/overlay/SPRINTS.md`).

This repo already contains **verified rails** (Iteration‑1):
- CANON ClickHouse gates + oracle: `./scripts/smoke.sh`
- Strict CANON config mapping: `python3 -m integration.config_mapper`
- One‑shot CANON SQL04 demo: `python3 -m integration.run_exit_plan --seed-golden`
- Paper runner rails: `python3 -m integration.paper_pipeline ...`
  - `run_trace_id`
  - queryable rejects: `forensics_events(kind='trade_reject')`

Iteration‑2 turns the strategy spec into **agent-executable tasks** and adds the missing contracts
(token snapshots, wallet profiles, risk, sim, features) **without breaking rails**.

## Where to start
- Human overview: `strategy/docs/overlay/IMPLEMENTATION_START_HERE.md`
- What agents must achieve (single source of truth): `strategy/docs/overlay/CODING_AGENT_TARGETS.md`
- Exact implementation backlog: `strategy/docs/overlay/NEXT_STEPS_STRATEGY_BACKLOG.md`
- PR checklist (Definition of Done): `strategy/docs/overlay/PR_DOD_CHECKLIST.md`

## Two-sprint plan (recommended)
If you want a clean handoff to coding agents, run exactly:

- **Sprint-1 (4 tasks):** repo hygiene + strategy schemas + ingestion normalization + `paper_pipeline --source`.
- **Sprint-2 (4 tasks):** SignalEngine v1 + Risk stage + Simulator wiring + Features/model-off interface.

The authoritative per-task DoD and file-level instructions live in:
`strategy/docs/overlay/CODING_AGENT_TARGETS.md`.

## Epics (Iteration‑2)
- Epic A — Data-track contracts (fixtures first)
- Epic B — Risk + execution simulator (paper/sim, no live keys)
- Epic C — Features + ML interfaces (model-off first)

> Each PR must keep `./scripts/smoke.sh` green and must not modify CANON (`vendor/gmee_canon/**`).
