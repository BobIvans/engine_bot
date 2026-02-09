#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SOT="strategy/docs/overlay/pr_labels.v1.json"
DOC="strategy/docs/overlay/PR_LABELS.md"

if [[ ! -f "$SOT" ]]; then
  echo "ERROR: missing SoT file: $SOT" >&2
  exit 1
fi
if [[ ! -f "$DOC" ]]; then
  echo "ERROR: missing doc file: $DOC" >&2
  exit 1
fi

python3 - "$SOT" "$DOC" <<'PYCODE'
import json, re, sys
from collections import Counter
from pathlib import Path

sot_path = Path(sys.argv[1])
doc_path = Path(sys.argv[2])

try:
    sot = json.loads(sot_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"ERROR: failed to parse SoT JSON: {e}", file=sys.stderr)
    raise SystemExit(1)

labels = sot.get("labels", None)
if not isinstance(labels, list) or not labels:
    print("ERROR: SoT labels must be a non-empty list", file=sys.stderr)
    raise SystemExit(1)

# Basic label format: no spaces, machine-readable
bad = [x for x in labels if (not isinstance(x, str)) or (" " in x) or (":" not in x)]
if bad:
    print(f"ERROR: invalid label(s) in SoT: {bad}", file=sys.stderr)
    raise SystemExit(1)

# Duplicates
cnt = Counter(labels)
dups = sorted([k for k,v in cnt.items() if v > 1])
if dups:
    for x in dups:
        print(f"ERROR: Duplicate label in SoT: {x}", file=sys.stderr)
    raise SystemExit(1)

if "required_groups" not in sot:
    print("ERROR: SoT missing required_groups", file=sys.stderr)
    raise SystemExit(1)
required_groups = sot.get("required_groups")
if not isinstance(required_groups, list):
    print("ERROR: SoT required_groups must be a list", file=sys.stderr)
    raise SystemExit(1)

# Extract labels mentioned in PR_LABELS.md doc
try:
    doc = doc_path.read_text(encoding="utf-8")
except Exception as e:
    print(f"ERROR: failed to read PR_LABELS.md: {e}", file=sys.stderr)
    raise SystemExit(1)

# Prefer backticked labels like `agent_scope:tiny`
mentioned = set(re.findall(r"`([a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]+)`", doc))
sot_set = set(labels)
missing_in_doc = sorted(sot_set - mentioned)
extra_in_doc = sorted(mentioned - sot_set)
if missing_in_doc:
    print("ERROR: labels in SoT missing in PR_LABELS.md:", file=sys.stderr)
    for x in missing_in_doc:
        print(f"  - {x}", file=sys.stderr)
    raise SystemExit(1)
if extra_in_doc:
    print("ERROR: labels mentioned in PR_LABELS.md but not in SoT:", file=sys.stderr)
    for x in extra_in_doc:
        print(f"  - {x}", file=sys.stderr)
    raise SystemExit(1)

# Validate each required_group object
prefixes = []
for i, g in enumerate(required_groups):
    if not isinstance(g, dict):
        print(f"ERROR: required_groups[{i}] must be an object", file=sys.stderr)
        raise SystemExit(1)
    if "prefix" not in g:
        print(f"ERROR: required_groups[{i}] missing prefix", file=sys.stderr)
        raise SystemExit(1)
    pref = g.get("prefix")
    if not isinstance(pref, str):
        print(f"ERROR: required_groups[{i}].prefix must be a string", file=sys.stderr)
        raise SystemExit(1)
    if not pref.strip():
        print(f"ERROR: required_groups[{i}].prefix must be non-empty", file=sys.stderr)
        raise SystemExit(1)
    prefixes.append(pref)
    # Prefix must match at least one label
    matches = [lbl for lbl in labels if isinstance(lbl, str) and lbl.startswith(pref)]
    if not matches:
        print(f"ERROR: required_groups[{i}] prefix has no matching labels: {pref}", file=sys.stderr)
        raise SystemExit(1)

# Detect ambiguous overlapping prefixes (optional, but should pass on current SoT)
# Overlap means one prefix is a strict prefix of another.
sorted_prefixes = sorted(set(prefixes), key=len)
for a in sorted_prefixes:
    for b in sorted_prefixes:
        if a == b:
            continue
        if b.startswith(a):
            # strict prefix overlap
            print(f"ERROR: required_groups prefixes overlap: {a} vs {b}", file=sys.stderr)
            raise SystemExit(1)

print("[pr_labels_lint] OK ✅", file=sys.stderr)
PYCODE
