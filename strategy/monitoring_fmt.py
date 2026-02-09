# strategy/monitoring_fmt.py
# Pure logic for InfluxDB Line Protocol formatting and JSON flattening.
# No I/O side effects.

import re
from typing import Any, Dict, List, Optional


def escape_tag(value: str) -> str:
    """
    Escape a tag value for InfluxDB Line Protocol.
    
    Escapes: commas, equals signs, and spaces.
    
    Args:
        value: The tag value to escape.
        
    Returns:
        Escaped string suitable for tag values.
    """
    if not isinstance(value, str):
        value = str(value)
    # Escape commas, equals signs, and spaces
    value = value.replace(",", "\\,")
    value = value.replace("=", "\\=")
    value = value.replace(" ", "\\ ")
    return value


def escape_field_key(value: str) -> str:
    """
    Escape a field key for InfluxDB Line Protocol.
    
    Escapes: commas, equals signs, and spaces.
    
    Args:
        value: The field key to escape.
        
    Returns:
        Escaped string suitable for field keys.
    """
    if not isinstance(value, str):
        value = str(value)
    value = value.replace(",", "\\,")
    value = value.replace("=", "\\=")
    value = value.replace(" ", "\\ ")
    return value


def escape_string_field(value: str) -> str:
    """
    Escape a string field value for InfluxDB Line Protocol.
    
    Wraps in double quotes and escapes existing double quotes and backslashes.
    
    Args:
        value: The string field value to escape.
        
    Returns:
        Escaped string wrapped in double quotes.
    """
    if not isinstance(value, str):
        value = str(value)
    # Escape backslashes first, then double quotes
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    return f'"{value}"'


def format_field_value(value: Any) -> str:
    """
    Format a field value for InfluxDB Line Protocol.
    
    Handles integers, floats, booleans, and strings.
    
    Args:
        value: The field value to format.
        
    Returns:
        Formatted string suitable for field values.
    """
    if value is None:
        return ""
    
    if isinstance(value, bool):
        return "true" if value else "false"
    
    if isinstance(value, int):
        return f"{value}i"
    
    if isinstance(value, float):
        # Handle NaN and infinity
        if value != value:  # NaN check
            return "NaN"
        if value == float('inf'):
            return "Inf"
        if value == float('-inf'):
            return "-Inf"
        # Format without unnecessary trailing zeros
        return f"{value}".rstrip('0').rstrip('.') if '.' in f"{value}" else f"{value}"
    
    if isinstance(value, str):
        return escape_string_field(value)
    
    return escape_string_field(str(value))


def flatten_dict(data: Dict, parent_key: str = "", sep: str = "_") -> Dict[str, Any]:
    """
    Flatten a nested dictionary.
    
    Nested keys are combined with separator (default: underscore).
    Example: {"roi": {"p50": 12.5}} -> {"roi_p50": 12.5}
    
    Args:
        data: The dictionary to flatten.
        parent_key: The prefix to use for nested keys.
        sep: The separator to use between nested keys.
        
    Returns:
        Flattened dictionary.
    """
    items = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else key
        if isinstance(value, dict):
            items.update(flatten_dict(value, new_key, sep))
        else:
            items[new_key] = value
    return items


def flatten_metrics(data: Dict, prefix: str = "") -> Dict[str, Any]:
    """
    Flatten nested JSON metrics for flat field sets.
    
    Args:
        data: The metrics dictionary to flatten.
        prefix: Optional prefix for all keys.
        
    Returns:
        Flattened dictionary suitable for InfluxDB fields.
    """
    flattened = flatten_dict(data, prefix, "_")
    return flattened


def to_influx_line(
    measurement: str,
    tags: Dict[str, str],
    fields: Dict[str, Any],
    timestamp_ns: Optional[int] = None,
) -> str:
    """
    Construct an InfluxDB Line Protocol line.
    
    Format: measurement,tag_set field_set timestamp
    
    Args:
        measurement: The measurement name.
        tags: Dictionary of tag key-value pairs.
        fields: Dictionary of field key-value pairs (at least one required).
        timestamp_ns: Optional timestamp in nanoseconds.
        
    Returns:
        Formatted InfluxDB Line Protocol string.
    """
    if not measurement:
        raise ValueError("Measurement name is required")
    
    if not fields:
        raise ValueError("At least one field is required")
    
    # Build measurement and tag set
    line = measurement
    
    if tags:
        tag_parts = []
        for key, value in sorted(tags.items()):
            if value is None:
                continue
            escaped_key = escape_field_key(str(key))
            escaped_value = escape_tag(str(value))
            tag_parts.append(f"{escaped_key}={escaped_value}")
        if tag_parts:
            line += "," + ",".join(tag_parts)
    
    # Build field set
    field_parts = []
    for key, value in sorted(fields.items()):
        if value is None:
            continue
        escaped_key = escape_field_key(str(key))
        formatted_value = format_field_value(value)
        if formatted_value:
            field_parts.append(f"{escaped_key}={formatted_value}")
    
    if not field_parts:
        raise ValueError("At least one non-null field is required")
    
    line += " " + " ".join(field_parts)
    
    # Add timestamp if provided
    if timestamp_ns is not None:
        line += f" {timestamp_ns}"
    
    return line


def convert_metrics_to_influx(
    data: Dict,
    measurement: str = "strategy_metrics",
    tag_keys: Optional[List[str]] = None,
    timestamp_ns: Optional[int] = None,
) -> str:
    """
    Convert a metrics dictionary to InfluxDB Line Protocol.
    
    Top-level string keys are treated as tags.
    Nested/numeric keys become fields.
    
    Args:
        data: The metrics dictionary.
        measurement: The measurement name.
        tag_keys: List of keys to treat as tags (if None, strings become tags).
        timestamp_ns: Optional timestamp in nanoseconds.
        
    Returns:
        InfluxDB Line Protocol string.
    """
    tags = {}
    fields = {}
    
    for key, value in data.items():
        if tag_keys is not None:
            if key in tag_keys:
                if isinstance(value, str):
                    tags[key] = value
                else:
                    tags[key] = str(value)
            else:
                fields[key] = value
        else:
            if isinstance(value, str):
                tags[key] = value
            else:
                fields[key] = value
    
    # Flatten any nested structures in fields
    if fields:
        fields = flatten_metrics(fields)
    
    return to_influx_line(measurement, tags, fields, timestamp_ns)


def convert_signals_to_influx(
    signals: List[Dict],
    measurement: str = "signals",
    timestamp_key: str = "ts",
) -> List[str]:
    """
    Convert a list of signal dictionaries to InfluxDB Line Protocol.
    
    signal_id and symbol are used as tags.
    score, p_model, expected_val become fields.
    
    Args:
        signals: List of signal dictionaries.
        measurement: The measurement name.
        timestamp_key: Key to use for timestamp extraction.
        
    Returns:
        List of InfluxDB Line Protocol strings.
    """
    lines = []
    
    for signal in signals:
        tags = {}
        fields = {}
        
        # Extract known tag fields
        if "signal_id" in signal:
            tags["signal_id"] = str(signal["signal_id"])
        if "symbol" in signal:
            tags["symbol"] = str(signal["symbol"])
        
        # Extract all other fields as fields
        for key, value in signal.items():
            if key in ("signal_id", "symbol", timestamp_key):
                continue
            fields[key] = value
        
        # Get timestamp
        timestamp_ns = None
        if timestamp_key in signal:
            ts_val = signal[timestamp_key]
            if isinstance(ts_val, (int, float)):
                timestamp_ns = int(ts_val)
            elif isinstance(ts_val, str):
                # Parse ISO timestamp
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                    timestamp_ns = int(dt.timestamp() * 1e9)
                except ValueError:
                    pass
        
        # Flatten any nested structures in fields
        if fields:
            fields = flatten_metrics(fields)
        
        # Build line (only if we have fields)
        if fields:
            line = to_influx_line(measurement, tags, fields, timestamp_ns)
            lines.append(line)
    
    return lines


def batch_to_influx_lines(
    lines: List[str],
) -> str:
    """
    Combine multiple lines into a batch output.
    
    Args:
        lines: List of InfluxDB Line Protocol strings.
        
    Returns:
        All lines joined with newlines.
    """
    return "\n".join(lines)


# Alias for backwards compatibility with influx_line_protocol naming
export_to_influx = to_influx_line
influx_line_protocol = to_influx_line
