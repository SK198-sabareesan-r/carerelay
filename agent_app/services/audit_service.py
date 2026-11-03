"""Deterministic audit trail: an append-only record of agent + human actions.

Every meaningful step (a document classified, a requirement retrieved, a
discrepancy detected, a Decider routing, a Safety Critic verdict, a human
action) is appended as an immutable entry with a UTC timestamp. The dashboard
AgentTrace / AgentTimeline views render this. Keeping it a plain in-memory /
serializable structure (not a model call) means the audit trail can never be
"reasoned away" - it is a literal log.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class AuditEntry:
    event: str                         # e.g. "DOCUMENT_CLASSIFIED", "DECIDER_ROUTED"
    actor: str                         # agent name, "decider", "readiness_engine", "human:<user>"
    detail: str
    timestamp: str = field(default_factory=_now_iso)
    data: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"audit-{uuid.uuid4().hex[:10]}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event": self.event,
            "actor": self.actor,
            "detail": self.detail,
            "timestamp": self.timestamp,
            "data": self.data,
        }


class AuditTrail:
    """Append-only trail for one case."""

    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        self._entries: List[AuditEntry] = []

    def record(
        self, event: str, actor: str, detail: str, data: Optional[Dict[str, Any]] = None
    ) -> AuditEntry:
        entry = AuditEntry(event=event, actor=actor, detail=detail, data=data or {})
        self._entries.append(entry)
        return entry

    @property
    def entries(self) -> List[AuditEntry]:
        return list(self._entries)

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]
