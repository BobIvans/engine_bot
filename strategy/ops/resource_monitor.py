"""
Pure logic for Free-Tier Resource Monitoring.

Monitors RPC credits, API quotas, and other rate-limited resources.
Emits warnings before limits are reached to prevent unexpected bills or bans.

Status thresholds:
  - OK: < 80% utilization
  - WARNING: 80-95% utilization
  - CRITICAL: > 95% utilization or exceeded

Output format: resource_status.v1.json
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional
from enum import Enum


class ResourceStatus(Enum):
    """Resource utilization status levels."""
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


# Default thresholds
DEFAULT_WARNING_THRESHOLD = 0.80
DEFAULT_CRITICAL_THRESHOLD = 0.95


@dataclass
class ResourceDetail:
    """Detailed status for a single resource."""
    resource_name: str
    current_usage: int
    limit: int
    utilization_pct: float
    status: str
    
    def to_dict(self) -> dict:
        return {
            "resource_name": self.resource_name,
            "current_usage": self.current_usage,
            "limit": self.limit,
            "utilization_pct": round(self.utilization_pct * 100, 2),
            "status": self.status,
        }


@dataclass
class QuotaReport:
    """Complete quota status report."""
    global_status: str
    details: Dict[str, ResourceDetail] = field(default_factory=dict)
    alerts: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "version": "resource_status.v1",
            "global_status": self.global_status,
            "details": {
                name: detail.to_dict() 
                for name, detail in self.details.items()
            },
            "alerts": self.alerts,
        }


# Resource name mapping (usage key -> limit key)
RESOURCE_MAPPING = {
    "rpc_requests_today": "rpc_daily_limit",
    "rpc_requests_month": "rpc_monthly_limit",
    "api_calls_today": "api_daily_limit",
    "api_calls_month": "api_monthly_limit",
    "helius_credits": "helius_credit_limit",
    "jupiter_calls": "jupiter_rate_limit",
}


def check_quotas(
    usage: Dict[str, int],
    limits: Dict[str, Any]
) -> QuotaReport:
    """
    Check resource usage against configured limits.
    
    Args:
        usage: Current usage stats by resource name
               e.g. {"rpc_requests_today": 95000, "api_calls_month": 20000}
        limits: Limit configuration with thresholds
               e.g. {"rpc_daily_limit": 100000, "threshold_warning": 0.8}
    
    Returns:
        QuotaReport with global status and per-resource details
    """
    # Extract thresholds from config
    warning_threshold = limits.get("threshold_warning", DEFAULT_WARNING_THRESHOLD)
    critical_threshold = limits.get("threshold_critical", DEFAULT_CRITICAL_THRESHOLD)
    
    details: Dict[str, ResourceDetail] = {}
    alerts: List[str] = []
    worst_status = ResourceStatus.OK
    
    for usage_key, current_usage in usage.items():
        # Find corresponding limit key
        limit_key = RESOURCE_MAPPING.get(usage_key, f"{usage_key}_limit")
        limit_value = limits.get(limit_key)
        
        if limit_value is None:
            # No limit configured for this resource, skip
            continue
        
        # Calculate utilization
        utilization = current_usage / limit_value if limit_value > 0 else 1.0
        
        # Determine status
        if utilization >= 1.0:
            status = ResourceStatus.CRITICAL
            alerts.append(f"EXCEEDED: {usage_key} at {utilization*100:.1f}% ({current_usage}/{limit_value})")
        elif utilization >= critical_threshold:
            status = ResourceStatus.CRITICAL
            alerts.append(f"CRITICAL: {usage_key} at {utilization*100:.1f}% ({current_usage}/{limit_value})")
        elif utilization >= warning_threshold:
            status = ResourceStatus.WARNING
            alerts.append(f"WARNING: {usage_key} at {utilization*100:.1f}% ({current_usage}/{limit_value})")
        else:
            status = ResourceStatus.OK
        
        # Track worst status
        if status == ResourceStatus.CRITICAL:
            worst_status = ResourceStatus.CRITICAL
        elif status == ResourceStatus.WARNING and worst_status != ResourceStatus.CRITICAL:
            worst_status = ResourceStatus.WARNING
        
        details[usage_key] = ResourceDetail(
            resource_name=usage_key,
            current_usage=current_usage,
            limit=limit_value,
            utilization_pct=utilization,
            status=status.value,
        )
    
    return QuotaReport(
        global_status=worst_status.value,
        details=details,
        alerts=alerts,
    )


def format_output(report: QuotaReport) -> dict:
    """Format quota report for JSON output."""
    return report.to_dict()


if __name__ == "__main__":
    # Simple test
    import json
    
    usage = {
        "rpc_requests_today": 85000,
        "api_calls_month": 48000,
    }
    
    limits = {
        "rpc_daily_limit": 100000,
        "api_monthly_limit": 50000,
        "threshold_warning": 0.8,
        "threshold_critical": 0.95,
    }
    
    report = check_quotas(usage, limits)
    print(json.dumps(report.to_dict(), indent=2))
