"""
ingestion/rpc package

RPC batching, caching, and failover layer for Free-Tier optimization.
"""
from .client import SmartRpcClient
from .batcher import RpcBatcher, BatchItem
from .cache import RpcCache
from .monitor import HealthMonitor, HealthScore
from .failover import FailoverManager, EndpointConfig

__all__ = [
    'SmartRpcClient',
    'RpcBatcher',
    'BatchItem',
    'RpcCache',
    'HealthMonitor',
    'HealthScore',
    'FailoverManager',
    'EndpointConfig',
]
