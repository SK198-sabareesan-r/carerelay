"""Verification tools: the deterministic prior-auth check and the simulated
payer IVR call.

`check_prior_auth` is a thin, read-only wrapper around rules_engine.evaluate().
The Verification Agent can call it as many times as it wants but cannot
change its outcome - the tool returns exactly what the rule data says.

`call_payer_ivr` is clearly a SIMULATION of an outbound call to an insurance
payer's automated phone line, not a real telephony integration. See the
docstring for why: building a production-grade agent that can navigate an
arbitrary third-party IVR tree, extract a spoken approval code, and interpret
success/failure is a multi-week integration project at a real insurer, not
something safe to fake as "real" in a hackathon demo. We simulate it with a
deterministic, seeded outcome so the step is honestly represented end-to-end
without claiming a live phone call that isn't happening. See
docs/ARCHITECTURE.md "Payer verification: simulated, not live" for the
production path (Amazon Connect contact flow + Lex/Bedrock IVR agent) this
would be replaced with.
"""
import hashlib
from typing import Any, Dict, List, Optional

from strands import tool

from lambdas.common import aws_clients, config
from lambdas.common.logging_utils import get_logger, log_event

from .. import rules_engine

logger = get_logger("agent_tools.verification")


@tool
def check_prior_auth(
    payer_id: str, cpt_code: str, documents_on_file: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Determine whether a procedure requires prior authorization (deterministic).

    This tool NEVER uses a language model to decide coverage. It loads the
    payer/CPT rule table from DynamoDB (falling back to a built-in rule set
    if the table is unavailable, e.g. in local testing) and evaluates it with
    plain Python. The result is fully auditable back to a specific rule row.

    Args:
        payer_id: insurance payer identifier, e.g. from the extracted card
            (map payer_name to a payer_id first if needed; use "PAYER-UNKNOWN"
            if it cannot be determined).
        cpt_code: the CPT/dental procedure code for the planned treatment.
        documents_on_file: document types already collected for this patient
            (e.g. ["clinical_notes"]). Omit or pass [] if none yet.

    Returns:
        A dict: outcome (PRIOR_AUTH_REQUIRED | NOT_REQUIRED | INCOMPLETE_INFO
        | NO_MATCHING_RULE), requires_prior_auth (bool), required_documents
        (list), missing_documents (list), matched_rule_id (string or null),
        rationale (plain-English statement of which rule fired).
    """
    rules = _load_rules_safely()
    decision = rules_engine.evaluate(
        payer_id=payer_id,
        cpt_code=cpt_code,
        documents_on_file=documents_on_file or [],
        rules=rules,
    )
    log_event(
        logger,
        "info",
        "rules_engine.evaluated",
        payer_id=payer_id,
        cpt_code=cpt_code,
        outcome=decision.outcome,
        matched_rule_id=decision.matched_rule_id,
    )
    return decision.to_dict()


def _load_rules_safely() -> Optional[List[Dict[str, Any]]]:
    """Load PayerRulesTable; return None (built-in fallback) if unavailable."""
    try:
        table = aws_clients.dynamodb_resource().Table(config.PAYER_RULES_TABLE)
        return rules_engine.load_rules_from_dynamodb(table)
    except Exception as exc:  # noqa: BLE001 - fall back to built-in rules
        log_event(logger, "warning", "payer_rules.load.failed", error=str(exc))
        return None


@tool
def call_payer_ivr(payer_id: str, member_id: str, cpt_code: str) -> Dict[str, Any]:
    """Call the insurance payer's IVR line to verify eligibility (SIMULATED).

    THIS IS A SIMULATION, not a live telephone call. It deterministically
    derives a plausible outcome from the inputs (same payer+member+cpt always
    produces the same result) so the demo is reproducible and honestly
    labeled, rather than pretending to dial a real insurer. See the module
    docstring for the production replacement (Amazon Connect + IVR agent).

    Args:
        payer_id: insurance payer identifier.
        member_id: the member/policy ID from the extracted insurance card.
        cpt_code: the CPT/procedure code being verified.

    Returns:
        A dict: simulated (always True, to make the non-live nature explicit
        to callers/logs/UI), eligible (bool), approval_code (string or null),
        payer_hotline_note (string describing what a real IVR call would do).
    """
    seed = f"{payer_id}:{member_id}:{cpt_code}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    eligible = int(digest[:2], 16) % 10 != 0  # ~90% eligible, deterministic per input
    approval_code = f"SIM-{digest[2:10].upper()}" if eligible else None

    log_event(
        logger,
        "info",
        "payer_ivr.simulated",
        payer_id=payer_id,
        eligible=eligible,
    )
    return {
        "simulated": True,
        "eligible": eligible,
        "approval_code": approval_code,
        "payer_hotline_note": (
            "SIMULATED verification. In production this step places an "
            "outbound call via Amazon Connect to the payer's IVR, navigates "
            "the menu with DTMF/speech, and records the spoken approval "
            "code to S3 for audit."
        ),
    }
