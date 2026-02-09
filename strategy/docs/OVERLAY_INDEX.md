# Overlay index (strategy pack)

Эта папка содержит **overlay-only** документы, импортированные из strategy-pack ZIP. Overlay используется **только как документация/гайд**, не как код.

## Источник истины и правила (критично)

- **CANON ONLY** = `vendor/gmee_canon/**` (v23) — **read-only**.
- **STRATEGY (docs-only)** = `strategy/docs/**` (включая `strategy/docs/overlay/**`).
- **CODE** (единственные места, где разрешены изменения) = `integration/**`, `scripts/**`, `.github/workflows/**`, `policy/**`, `AGENT_RULES.md`.
- **Запрещено навсегда:** любые `.sql`, `schemas/`, `configs/queries.yaml` **вне** `vendor/gmee_canon/**`, LEGACY_PATH: любые упоминания `golden-engine-exit` (legacy), любой “второй канон”.

## Главный документ стратегии

Начинать чтение и обсуждение стратегии отсюда:

- `strategy/docs/overlay/SOLANA_COPY_SCALPING_SPEC_v0_2.md` — **Strategy Spec (Free‑First) v0.2** (главный source doc)
- `strategy/docs/overlay/ENGINEERING_PLAN_MVP_V0.md` — **Engineering plan (repo structure + module map + MVP v0)**

Связанные документы:
- `strategy/docs/overlay/STRATEGY_TO_UV_MAPPING.md`
- `strategy/docs/overlay/GMEE_INTEGRATION_NOTES.md`
- `strategy/docs/overlay/RESOURCES_AND_APPS.yaml`
- `strategy/docs/overlay/strategy_docs/strategy_manifest.json`
- Overlay PR/план: `strategy/docs/overlay/strategy_overlay/`

## Agent‑friendly rails (универсально для любого кодинг‑агента)

### Почему `allowed_edit_globs` важен
Любой кодинг‑агент (или человек с автогенерацией) часто путается в границах ответственности.  
`allowed_edit_globs` делает границы **структурными**: агент читает policy → понимает, где можно менять → работает.

### Машиночитаемая политика
- `policy/agent_policy.yaml` — единый контракт:
  - `allowed_edit_globs`: где разрешены изменения
  - запреты на SQL/DDL/registry вне CANON
  - LEGACY_PATH: запрет legacy‑строк (`golden-engine-exit`) в overlay
  - DoD/CI‑контракт

### Локальный pre‑commit guard (до PR)
- `scripts/pre_commit_agent_guard.sh` — валит commit, если staged‑файлы выходят за `allowed_edit_globs`.

Установка (локально, один раз):
```bash
chmod +x scripts/pre_commit_agent_guard.sh
ln -s ../../scripts/pre_commit_agent_guard.sh .git/hooks/pre-commit
```

### Минимальные правила для агента (перед каждым PR)
- `AGENT_RULES.md` — короткий чек‑лист без привязки к названию агента.

## Как использовать overlay правильно

- Используйте overlay‑доки как руководство для Solana copy‑scalping (data map, контракты, гейты, runbook).
- Реализация должна соответствовать CANON интерфейсам:
  - `vendor/gmee_canon/configs/queries.yaml` (registry имен параметров)
  - `vendor/gmee_canon/queries/04_glue_select.sql` (формат вывода, параметры 1:1)
  - golden seed + oracle gates + canary/smoke (через `scripts/iteration1.sh`)

**Если агент сомневается — перечитай `AGENT_RULES.md` и `policy/agent_policy.yaml` перед любым изменением.**


## Start here

- `strategy/docs/overlay/SOLANA_COPY_SCALPING_SPEC_v0_2.md` — strategy spec (Free-first v0.2)
- `strategy/docs/overlay/ENGINEERING_PLAN_MVP_V0.md` — repo layout + MVP plan (0$)
- `strategy/docs/overlay/IMPLEMENTATION_START_HERE.md` — first PR (stubs + commands)
- `strategy/docs/overlay/STRATEGY_COVERAGE_CHECKLIST.md` — what’s done vs planned


---

If an agent is uncertain or confused — re-read `AGENT_RULES.md` and `policy/agent_policy.yaml` before making any change.


## Next iteration backlog

- [P1 — run_trace_id + trade_reject events](overlay/P1_TRACE_AND_REJECTS_BACKLOG.md)

## Verification
- overlay/CLICKHOUSE_TRACE_VALIDATION.md

## Next iteration backlog
- overlay/NEXT_STEPS_STRATEGY_BACKLOG.md
- overlay/CODING_AGENT_TARGETS.md
