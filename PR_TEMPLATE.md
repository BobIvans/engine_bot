# PR Title

## Goal

One sentence describing the single layer this PR adds/changes.

## Scope (files 1:1)

List every file changed/added (one per line):

- `...`

## Behavior changes

- [ ] No behavior changes on existing fixtures (golden unchanged)
- [ ] Behavior changes (describe) and golden updated

If behavior changes, specify:

- `integration/fixtures/...` updated: ...
- `integration/fixtures/expected_counts.json` updated: ...
- New/modified counters: ...

## Rails verification

Commands that must pass:

```bash
bash scripts/overlay_lint.sh
bash scripts/paper_runner_smoke.sh
```

If this PR introduces a new smoke:

```bash
bash scripts/<new_smoke>.sh
```

## Stdout/stderr contract

- When running with `--summary-json`, **stdout is exactly 1 JSON line**.
- Any human logs go to stderr.

## ClickHouse validation (if applicable)

If the PR touches writers / CH schema, include:

- Query / check used:
  - `...`

## Notes

- Anything non-obvious for reviewers.
