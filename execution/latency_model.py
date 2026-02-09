"""execution/latency_model.py

Deterministic latency sampler.

We avoid global randomness so simulation results are reproducible when we seed with run_trace_id.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LogNormalLatencyParams:
    mean_ms: float
    sigma: float
    clamp_min_ms: int
    clamp_max_ms: int


def sample_lognormal_ms(params: LogNormalLatencyParams, seed: Optional[int]) -> int:
    r = random.Random(seed)
    mu = math.log(max(params.mean_ms, 1.0))
    x = r.lognormvariate(mu, params.sigma)
    ms = int(x)
    if ms < params.clamp_min_ms:
        return params.clamp_min_ms
    if ms > params.clamp_max_ms:
        return params.clamp_max_ms
    return ms
