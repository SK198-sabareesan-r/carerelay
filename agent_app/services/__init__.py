"""Deterministic services for CareRelay Sentinel.

These modules are the "code" half of "code decides, AI talks". They contain
NO language-model calls for any decision-bearing logic. Agents call into them
(or the orchestrator does) to:

- extract/normalize evidence (evidence_extraction)
- retrieve payer requirements (policy_retrieval)
- detect cross-document conflicts (reconciliation)
- compute the readiness report + overall status (readiness_engine)
- validate case-state transitions (state_transition)
- record an auditable trail of agent + human actions (audit_service)

Everything a judge or clinician would challenge ("why did it decide X?")
traces back to one of these deterministic functions, not to a prompt.
"""
