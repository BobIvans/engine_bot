"""integration/run_trace.py

Utilities for generating and carrying a single run_trace_id across a pipeline run.

Invariant:
- A run produces exactly one run_trace_id.
- In ClickHouse tables that have `trace_id`, we set `trace_id == run_trace_id`.
"""

from __future__ import annotations

import uuid
from typing import Optional


def new_run_trace_id(prefix: str = "paper") -> str:
    """Generate a new trace id with a stable prefix."""
    return f"{prefix}-{uuid.uuid4()}"


def get_run_trace_id(cli_value: Optional[str], prefix: str = "paper") -> str:
    """Return the provided trace id or generate a new one."""
    return cli_value if (cli_value and str(cli_value).strip()) else new_run_trace_id(prefix=prefix)
