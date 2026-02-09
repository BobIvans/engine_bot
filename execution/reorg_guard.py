"""execution/reorg_guard.py

PR-G.2 Reorg Guard. Extended in PR-G.5 for position state rollback.

Detects dropped or rolled-back transactions by monitoring transaction status
against block height to identify reorgs and phantom confirmations.

PR-G.5 Extensions:
- Async reorg detection (non-blocking)
- Position state rollback on reorg detection
- Adjustment records for all corrections
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests

# Default Solana RPC URL
DEFAULT_SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"


class ReorgGuard:
    """Monitors transaction finality and detects reorgs.

    Uses RPC getSignatureStatuses to check transaction confirmation status
    and compares against block height to detect dropped transactions.

    Status return values:
    - FINALIZED: Transaction is confirmed and finalized
    - CONFIRMED: Transaction is confirmed but not yet finalized
    - PENDING: Transaction is still processing
    - DROPPED: Transaction was dropped (not in recent block history)
    """

    def __init__(
        self,
        *,
        rpc_url: str = DEFAULT_SOLANA_RPC_URL,
        timeout_ms: int = 5000,
    ):
        """Initialize the reorg guard.

        Args:
            rpc_url: Solana RPC endpoint URL.
            timeout_ms: Request timeout in milliseconds.
        """
        self.rpc_url = rpc_url
        self.timeout_ms = timeout_ms
        self._session = requests.Session()

    def _rpc_request(self, method: str, params: list = None) -> Dict[str, Any]:
        """Make an RPC request to the Solana node.

        Args:
            method: RPC method name.
            params: Optional list of parameters.

        Returns:
            Response dictionary or error dict.
        """
        request_body = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params or [],
        }

        try:
            response = self._session.post(
                self.rpc_url,
                json=request_body,
                timeout=self.timeout_ms / 1000.0,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": str(e),
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON response: {str(e)}",
            }

    def get_block_height(self) -> Optional[int]:
        """Get the current block height from the cluster.

        Returns:
            Current block height or None on error.
        """
        result = self._rpc_request("getBlockHeight")
        if result.get("success") is False:
            return None
        return result.get("result")

    def get_signature_statuses(
        self, signatures: list[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Get status for multiple transaction signatures.

        Args:
            signatures: List of transaction signatures.

        Returns:
            Dict mapping signature to status info.
        """
        if not signatures:
            return {}

        result = self._rpc_request("getSignatureStatuses", [signatures])

        if result.get("success") is False:
            return {}

        statuses = {}
        for entry in result.get("result", {}).get("value", []):
            if entry is None:
                continue
            sig = entry.get("signature", "")
            statuses[sig] = {
                "slot": entry.get("slot", 0),
                "confirmations": entry.get("confirmations"),
                "status": entry.get("status"),
                "err": entry.get("err"),
            }

        return statuses

    def check_tx_status(
        self,
        *,
        tx_hash: str,
        last_valid_block_height: Optional[int] = None,
    ) -> str:
        """Check transaction status and detect reorgs/drops.

        Args:
            tx_hash: The transaction signature/hash.
            last_valid_block_height: The last valid block height from the tx.
                If current block height exceeds this and tx is not found,
                the tx is considered dropped.

        Returns:
            Status string: FINALIZED, CONFIRMED, PENDING, or DROPPED.
        """
        # Get current block height
        current_height = self.get_block_height()

        # Get transaction status
        statuses = self.get_signature_statuses([tx_hash])

        if tx_hash not in statuses:
            # Transaction not found in recent history
            if current_height is not None and last_valid_block_height is not None:
                if current_height > last_valid_block_height:
                    # Past the valid block height and tx not found = DROPPED
                    return "DROPPED"
            return "PENDING"

        status_info = statuses[tx_hash]
        status = status_info.get("status")
        err = status_info.get("err")

        # Check for transaction error
        if err is not None:
            # Transaction failed
            return "DROPPED"

        # Check confirmation status
        if status is not None:
            # Transaction succeeded - check if finalized
            if isinstance(status, dict) and status.get("Ok") is not None:
                # "Ok" status means success
                if status_info.get("confirmations") is None:
                    # No confirmations means finalized
                    return "FINALIZED"
                else:
                    # Has confirmations but not finalized
                    return "CONFIRMED"

        # Check slot vs current height for finality heuristic
        tx_slot = status_info.get("slot", 0)
        if current_height is not None:
            # If we're more than 150 blocks ahead, consider it finalized
            if current_height - tx_slot > 150:
                return "FINALIZED"
            elif tx_slot <= current_height:
                return "CONFIRMED"

        return "PENDING"

    def is_confirmed(self, *, tx_hash: str) -> bool:
        """Quick check if a transaction is confirmed.

        Args:
            tx_hash: The transaction signature/hash.

        Returns:
            True if confirmed or finalized.
        """
        status = self.check_tx_status(tx_hash=tx_hash)
        return status in ("CONFIRMED", "FINALIZED")

    def is_finalized(self, *, tx_hash: str) -> bool:
        """Quick check if a transaction is finalized.

        Args:
            tx_hash: The transaction signature/hash.

        Returns:
            True if finalized.
        """
        return self.check_tx_status(tx_hash=tx_hash) == "FINALIZED"


# PR-G.5 Extensions: Reorg Detection with Position State Rollback
# ================================================================

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class ReorgEvent:
    """Reorganization event detected by the guard."""
    tx_hash: str
    signal_id: str
    previous_status: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    block_height: Optional[int] = None
    rollback_amount: Optional[float] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "signal_id": self.signal_id,
            "previous_status": self.previous_status,
            "detected_at": self.detected_at.isoformat(),
            "block_height": self.block_height,
            "rollback_amount": self.rollback_amount,
            "reason": self.reason,
        }


@dataclass
class PositionAdjustment:
    """Position state adjustment due to reorg or fill correction."""
    signal_id: str
    mint: str
    adjustment_type: str  # reorg_rollback | fill_correction | close_correction
    previous_amount: float
    new_amount: float
    price: float
    tx_hash: str
    trace_id: str
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "mint": self.mint,
            "adjustment_type": self.adjustment_type,
            "previous_amount": self.previous_amount,
            "new_amount": self.new_amount,
            "price": self.price,
            "tx_hash": self.tx_hash,
            "trace_id": self.trace_id,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
        }


class ReorgGuardExtended(ReorgGuard):
    """Extended Reorg Guard with async detection and position rollback.

    Features:
    - Async polling for reorg detection (non-blocking)
    - Position state rollback on reorg detection
    - Adjustment records for all corrections
    - Trace_id / tx_sig logging
    """

    def __init__(
        self,
        *,
        rpc_url: str = DEFAULT_SOLANA_RPC_URL,
        timeout_ms: int = 5000,
        poll_interval_sec: int = 5,
        confirmation_blocks: int = 31,
    ):
        """Initialize extended reorg guard.

        Args:
            rpc_url: Solana RPC endpoint URL.
            timeout_ms: Request timeout in milliseconds.
            poll_interval_sec: Polling interval for reorg detection.
            confirmation_blocks: Blocks to wait for confirmation.
        """
        super().__init__(rpc_url=rpc_url, timeout_ms=timeout_ms)
        self.poll_interval_sec = poll_interval_sec
        self.confirmation_blocks = confirmation_blocks

        # Tracked transactions
        self._pending_txs: Dict[str, Dict[str, Any]] = {}

        # Reorg events history
        self._reorg_events: list[ReorgEvent] = []

        # Position adjustments history
        self._adjustments: list[PositionAdjustment] = []

        # Callbacks
        self._on_reorg: Optional[callable] = None
        self._on_adjustment: Optional[callable] = None

        # Async polling state
        self._running = False

    def set_reorg_callback(self, callback: callable) -> None:
        """Set callback for reorg events.

        Args:
            callback: Function to call on reorg detection
        """
        self._on_reorg = callback

    def set_adjustment_callback(self, callback: callable) -> None:
        """Set callback for position adjustments.

        Args:
            callback: Function to call on position adjustments
        """
        self._on_adjustment = callback

    def track_transaction(
        self,
        tx_hash: str,
        signal_id: str,
        amount: float,
        price: float,
        tx_type: str = "fill",
        trace_id: Optional[str] = None,
    ) -> None:
        """Track a transaction for reorg detection.

        Args:
            tx_hash: Transaction signature.
            signal_id: Signal ID associated with the tx.
            amount: Position amount (for rollback calculation).
            price: Entry/close price.
            tx_type: Type of transaction (fill, close).
            trace_id: Optional trace ID for logging.
        """
        if trace_id is None:
            trace_id = str(uuid.uuid4())[:8]

        self._pending_txs[tx_hash] = {
            "signal_id": signal_id,
            "amount": amount,
            "price": price,
            "tx_type": tx_type,
            "trace_id": trace_id,
            "status": "pending",
            "first_seen": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"[reorg_guard] Tracking tx {tx_hash[:16]}... "
            f"signal={signal_id} amount={amount} trace={trace_id}"
        )

    def detect_reorg(self, tx_hash: str) -> Optional[ReorgEvent]:
        """Detect if a transaction was affected by reorg.

        Args:
            tx_hash: Transaction to check.

        Returns:
            ReorgEvent if reorg detected, None otherwise.
        """
        if tx_hash not in self._pending_txs:
            return None

        tx_info = self._pending_txs[tx_hash]
        status = self.check_tx_status(tx_hash=tx_hash)

        if status == "DROPPED":
            # Transaction was dropped - create reorg event
            event = ReorgEvent(
                tx_hash=tx_hash,
                signal_id=tx_info["signal_id"],
                previous_status="pending",
                reason="Transaction dropped (reorg or timeout)",
                rollback_amount=tx_info["amount"],
            )

            self._reorg_events.append(event)
            self._pending_txs[tx_hash]["status"] = "dropped"

            # Notify callback
            if self._on_reorg:
                try:
                    self._on_reorg(event)
                except Exception as e:
                    logger.error(f"[reorg_guard] Reorg callback failed: {e}")

            logger.warning(
                f"[reorg_guard] Reorg detected: tx={tx_hash[:16]}... "
                f"signal={tx_info['signal_id']} amount={tx_info['amount']}"
            )

            return event

        elif status == "FINALIZED":
            self._pending_txs[tx_hash]["status"] = "finalized"

        return None

    def rollback_position(
        self,
        signal_id: str,
        mint: str,
        previous_amount: float,
        new_amount: float,
        price: float,
        tx_hash: str,
        reason: str = "reorg_rollback",
    ) -> PositionAdjustment:
        """Create a position adjustment for reorg rollback.

        Args:
            signal_id: Signal ID for the position.
            mint: Token mint.
            previous_amount: Previous position amount.
            new_amount: New position amount after rollback.
            price: Entry price.
            tx_hash: Transaction that was reorged.
            reason: Reason for adjustment.

        Returns:
            PositionAdjustment record.
        """
        # Get trace_id from pending tx or generate new one
        trace_id = self._pending_txs.get(tx_hash, {}).get("trace_id", str(uuid.uuid4())[:8])

        adjustment = PositionAdjustment(
            signal_id=signal_id,
            mint=mint,
            adjustment_type=reason,
            previous_amount=previous_amount,
            new_amount=new_amount,
            price=price,
            tx_hash=tx_hash,
            trace_id=trace_id,
            reason=reason,
        )

        self._adjustments.append(adjustment)

        # Notify callback
        if self._on_adjustment:
            try:
                self._on_adjustment(adjustment)
            except Exception as e:
                logger.error(f"[reorg_guard] Adjustment callback failed: {e}")

        logger.info(
            f"[reorg_guard] Position adjustment: signal={signal_id} "
            f"{previous_amount} -> {new_amount} "
            f"(tx={tx_hash[:16]}... trace={trace_id} reason={reason})"
        )

        return adjustment

    def check_all_pending(self) -> list[ReorgEvent]:
        """Check all pending transactions for reorgs.

        Returns:
            List of detected reorg events.
        """
        events = []
        for tx_hash in list(self._pending_txs.keys()):
            if self._pending_txs[tx_hash]["status"] == "pending":
                event = self.detect_reorg(tx_hash)
                if event:
                    events.append(event)
        return events

    def get_reorg_history(self) -> list[Dict[str, Any]]:
        """Get all reorg events as dictionaries."""
        return [e.to_dict() for e in self._reorg_events]

    def get_adjustment_history(self) -> list[Dict[str, Any]]:
        """Get all position adjustments as dictionaries."""
        return [a.to_dict() for a in self._adjustments]

    def get_pending_txs(self) -> list[Dict[str, Any]]:
        """Get pending transactions status."""
        return [
            {**info, "tx_hash": tx_hash}
            for tx_hash, info in self._pending_txs.items()
            if info["status"] == "pending"
        ]
