"""
Pure logic for assembling Trade Forensics bundles.

Aggregates signals, features, and execution data into a unified forensics document.
Output format: trade_forensics.v1

This module contains NO/O operations — I only data transformation.
"""

from typing import Dict, List, Optional, Any
import json


# Keys to redact for privacy/security
REDACTED_KEYS = {
    "private_key", "secret_key", "password", "passphrase",
    "api_key", "access_token", "refresh_token",
}


def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively sanitize a dict by removing sensitive keys.
    
    Args:
        data: Input dictionary
        
    Returns:
        Sanitized dictionary with sensitive keys removed
    """
    result = {}
    
    for key, value in data.items():
        # Skip redacted keys
        if key.lower() in REDACTED_KEYS:
            continue
        
        # Recursively sanitize nested dicts
        if isinstance(value, dict):
            result[key] = sanitize_dict(value)
        # Copy other values as-is
        else:
            result[key] = value
    
    return result


def assemble_forensics(
    signal: Dict,
    features: Optional[Dict] = None,
    execution: Optional[Dict] = None,
) -> Dict:
    """
    Assemble a forensics bundle from signal, features, and execution data.
    
    Args:
        signal: Signal document (Source of Truth for intent)
        features: Feature snapshot at signal time (optional)
        execution: Execution result (optional)
        
    Returns:
        Forensics bundle dict ready for BigQuery/DuckDB export
        
    Structure:
        {
            "version": "trade_forensics.v1",
            "meta": {
                "signal_id": str,
                "timestamp": int,
                "mint": str,
            },
            "context": {
                "features": dict,  # Raw feature values
            },
            "decision": {
                "model_score": float,
                "threshold_used": float,
                "reason": str,
            },
            "outcome": {
                "fill_status": str,
                "price": float,
                "fees": float,
                "error": str,  # null if no error
            }
        }
    """
    # Sanitize inputs (remove sensitive data)
    signal_san = sanitize_dict(signal)
    features_san = sanitize_dict(features) if features else None
    execution_san = sanitize_dict(execution) if execution else None
    
    # Build meta section
    meta = {
        "signal_id": signal_san.get("signal_id", signal_san.get("id", "")),
        "timestamp": signal_san.get("timestamp", signal_san.get("created_at", 0)),
        "mint": signal_san.get("mint", signal_san.get("token_mint", "")),
    }
    
    # Build context section (features)
    context = {
        "features": features_san if features_san else {},
    }
    
    # Build decision section
    decision = {
        "model_score": signal_san.get("score", signal_san.get("model_score", 0.0)),
        "threshold_used": signal_san.get("threshold", signal_san.get("decision_threshold", 0.5)),
        "reason": signal_san.get("reason", signal_san.get("decision_reason", "")),
    }
    
    # Build outcome section
    if execution_san:
        outcome = {
            "fill_status": execution_san.get("status", execution_san.get("fill_status", "unknown")),
            "price": execution_san.get("price", execution_san.get("fill_price", 0.0)),
            "fees": execution_san.get("fees", execution_san.get("total_fees", 0.0)),
            "error": execution_san.get("error", execution_san.get("error_message", None)),
        }
    else:
        # No execution data - null fields
        outcome = {
            "fill_status": None,
            "price": None,
            "fees": None,
            "error": None,
        }
    
    # Assemble final bundle
    bundle = {
        "version": "trade_forensics.v1",
        "meta": meta,
        "context": context,
        "decision": decision,
        "outcome": outcome,
    }
    
    return bundle


def assemble_forensics_batch(
    signals: List[Dict],
    features_map: Dict[str, Dict],
    execution_map: Dict[str, Dict],
) -> List[Dict]:
    """
    Assemble forensics bundles for multiple signals.
    
    Args:
        signals: List of signal documents
        features_map: Dict mapping signal_id -> feature document
        execution_map: Dict mapping signal_id -> execution document
        
    Returns:
        List of forensics bundles
    """
    bundles = []
    
    for signal in signals:
        signal_id = signal.get("signal_id", signal.get("id", ""))
        
        # Get related data
        features = features_map.get(signal_id)
        execution = execution_map.get(signal_id)
        
        # Assemble bundle
        bundle = assemble_forensics(signal, features, execution)
        bundles.append(bundle)
    
    return bundles


if __name__ == "__main__":
    # Test with synthetic data
    signal = {
        "signal_id": "S1",
        "timestamp": 1704067200,
        "mint": "So11111111111111111111111111111111111111112",
        "score": 0.85,
        "threshold": 0.7,
        "reason": "high_score",
        "wallet": "Wallet123",
    }
    
    features = {
        "signal_id": "S1",
        "volume_24h": 1500000.0,
        "holder_count": 2500,
        "price_change_1h": 0.05,
        "smart_money_score": 0.72,
    }
    
    execution = {
        "signal_id": "S1",
        "status": "filled",
        "price": 1.25,
        "fees": 0.0015,
    }
    
    bundle = assemble_forensics(signal, features, execution)
    print(json.dumps(bundle, indent=2))
