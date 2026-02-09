from __future__ import annotations
from pathlib import Path
import json, html
from typing import Any, Dict, List, Tuple

def _read_json_file(p: Path, max_chars: int = 5000) -> str:
    if not p.exists():
        return ""
    try:
        txt = p.read_text(encoding="utf-8")
        if len(txt) > max_chars:
            return txt[:max_chars] + "\n... (truncated)"
        return txt
    except Exception:
        return ""

def _read_jsonl(p: Path, limit: int = 50) -> List[Dict[str, Any]]:

    rows: List[Dict[str, Any]] = []
    if not p.exists():
        return rows
    with p.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if i + 1 >= limit:
                break
    return rows

def render_bundle_report(bundle_dir: Path, limit_per_file: int = 50) -> Path:
    """Render a deterministic HTML report for a trade/trace evidence bundle."""
    bundle_dir = bundle_dir.resolve()
    manifest_path = bundle_dir / "manifest.json"
    trace_manifest_path = bundle_dir / "trace_manifest.json"

    title = f"GMEE Evidence Bundle Report: {bundle_dir.name}"
    parts: List[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append(f"<title>{html.escape(title)}</title>")
    parts.append("<style>body{font-family:ui-sans-serif,system-ui,Arial;margin:20px} pre{white-space:pre-wrap} table{border-collapse:collapse} td,th{border:1px solid #ddd;padding:6px} .muted{color:#666}</style>")
    parts.append("</head><body>")
    parts.append(f"<h1>{html.escape(title)}</h1>")

    def emit_manifest(mp: Path, label: str) -> None:
        if not mp.exists():
            return
        m = json.loads(mp.read_text(encoding="utf-8"))
        parts.append(f"<h2>{html.escape(label)}</h2>")
        parts.append("<pre class='muted'>" + html.escape(json.dumps(m, indent=2, ensure_ascii=False)) + "</pre>")

    emit_manifest(trace_manifest_path, "Trace manifest")
    emit_manifest(manifest_path, "Trade manifest")
    # External capture snapshots (optional)
    ext_paths = bundle_dir / "external_snapshot_paths.json"
    if ext_paths.exists():
        parts.append("<h2>External snapshot paths</h2>")
        parts.append("<pre class='muted'>" + html.escape(_read_json_file(ext_paths)) + "</pre>")

    ext_root = bundle_dir / "external_snapshots"
    if ext_root.exists():
        parts.append("<h2>External snapshot manifests</h2>")
        for mp in sorted(ext_root.glob("*/snapshot_manifest.json")):
            parts.append(f"<h3><code>{html.escape(str(mp.relative_to(bundle_dir)))}</code></h3>")
            parts.append("<pre class='muted'>" + html.escape(_read_json_file(mp)) + "</pre>")

    # List files
    parts.append("<h2>Files</h2><table><tr><th>path</th><th>preview</th></tr>")
    for p in sorted(bundle_dir.rglob("*.jsonl")):
        rel = p.relative_to(bundle_dir)
        preview = _read_jsonl(p, limit=5)
        parts.append("<tr>")
        parts.append(f"<td><code>{html.escape(str(rel))}</code></td>")
        parts.append(f"<td><pre>{html.escape(json.dumps(preview, indent=2, ensure_ascii=False))}</pre></td>")
        parts.append("</tr>")
    parts.append("</table>")

    parts.append("</body></html>")
    out = bundle_dir / "report.html"
    out.write_text("".join(parts), encoding="utf-8")
    return out
