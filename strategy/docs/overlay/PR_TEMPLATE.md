# PR Template (Overlay)

## Summary
- **Layer / PR name**:
- **Why** (1–2 sentences):

## Scope
### Files changed (1:1)
- [ ] `path/to/file`
- [ ] `path/to/file`

### Non-goals
- 

## Contracts / Rails
### Stdout / stderr
- [ ] When `--summary-json` is used, **stdout is exactly 1 JSON line**.
- [ ] Human logs go to **stderr**.

### Golden expectations
- [ ] `integration/fixtures/expected_counts.json` updated (only if behavior changed)
- [ ] If unchanged, state: “No expected_counts changes.”

### Fixtures
- [ ] Added/updated fixtures:
  - 

## Verification
### Commands
- [ ] `bash scripts/overlay_lint.sh`
- [ ] `bash scripts/paper_runner_smoke.sh`
- [ ] (if applicable) `bash scripts/features_smoke.sh`
- [ ] (if applicable) any PR-specific smoke script(s)

### What changed in counters (if any)
- `rejected_by_gates`:
- `filtered_out`:
- `passed`:
- (new) `...`:

## Notes
- 
