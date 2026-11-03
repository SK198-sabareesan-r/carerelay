"""Strands observability hook for CareRelay Sentinel.

Implements the Strands HookProvider interface to add lightweight, structured
observability around every agent's lifecycle: when an invocation starts/ends,
and when each tool is called/returns (with duration and any exception). This
is the workshop's "hooks / production layer" concept applied to CareRelay -
it gives an auditable, real-time trace of agent + tool activity without
changing any decision logic (hooks observe; they never decide).

Captured entries are both logged (CloudWatch when running on App Runner /
Lambda) and, optionally, appended to an in-memory sink the caller can read
back for the activity timeline. Field access is defensive because the exact
event attribute names vary slightly across Strands SDK versions.
"""
from __future__ import annotations

import time
from typing import Any, Callable, List, Optional

from strands.hooks import (
    HookProvider,
    HookRegistry,
    BeforeInvocationEvent,
    AfterInvocationEvent,
    BeforeToolCallEvent,
    AfterToolCallEvent,
)

from ..services.audit_service import AuditTrail


def _attr(obj: Any, *names: str, default: Any = None) -> Any:
    """Return the first present attribute from `names` (SDK versions differ)."""
    for n in names:
        if hasattr(obj, n):
            val = getattr(obj, n)
            if val is not None:
                return val
    return default


def _tool_name(event: Any) -> str:
    # Try a few shapes: event.tool_use["name"], event.tool.name, event.tool_name
    tu = _attr(event, "tool_use", "toolUse")
    if isinstance(tu, dict):
        return tu.get("name") or tu.get("toolName") or "tool"
    tool = _attr(event, "tool")
    if tool is not None:
        return _attr(tool, "name", "tool_name", default="tool")
    return _attr(event, "tool_name", default="tool")


class SentinelObservabilityHook(HookProvider):
    """Audit/observability hook attachable to any Strands Agent.

    Usage:
        hook = SentinelObservabilityHook(agent_name="document_agent", audit=trail)
        agent = Agent(..., hooks=[hook])
    """

    def __init__(
        self,
        agent_name: str,
        audit: Optional[AuditTrail] = None,
        log_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.agent_name = agent_name
        self.audit = audit
        self._log = log_fn or (lambda msg: None)
        self.events: List[dict] = []  # in-memory sink (always populated)

    # HookProvider interface ------------------------------------------------
    def register_hooks(self, registry: HookRegistry, **_kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)
        registry.add_callback(BeforeToolCallEvent, self._on_before_tool)
        registry.add_callback(AfterToolCallEvent, self._on_after_tool)

    # Callbacks -------------------------------------------------------------
    def _record(self, event_name: str, detail: str, data: Optional[dict] = None) -> None:
        entry = {"event": event_name, "actor": self.agent_name, "detail": detail,
                 "data": data or {}, "ts": time.time()}
        self.events.append(entry)
        self._log(f"[{self.agent_name}] {event_name}: {detail}")
        if self.audit is not None:
            self.audit.record(event_name, self.agent_name, detail, data or {})

    def _on_before_invocation(self, event: BeforeInvocationEvent) -> None:
        self._record("AGENT_INVOCATION_START", f"{self.agent_name} invocation started.")

    def _on_after_invocation(self, event: AfterInvocationEvent) -> None:
        self._record("AGENT_INVOCATION_END", f"{self.agent_name} invocation completed.")

    def _on_before_tool(self, event: BeforeToolCallEvent) -> None:
        name = _tool_name(event)
        self._record("TOOL_CALL_START", f"{self.agent_name} called tool '{name}'.",
                     {"tool": name})

    def _on_after_tool(self, event: AfterToolCallEvent) -> None:
        name = _tool_name(event)
        duration = _attr(event, "duration", default=None)
        exc = _attr(event, "exception", default=None)
        if exc is not None:
            self._record("TOOL_CALL_FAILED", f"Tool '{name}' raised: {str(exc)[:160]}",
                         {"tool": name, "error": str(exc)[:200]})
        else:
            d = f" ({duration:.2f}s)" if isinstance(duration, (int, float)) else ""
            self._record("TOOL_CALL_DONE", f"Tool '{name}' returned{d}.",
                         {"tool": name, "duration": duration})
