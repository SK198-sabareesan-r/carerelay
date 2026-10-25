"""Strands tools for the CareRelay agents.

Every tool here either (a) reads/extracts data via an AWS service (the
Bedrock vision model for card photos, Transcribe for voice notes) or
(b) calls the deterministic rules_engine / a simulated payer endpoint and
returns the structured result unchanged. No tool in this package makes a
coverage, eligibility, or approval decision
itself - see agent_app/__init__.py for the full rationale.
"""
