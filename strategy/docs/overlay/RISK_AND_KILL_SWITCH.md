# RISK_AND_KILL_SWITCH (hard gate)

Этот документ — не “совет”, а **обязательные правила запуска**.

## Hard limits (from config)
- max position size: `risk.sizing.max_pos_pct`
- max daily loss: `risk.limits.max_daily_loss_pct`
- max total drawdown: `risk.limits.max_drawdown_total_pct`

## Kill-switch (обязателен)
Срабатывает если:
- достигнут `max_drawdown_total_pct` **или**
- дневной loss превысил `max_daily_loss_pct`

Действие:
- стоп новых входов
- закрыть/заморозить активные позиции (в paper/sim — пометить как принудительное закрытие)
- записать `forensics_events(kind="run_meta" or "error")`

## Cooldown (обязателен)
- после N подряд убытков (`cooldown.trigger_after_consecutive_losses`)
- пауза `cooldown_minutes`
- на паузе: `force_base_only=true` + поднять `p_model_min` на `raise_p_model_min_by`

## Live запрет
Live режим разрешён только после DoD:
- `scripts/overlay_lint.sh` зелёный
- `scripts/iteration1.sh` зелёный
- `scripts/p1_smoke.sh` зелёный
- в таблице `forensics_events` видны `allowlist_version` и `config_version`
