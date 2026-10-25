"""Deterministic prior-authorization rules engine.

NO LLM CALLS IN THIS FILE. Every function here is plain Python evaluated
against structured data (the PayerRulesTable, or the in-memory fallback used
for local tests). This module is "the code" half of "code decides, AI talks" -
it is called BY the Strands tools, it never calls a model itself.

A rule row looks like (see cdk/stacks/storage_stack.py PayerRulesTable and
seed/payer_rules.json):

    {
      "payer_id": "PAYER-ACME",
      "cpt_code": "29881",
      "procedure_name": "Knee arthroscopy, meniscectomy",
      "requires_prior_auth": true,
      "required_documents": ["clinical_notes", "xray_or_mri"],
      "rule_id": "ACME-29881-v1",
      "notes": "Requires imaging within 90 days per ACME policy section 4.2"
    }
"""
import dataclasses
from typing import Any, Dict, List, Optional

PRIOR_AUTH_REQUIRED = "PRIOR_AUTH_REQUIRED"
PRIOR_AUTH_NOT_REQUIRED = "NOT_REQUIRED"
PRIOR_AUTH_INCOMPLETE = "INCOMPLETE_INFO"
PRIOR_AUTH_UNKNOWN_RULE = "NO_MATCHING_RULE"


@dataclasses.dataclass
class RuleDecision:
    """Output of evaluate(). Every field traces to rule data, not a model."""

    cpt_code: str
    payer_id: str
    outcome: str  # one of the PRIOR_AUTH_* constants above
    requires_prior_auth: bool
    required_documents: List[str]
    missing_documents: List[str]
    matched_rule_id: Optional[str]
    rationale: str  # plain statement of which rule fired, no model involved

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


# Fallback in-memory rule set so this module (and anything that imports it)
# works with zero AWS setup - used by local tests and as a safety net if
# DynamoDB is briefly unavailable. The real deployed rules live in
# PayerRulesTable, seeded from seed/payer_rules.json.
_FALLBACK_RULES: List[Dict[str, Any]] = [
    {
        "payer_id": "PAYER-ACME",
        "cpt_code": "29881",
        "procedure_name": "Knee arthroscopy, meniscectomy",
        "requires_prior_auth": True,
        "required_documents": ["clinical_notes", "xray_or_mri"],
        "rule_id": "ACME-29881-v1",
        "notes": "Requires imaging within 90 days per ACME policy section 4.2",
    },
    {
        "payer_id": "PAYER-ACME",
        "cpt_code": "D0150",
        "procedure_name": "Comprehensive oral evaluation",
        "requires_prior_auth": False,
        "required_documents": [],
        "rule_id": "ACME-D0150-v1",
        "notes": "Routine dental exam, no prior-auth required under ACME policy",
    },
    {
        "payer_id": "PAYER-ACME",
        "cpt_code": "D2740",
        "procedure_name": "Crown - porcelain/ceramic",
        "requires_prior_auth": True,
        "required_documents": ["clinical_notes", "xray_or_mri"],
        "rule_id": "ACME-D2740-v1",
        "notes": "Requires pre-treatment X-ray per ACME dental policy section 7.1",
    },
    {
        "payer_id": "PAYER-GLOBALHEALTH",
        "cpt_code": "29881",
        "procedure_name": "Knee arthroscopy, meniscectomy",
        "requires_prior_auth": True,
        "required_documents": ["clinical_notes", "xray_or_mri", "conservative_treatment_history"],
        "rule_id": "GH-29881-v1",
        "notes": "Requires 6 weeks documented conservative treatment per GlobalHealth policy",
    },
    {
        "payer_id": "PAYER-GLOBALHEALTH",
        "cpt_code": "77067",
        "procedure_name": "Screening mammography, bilateral",
        "requires_prior_auth": False,
        "required_documents": [],
        "rule_id": "GH-77067-v1",
        "notes": "Preventive screening, no prior-auth required under GlobalHealth policy",
    },
]


def _lookup_rule(payer_id: str, cpt_code: str, rules: Optional[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
    source = rules if rules is not None else _FALLBACK_RULES
    for rule in source:
        if rule.get("payer_id") == payer_id and rule.get("cpt_code") == cpt_code:
            return rule
    return None


def evaluate(
    payer_id: str,
    cpt_code: str,
    documents_on_file: Optional[List[str]] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
) -> RuleDecision:
    """Evaluate whether a procedure needs prior authorization.

    Args:
        payer_id: insurance payer identifier (from the extracted card, e.g. "PAYER-ACME").
        cpt_code: the CPT/procedure code the clinic is billing for.
        documents_on_file: document types already collected for this case
            (e.g. ["clinical_notes"]). Compared against the rule's
            required_documents to compute missing_documents.
        rules: optional explicit rule set (used by tests / the Lambda that
            loads PayerRulesTable). Falls back to the built-in rule set.

    Returns:
        RuleDecision - a fully deterministic result. No model is invoked.
    """
    documents_on_file = documents_on_file or []
    rule = _lookup_rule(payer_id, cpt_code, rules)

    if rule is None:
        return RuleDecision(
            cpt_code=cpt_code,
            payer_id=payer_id,
            outcome=PRIOR_AUTH_UNKNOWN_RULE,
            requires_prior_auth=True,  # fail safe: treat unknown as requiring review
            required_documents=[],
            missing_documents=[],
            matched_rule_id=None,
            rationale=(
                f"No rule found for payer={payer_id} cpt={cpt_code}. "
                "Defaulting to manual review (fail-safe)."
            ),
        )

    requires = bool(rule.get("requires_prior_auth", False))
    required_docs = list(rule.get("required_documents", []))

    if not requires:
        return RuleDecision(
            cpt_code=cpt_code,
            payer_id=payer_id,
            outcome=PRIOR_AUTH_NOT_REQUIRED,
            requires_prior_auth=False,
            required_documents=[],
            missing_documents=[],
            matched_rule_id=rule.get("rule_id"),
            rationale=f"Rule {rule.get('rule_id')}: {rule.get('notes', 'no prior-auth required')}",
        )

    missing = [d for d in required_docs if d not in documents_on_file]
    outcome = PRIOR_AUTH_INCOMPLETE if missing else PRIOR_AUTH_REQUIRED

    return RuleDecision(
        cpt_code=cpt_code,
        payer_id=payer_id,
        outcome=outcome,
        requires_prior_auth=True,
        required_documents=required_docs,
        missing_documents=missing,
        matched_rule_id=rule.get("rule_id"),
        rationale=f"Rule {rule.get('rule_id')}: {rule.get('notes', 'prior authorization required')}",
    )


def load_rules_from_dynamodb(table) -> List[Dict[str, Any]]:
    """Scan PayerRulesTable into the plain-dict shape `evaluate()` expects.

    `table` is a boto3 DynamoDB Table resource. Kept separate from
    `evaluate()` so the rule logic itself has zero AWS dependency and stays
    trivially unit-testable.
    """
    items: List[Dict[str, Any]] = []
    resp = table.scan()
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items
