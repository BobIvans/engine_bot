# BACKTEST_EVAL (walk-forward)

Цель: проверить, что стратегия **работает на будущих отрезках**, а не только на обучении.

## Split: walk-forward
- Данные: time-series, без перемешивания по времени.
- Схема:
  1) Train: окно N дней (например 60–90)
  2) Test: следующий отрезок (например 7–14)
  3) Сдвиг окна вперёд, повторить K раз
- Параметры: `model.training.timeseries_splits`, `lookback_days` в `params_base.yaml`.

## Метрики (минимум)
- Fill-rate (сим) и доля “нулевых филлов”
- Winrate, avg/median PnL per trade
- Max drawdown (общий + по режимам U/S/M/L)
- Tail-risk: worst 1% outcomes
- Per-wallet/per-token концентрация риска

## Критерий “можно двигаться дальше”
- Выполнены acceptance targets из `backtest.acceptance_targets`:
  - `min_fill_rate`
  - `max_drawdown_pct`
- Нет “одного кошелька/токена”, который делает >X% профита (концентрация).

## Важно
Бэктест должен использовать **те же правила TP/SL/TTL + slippage/latency модель**, что и paper-runner.
