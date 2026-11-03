"""Orchestration layer for CareRelay Sentinel.

Graph-led orchestration (case_graph) coordinates the case lifecycle; the
evidence_workflow runs the independent evidence-analysis tasks in parallel;
the exception_swarm investigates complex conflicts; the decider_router makes
the bounded next-action choice; case_state carries the shared, serializable
state between all of them.

The orchestration layer sequences work and routes it. It never makes a
coverage decision itself - those come from the deterministic services
(agent_app/services) and rules engine, exactly as in the rest of CareRelay.
"""
