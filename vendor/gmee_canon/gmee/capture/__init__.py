"""Premium-source capture pipeline (P0-safe).

This module helps you turn short access windows (trial/demo) into long-lived,
reproducible artifacts:

A) RAW snapshots: store primary responses with metadata & hashes.
B) Universal Variables: normalize provider-specific fields to a unified schema.
C) Labels: derive "truth" labels from your own trades (ClickHouse), not from providers.

Strict P0 rule: no canonical schema/docs/SQL/YAML edits are required.
Artifacts are stored on disk (JSONL/manifest) or referenced from forensics_events.
"""

from .raw import RawRecord, RawSnapshotWriter
from .universal_vars import UniversalVar, UniversalVarsWriter, ProviderMapping
from .labels import TradeLabel, TradeLabelsExporter
from .snapshot import SnapshotManifest, SnapshotBuilder
from .glue import (
    CaptureSnapshotRef,
    load_snapshots,
    match_snapshots_for_trade,
    attach_snapshots_via_forensics,
    write_capture_refs_jsonl,
    write_external_snapshot_paths_json,
    copy_snapshot_manifests,
)


__all__ = [
    "RawRecord",
    "RawSnapshotWriter",
    "UniversalVar",
    "UniversalVarsWriter",
    "ProviderMapping",
    "TradeLabel",
    "TradeLabelsExporter",
    "SnapshotManifest",
    "SnapshotBuilder",
    "CaptureSnapshotRef",
    "load_snapshots",
    "match_snapshots_for_trade",
    "attach_snapshots_via_forensics",
    "write_capture_refs_jsonl",
    "write_external_snapshot_paths_json",
    "copy_snapshot_manifests",
]

