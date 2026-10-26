"""Formal prior-authorization request email sent to the INSURANCE PAYER's
prior-auth department - distinct from the internal KMS-signed audit email
(_send_audit_email in handler.py, which goes to the clinic's own billing/ops
staff).

This is the outbound artifact a payer's prior-auth intake inbox would
receive: a structured request letter naming the member, the procedure
(CPT), the clinical justification, and the matched coverage rule. This
email is CareRelay's sole mechanism for contacting the insurance payer -
there is no outbound IVR/phone call. Many payers accept prior-auth
submissions by email/fax, so a formal written request is a realistic and
honestly-representable payer-contact path.

Uses Amazon SES v2 via the shared aws_clients.ses() client (same credential
path as every other non-Bedrock call). Recipient honors
config.resolve_ses_recipients() so that while the SES account is in the
sandbox, the letter is redirected to the verified override address instead
of failing to reach an unverified payer inbox. Sending is best-effort - a
failure here is logged, never raised, so it can't break case handling.
"""
import time
from typing import Any, Dict, List, Optional

from common import aws_clients, config
from common.logging_utils import get_logger, log_event

logger = get_logger("channel_dispatcher.payer_email")

# Where real payer prior-auth requests would be addressed. Overridable via
# env so each deployment can point at the payer's actual intake inbox (or,
# in the SES sandbox, everything is redirected to the verified override
# address by config.resolve_ses_recipients regardless of this value).
_PAYER_INTAKE_ADDRESS = config._get("PAYER_PRIOR_AUTH_INBOX", "priorauth@payer.example.com")  # noqa: SLF001


def _fmt(value: Optional[str], fallback: str = "Not provided") -> str:
    return value if value else fallback


def _render_html(ctx: Dict[str, Any]) -> str:
    year = time.strftime("%Y")
    docs = ctx.get("missing_documents") or []
    docs_block = (
        "<ul style='margin:6px 0 0;padding-left:18px;color:#334155;font-size:13px;'>"
        + "".join(f"<li>{d}</li>" for d in docs)
        + "</ul>"
        if docs
        else "<span style='color:#334155;font-size:13px;'>All required clinical documentation is attached/on file.</span>"
    )
    return f"""\
<!DOCTYPE html>
<html lang="en">
  <body style="margin:0;padding:0;background:#eef2f1;font-family:Arial,Helvetica,sans-serif;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f1;padding:0;">
      <tr><td align="center">
        <table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;">

          <tr>
            <td style="background:#0b2b27;padding:24px 32px;">
              <div style="color:#8fb0ac;font-size:11px;letter-spacing:1.5px;text-transform:uppercase;">Prior Authorization Request</div>
              <div style="color:#ffffff;font-size:20px;font-weight:700;margin-top:4px;">{_fmt(ctx.get("clinic_name"), "CareRelay Clinic")}</div>
            </td>
          </tr>

          <tr>
            <td style="padding:28px 32px 8px;">
              <p style="margin:0 0 16px;font-size:13px;line-height:1.6;color:#334155;">
                To the Prior Authorization Department, <strong>{_fmt(ctx.get("payer_name"), _fmt(ctx.get("payer_id")))}</strong>:
              </p>
              <p style="margin:0 0 18px;font-size:13px;line-height:1.6;color:#334155;">
                We are requesting prior authorization for the procedure detailed below on behalf of the
                member named. This request was generated and verified against your published coverage
                policy. Please review and confirm authorization.
              </p>

              <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e2e8f0;border-radius:10px;">
                <tr><td style="padding:16px 18px;">
                  <table width="100%" cellpadding="0" cellspacing="0" style="font-size:13px;color:#0f172a;">
                    {_row("Member ID", _fmt(ctx.get("member_id")))}
                    {_row("Group Number", _fmt(ctx.get("group_number")))}
                    {_row("Payer", _fmt(ctx.get("payer_name"), _fmt(ctx.get("payer_id"))))}
                    {_row("Patient reference", _fmt(ctx.get("patient_name")))}
                    {_row("Procedure (CPT)", f"{_fmt(ctx.get('cpt_code'))} &ndash; {_fmt(ctx.get('procedure_name'))}")}
                    {_row("Coverage rule", _fmt(ctx.get("matched_rule_id")))}
                    {_row("Case reference", _fmt(ctx.get("case_id")))}
                  </table>
                </td></tr>
              </table>

              <p style="margin:20px 0 4px;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;">Clinical justification</p>
              <p style="margin:0 0 16px;font-size:13px;line-height:1.6;color:#334155;">{_fmt(ctx.get("clinical_summary"), "Clinical summary pending provider review.")}</p>

              <p style="margin:0 0 4px;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;">Coverage determination</p>
              <p style="margin:0 0 6px;font-size:13px;line-height:1.6;color:#334155;">{_fmt(ctx.get("rationale"))}</p>

              <p style="margin:12px 0 4px;font-size:12px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;">Supporting documentation</p>
              {docs_block}
            </td>
          </tr>

          <tr>
            <td style="padding:20px 32px 28px;">
              <p style="margin:0;font-size:12px;line-height:1.6;color:#64748b;">
                This request was prepared by CareRelay on behalf of {_fmt(ctx.get("clinic_name"), "the requesting clinic")}.
                Coverage determinations are made against the payer's published rules; this letter does not
                constitute a guarantee of payment. Please direct questions to the requesting clinic.
              </p>
            </td>
          </tr>

          <tr>
            <td style="background:#0b2b27;padding:16px 32px;text-align:center;">
              <span style="color:#ffffff;font-size:12px;font-weight:700;">CareRelay</span>
              <p style="margin:5px 0 0;color:#8fb0ac;font-size:10px;">Automated prior-authorization request &copy; {year} CareRelay.</p>
            </td>
          </tr>

        </table>
      </td></tr>
    </table>
  </body>
</html>"""


def _row(label: str, value: str) -> str:
    return (
        f"<tr>"
        f"<td style='padding:5px 0;width:150px;color:#0f766e;font-weight:700;font-size:11px;"
        f"text-transform:uppercase;letter-spacing:0.5px;vertical-align:top;'>{label}</td>"
        f"<td style='padding:5px 0;color:#0f172a;font-size:13px;'>{value}</td>"
        f"</tr>"
    )


def _render_text(ctx: Dict[str, Any]) -> str:
    docs = ctx.get("missing_documents") or []
    docs_text = (
        "Outstanding documentation required:\n" + "\n".join(f"  - {d}" for d in docs)
        if docs
        else "All required clinical documentation is attached/on file."
    )
    return (
        "PRIOR AUTHORIZATION REQUEST\n"
        "===========================\n\n"
        f"To the Prior Authorization Department, {_fmt(ctx.get('payer_name'), _fmt(ctx.get('payer_id')))}:\n\n"
        "We are requesting prior authorization for the procedure below on behalf of the named member.\n\n"
        f"Member ID        : {_fmt(ctx.get('member_id'))}\n"
        f"Group Number     : {_fmt(ctx.get('group_number'))}\n"
        f"Payer            : {_fmt(ctx.get('payer_name'), _fmt(ctx.get('payer_id')))}\n"
        f"Patient reference: {_fmt(ctx.get('patient_name'))}\n"
        f"Procedure (CPT)  : {_fmt(ctx.get('cpt_code'))} - {_fmt(ctx.get('procedure_name'))}\n"
        f"Coverage rule    : {_fmt(ctx.get('matched_rule_id'))}\n"
        f"Case reference   : {_fmt(ctx.get('case_id'))}\n\n"
        f"CLINICAL JUSTIFICATION\n{_fmt(ctx.get('clinical_summary'), 'Clinical summary pending provider review.')}\n\n"
        f"COVERAGE DETERMINATION\n{_fmt(ctx.get('rationale'))}\n\n"
        f"{docs_text}\n\n"
        "---\n"
        f"Prepared by CareRelay on behalf of {_fmt(ctx.get('clinic_name'), 'the requesting clinic')}. "
        "This letter does not constitute a guarantee of payment.\n"
    )


def send_payer_prior_auth_request(ctx: Dict[str, Any]) -> Optional[str]:
    """Send the formal prior-auth request letter to the payer. `ctx` keys:
    payer_name, payer_id, member_id, group_number, patient_name, cpt_code,
    procedure_name, matched_rule_id, rationale, clinical_summary,
    missing_documents (list), case_id, clinic_name. Returns the SES message
    id, or None if skipped/failed (never raises)."""
    if not config.SES_SENDER:
        log_event(logger, "warning", "payer_email.skipped.no_sender_configured")
        return None

    recipients = config.resolve_ses_recipients([_PAYER_INTAKE_ADDRESS])
    subject = (
        f"Prior Authorization Request - {_fmt(ctx.get('procedure_name'), 'procedure')} "
        f"(CPT {_fmt(ctx.get('cpt_code'), 'n/a')}) - Member {_fmt(ctx.get('member_id'), 'n/a')}"
    )[:200]

    try:
        resp = aws_clients.ses().send_email(
            FromEmailAddress=config.SES_SENDER,
            Destination={"ToAddresses": recipients},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Html": {"Data": _render_html(ctx), "Charset": "UTF-8"},
                        "Text": {"Data": _render_text(ctx), "Charset": "UTF-8"},
                    },
                }
            },
        )
    except Exception as exc:  # noqa: BLE001 - never break case handling over the payer email
        log_event(logger, "warning", "payer_email.send.failed", error=str(exc))
        return None

    message_id = resp.get("MessageId")
    log_event(logger, "info", "payer_email.sent", message_id=message_id,
              to=recipients[0], intended=_PAYER_INTAKE_ADDRESS, case_id=ctx.get("case_id"))
    return message_id
