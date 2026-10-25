"""Message drafting tools for the Notification Agent.

These tools only DRAFT message content and structure (patient WhatsApp text,
doctor RCS approval card, audit email summary). They do not call any AWS
messaging API themselves - the channel_dispatcher Lambda takes the drafted
output and sends it via lambdas/common/channels.py. This keeps the Strands
agent's blast radius limited to composing text, never to actually dispatching
real messages to real phone numbers or inboxes.
"""
from typing import Any, Dict, List, Optional

from strands import tool


@tool
def draft_patient_message(
    outcome: str,
    missing_documents: Optional[List[str]] = None,
    approval_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Draft the WhatsApp message to send back to the patient.

    Args:
        outcome: the prior-auth outcome string from check_prior_auth
            (PRIOR_AUTH_REQUIRED | NOT_REQUIRED | INCOMPLETE_INFO | NO_MATCHING_RULE).
        missing_documents: document types still needed, if outcome is INCOMPLETE_INFO.
        approval_code: the payer approval code, if verification succeeded.

    Returns:
        A dict: body (string, the message text) and buttons (list of
        {id, title} quick replies, 1-3 items).
    """
    missing_documents = missing_documents or []

    if outcome == "NOT_REQUIRED":
        return {
            "body": (
                "Good news - your upcoming procedure does not require prior "
                "authorization. Your appointment is confirmed."
            ),
            "buttons": [{"id": "ack", "title": "Got it"}],
        }

    if outcome == "INCOMPLETE_INFO":
        items = ", ".join(d.replace("_", " ") for d in missing_documents) or "a few documents"
        return {
            "body": (
                "We're processing your prior authorization. We still need: "
                f"{items}. Please reply with a photo or PDF of each."
            ),
            "buttons": [{"id": "upload_docs", "title": "Upload now"}],
        }

    if outcome == "PRIOR_AUTH_REQUIRED" and approval_code:
        return {
            "body": (
                "Your insurance coverage has been verified "
                f"(approval code {approval_code}). Your doctor's office has "
                "been notified to confirm your appointment slot."
            ),
            "buttons": [{"id": "ack", "title": "Thank you"}],
        }

    return {
        "body": (
            "We're still verifying your insurance coverage for this "
            "procedure. We'll message you as soon as it's confirmed."
        ),
        "buttons": [{"id": "ack", "title": "Got it"}],
    }


@tool
def draft_doctor_approval_card(
    patient_name: str,
    procedure_name: str,
    cpt_code: str,
    outcome: str,
    missing_documents: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Draft the RCS action card sent to the clinic/doctor for approval.

    Args:
        patient_name: patient's display name (use a masked/short identifier
            if the full name is not available, never invent one).
        procedure_name: human-readable procedure description.
        cpt_code: the CPT/procedure code.
        outcome: the prior-auth outcome string from check_prior_auth.
        missing_documents: document types still outstanding, if any.

    Returns:
        A dict: body (string) and buttons (list of {id, title}, max 2:
        approve + request-more-info).
    """
    missing_documents = missing_documents or []
    status_line = {
        "NOT_REQUIRED": "No prior authorization required.",
        "PRIOR_AUTH_REQUIRED": "Prior authorization verified with payer.",
        "INCOMPLETE_INFO": f"Missing documents: {', '.join(missing_documents) or 'see case'}.",
        "NO_MATCHING_RULE": "No matching payer rule - manual review needed.",
    }.get(outcome, "Status unknown.")

    return {
        "body": (
            f"Patient: {patient_name}\n"
            f"Procedure: {procedure_name} ({cpt_code})\n"
            f"{status_line}"
        ),
        "buttons": [
            {"id": "approve_slot", "title": "Approve Treatment Slot"},
            {"id": "request_notes", "title": "Request Extra Notes"},
        ],
    }


@tool
def draft_audit_summary(
    case_id: str,
    patient_name: str,
    payer_id: str,
    cpt_code: str,
    outcome: str,
    rationale: str,
    approval_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Draft the plain-text/HTML content for the KMS-signed audit report email.

    Args:
        case_id: the prior-auth case identifier.
        patient_name: patient's display name.
        payer_id: insurance payer identifier.
        cpt_code: the CPT/procedure code.
        outcome: the prior-auth outcome string from check_prior_auth.
        rationale: the rules_engine rationale string (quote it verbatim -
            do not paraphrase the rule citation).
        approval_code: payer approval code, if verification occurred.

    Returns:
        A dict: headline (string) and detail_lines (list of strings) for the
        report_generator Lambda to render into the signed PDF/HTML email.
    """
    detail_lines = [
        f"Case ID: {case_id}",
        f"Payer: {payer_id}  |  CPT: {cpt_code}",
        f"Outcome: {outcome}",
        f"Rule rationale: {rationale}",
    ]
    if approval_code:
        detail_lines.append(f"Payer approval code: {approval_code}")

    return {
        "headline": f"Prior authorization {outcome.replace('_', ' ').lower()} for {patient_name}",
        "detail_lines": detail_lines,
    }
