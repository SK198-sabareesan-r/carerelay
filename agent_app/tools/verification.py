"""Verification tools: the deterministic prior-auth check.

`check_prior_auth` is a thin, read-only wrapper around rules_engine.evaluate().
The Verification Agent can call it as many times as it wants but cannot
change its outcome - the tool returns exactly what the rule data says.

NOTE: CareRelay contacts the insurance payer ONLY by email - a formal
written prior-authorization request sent via Amazon SES (see
lambdas/channel_dispatcher/payer_email.py). There is no outbound IVR/phone
call to the payer. An earlier revision included a simulated `call_payer_ivr`
tool; it was removed in favor of the email-only payer contact path, which is
simpler, honestly representable end-to-end, and reflects how many payers
actually accept prior-auth submissions.
"""
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



