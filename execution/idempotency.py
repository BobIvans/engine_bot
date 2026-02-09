"""execution/idempotency.py

PR-G.2 Idempotency Layer.

Idempotency manager that prevents double-execution of trades:
- Uses deterministic hash-based keys
- File-backed JSONL persistence for crash recovery
- Atomic lock acquisition with file renaming
- TTL-based automatic cleanup
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


class IdempotencyManager:
    """Manages idempotency locks for trade execution.

    Generates deterministic keys from signals and maintains a persistent
    lock state using a file-backed JSONL format.

    Design:
    - Keys are SHA256 hashes of (wallet + mint + side + bucketed_ts)
    - Lock acquisition is atomic via temporary file rename pattern
    - State persists across process restarts
    """

    def __init__(
        self,
        *,
        state_file: str = "/tmp/idempotency_state.jsonl",
        ttl_sec: int = 3600,
    ):
        """Initialize the idempotency manager.

        Args:
            state_file: Path to the JSONL file for persistence.
            ttl_sec: Time-to-live for locks in seconds.
        """
        self.state_file = Path(state_file)
        self.ttl_sec = ttl_sec
        self._ensure_state_file()

    def _ensure_state_file(self) -> None:
        """Create state file if it doesn't exist."""
        if not self.state_file.exists():
            self.state_file.write_text("")

    def _bucketed_timestamp(self, bucket_sec: int = 60) -> int:
        """Get current time bucketed to reduce key variance."""
        return int(time.time() // bucket_sec)

    def generate_key(self, *, signal: Dict[str, Any]) -> str:
        """Generate a deterministic idempotency key from a signal.

        The key is based on:
        - wallet address
        - token mint
        - trade side (buy/sell)
        - bucketed timestamp (1-minute buckets)

        Args:
            signal: The trade signal dictionary.

        Returns:
            SHA256 hash as a hex string.
        """
        wallet = signal.get("wallet", "")
        mint = signal.get("mint", "")
        side = signal.get("side", "")
        bucket = self._bucketed_timestamp()

        key_input = f"{wallet}:{mint}:{side}:{bucket}"
        return hashlib.sha256(key_input.encode()).hexdigest()

    def acquire_lock(self, *, key: str) -> bool:
        """Acquire an idempotency lock for the given key.

        Uses atomic file operations:
        1. Read existing locks
        2. Check if key exists and is not expired
        3. Write new lock to temp file
        4. Atomically rename to state file

        Args:
            key: The idempotency key.

        Returns:
            True if lock was acquired (new key), False if already exists.
        """
        now = time.time()

        # Read current state
        locks = self._read_locks()

        # Check if key exists and is not expired
        if key in locks:
            expiry = locks[key].get("expiry", 0)
            if now < expiry:
                # Lock exists and is still valid
                return False
            # Lock has expired, will be overwritten

        # Create new lock entry
        locks[key] = {
            "acquired_at": now,
            "expiry": now + self.ttl_sec,
        }

        # Atomic write via temp file
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                for k, v in locks.items():
                    f.write(json.dumps({"key": k, **v}) + "\n")
            temp_file.rename(self.state_file)
        except OSError:
            # Cleanup on failure
            if temp_file.exists():
                temp_file.unlink()
            return False

        return True

    def release_lock(self, *, key: str) -> bool:
        """Release an idempotency lock.

        Args:
            key: The idempotency key.

        Returns:
            True if lock was released, False if key didn't exist.
        """
        locks = self._read_locks()

        if key not in locks:
            return False

        del locks[key]

        # Atomic write
        temp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(temp_file, "w") as f:
                for k, v in locks.items():
                    f.write(json.dumps({"key": k, **v}) + "\n")
            temp_file.rename(self.state_file)
        except OSError:
            if temp_file.exists():
                temp_file.unlink()
            return False

        return True

    def _read_locks(self) -> Dict[str, Dict[str, Any]]:
        """Read all locks from the state file.

        Returns:
            Dict mapping keys to lock metadata.
        """
        locks: Dict[str, Dict[str, Any]] = {}

        if not self.state_file.exists():
            return locks

        try:
            with open(self.state_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        locks[entry["key"]] = {
                            "acquired_at": entry.get("acquired_at", 0),
                            "expiry": entry.get("expiry", 0),
                        }
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed lines
                        continue
        except OSError:
            pass

        return locks

    def prune(self) -> int:
        """Remove expired locks from the state file.

        Returns:
            Number of locks removed.
        """
        locks = self._read_locks()
        now = time.time()

        # Filter out expired locks
        active_locks = {k: v for k, v in locks.items() if v.get("expiry", 0) > now}

        removed = len(locks) - len(active_locks)

        if removed > 0:
            # Atomic write
            temp_file = self.state_file.with_suffix(".tmp")
            try:
                with open(temp_file, "w") as f:
                    for k, v in active_locks.items():
                        f.write(json.dumps({"key": k, **v}) + "\n")
                temp_file.rename(self.state_file)
            except OSError:
                if temp_file.exists():
                    temp_file.unlink()

        return removed

    def check(self, *, key: str) -> bool:
        """Check if a lock exists and is valid.

        Args:
            key: The idempotency key.

        Returns:
            True if lock exists and is not expired, False otherwise.
        """
        locks = self._read_locks()

        if key not in locks:
            return False

        expiry = locks[key].get("expiry", 0)
        return time.time() < expiry
