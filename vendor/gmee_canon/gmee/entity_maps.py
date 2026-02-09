from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple, Optional
import yaml

@dataclass(frozen=True)
class EntityMap:
    rows: Dict[Tuple[str, str], Dict[str, Any]]

    @staticmethod
    def load(path: str) -> "EntityMap":
        p = Path(path)
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
        rows: Dict[Tuple[str,str], Dict[str, Any]] = {}
        for r in data:
            et = str(r.get("entity_type",""))
            eid = str(r.get("entity_id",""))
            attrs = {k:v for k,v in (r or {}).items() if k not in ("entity_type","entity_id")}
            rows[(et,eid)] = attrs
        return EntityMap(rows=rows)

    def enrich(self, feature_rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in feature_rows:
            et = str(r.get("entity_type",""))
            eid = str(r.get("entity_id",""))
            attrs = self.rows.get((et,eid))
            if attrs:
                rr = dict(r)
                for k,v in attrs.items():
                    # avoid overwriting existing keys
                    if k not in rr:
                        rr[k] = v
                out.append(rr)
            else:
                out.append(r)
        return out
