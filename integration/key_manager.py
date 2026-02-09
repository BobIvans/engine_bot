"""integration/key_manager.py

PR-G.3 Live Config Gate & Key Management.

Safe key loading from environment variables:
- Reads SOLANA_PRIVATE_KEY from environment
- Supports Base58 string and JSON array formats
- Raises RuntimeError if key is missing or invalid
"""

from __future__ import annotations

import json
import os
from typing import Optional, Union


class KeyLoadError(Exception):
    """Raised when key loading fails."""
    pass


def load_solana_private_key() -> bytes:
    """Load Solana private key from environment variable.

    Reads SOLANA_PRIVATE_KEY from os.environ and parses it:
    - Base58 encoded string (e.g., "4f3a...")
    - JSON array of bytes (e.g., "[12, 45, 78, ...]")

    Returns:
        Raw key bytes.

    Raises:
        KeyLoadError: If variable is missing or key is invalid.
    """
    key_str = os.environ.get("SOLANA_PRIVATE_KEY", "")

    if not key_str:
        raise KeyLoadError("SOLANA_PRIVATE_KEY environment variable is not set")

    key_str = key_str.strip()

    # Try JSON array format first
    if key_str.startswith("["):
        try:
            key_array = json.loads(key_str)
            if isinstance(key_array, list) and all(isinstance(x, int) for x in key_array):
                return bytes(key_array)
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Try Base58 format
    try:
        # Base58 decoding
        import base58
        key_bytes = base58.b58decode(key_str)
        if len(key_bytes) == 64:  # Ed25519 secret key is 64 bytes
            return key_bytes
    except Exception:
        pass

    raise KeyLoadError(
        f"Invalid SOLANA_PRIVATE_KEY format. Expected Base58 string or JSON array. "
        f"Got: {key_str[:20]}..." if len(key_str) > 20 else f"Got: {key_str}"
    )


def load_signing_key() -> bytes:
    """Alias for load_solana_private_key for compatibility.

    Returns:
        Raw key bytes.

    Raises:
        KeyLoadError: If variable is missing or key is invalid.
    """
    return load_solana_private_key()


def validate_key_exists() -> bool:
    """Check if SOLANA_PRIVATE_KEY is set and appears valid.

    Returns:
        True if key is set and parseable, False otherwise.
    """
    try:
        load_solana_private_key()
        return True
    except KeyLoadError:
        return False
