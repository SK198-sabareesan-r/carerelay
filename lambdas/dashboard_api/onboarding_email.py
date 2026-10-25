"""Onboarding email sent to a hospital's registered contact address right
after a successful staff signup (see handler._handle_signup).

Uses Amazon SES v2 (SendEmail, simple content) via the shared
aws_clients.ses() client - same credential path as every other non-Bedrock
AWS call in this project (main AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY, see
lambdas/common/aws_clients.py). The sender identity (config.SES_SENDER) must
be a verified SES identity in the target account/region or SendEmail will
fail - this module treats that failure as non-fatal (signup must still
succeed; see the try/except in handler.py), so the console works even
before/without SES verification completing.
"""
import time
from typing import Optional

from common import aws_clients, config
from common.logging_utils import get_logger, log_event

logger = get_logger("dashboard_api.onboarding_email")


def _render_html(display_name: str, hospital_name: str, hospital_id: str, username: str, role: str) -> str:
    year = time.strftime("%Y")
    return f"""\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Welcome to CareRelay</title>
  </head>
  <body style="margin:0;padding:0;background:#eef2f1;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <!-- Preview text (hidden, shows in inbox preview line) -->
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">
      Your CareRelay staff account for {hospital_name} is ready - sign in details inside.
    </div>

    <table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f1;padding:0;">
      <tr>
        <td align="center">
          <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;">

            <!-- ============ HEADER BANNER ============ -->
            <tr>
              <td style="background-color:#0f766e;background:linear-gradient(135deg,#0f766e 0%,#14b8a6 100%);padding:26px 32px 22px;">
                <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
                  <tr>
                    <td width="32" style="width:32px;">
                      <table cellpadding="0" cellspacing="0" role="presentation">
                        <tr>
                          <td width="32" height="32" bgcolor="#ffffff" style="width:32px;height:32px;border-radius:8px;text-align:center;vertical-align:middle;font-size:16px;font-weight:700;color:#0f766e;font-family:Arial,sans-serif;">+</td>
                        </tr>
                      </table>
                    </td>
                    <td style="padding-left:10px;" valign="middle">
                      <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:0.2px;font-family:Arial,sans-serif;">CareRelay</span>
                    </td>
                  </tr>
                </table>
                <h1 style="margin:18px 0 0;color:#ffffff;font-size:21px;line-height:1.3;font-weight:700;font-family:Arial,sans-serif;">
                  Welcome aboard, {display_name.split(" ")[0] if display_name else "there"}.
                </h1>
              </td>
            </tr>

            <!-- ============ CREDENTIALS CARD ============ -->
            <tr>
              <td style="padding:28px 32px 6px;">
                <p style="margin:0 0 16px;font-size:14px;line-height:1.6;color:#334155;font-family:Arial,sans-serif;">
                  Your staff account for <strong>{hospital_name}</strong> is ready. Use these details to sign in:
                </p>

                <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdfa;border:1px solid #ccfbf1;border-radius:12px;">
                  <tr>
                    <td style="padding:18px 20px;">
                      <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                          <td style="padding:5px 0;font-size:11px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;width:110px;font-family:Arial,sans-serif;">Hospital ID</td>
                          <td style="padding:5px 0;font-size:14px;font-weight:700;color:#0f172a;font-family:Consolas,Menlo,monospace;">{hospital_id}</td>
                        </tr>
                        <tr>
                          <td style="padding:5px 0;font-size:11px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;font-family:Arial,sans-serif;">Username</td>
                          <td style="padding:5px 0;font-size:14px;font-weight:700;color:#0f172a;font-family:Consolas,Menlo,monospace;">{username}</td>
                        </tr>
                        <tr>
                          <td style="padding:5px 0;font-size:11px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;color:#0f766e;font-family:Arial,sans-serif;">Role</td>
                          <td style="padding:5px 0;font-size:14px;font-weight:600;color:#0f172a;font-family:Arial,sans-serif;">{role}</td>
                        </tr>
                      </table>
                    </td>
                  </tr>
                </table>

                <p style="margin:14px 0 0;font-size:12px;line-height:1.5;color:#64748b;font-family:Arial,sans-serif;">
                  Didn't request this account? Contact your clinic administrator.
                </p>
              </td>
            </tr>

            <!-- ============ FEATURE HIGHLIGHT STRIP ============ -->
            <tr>
              <td style="padding:20px 32px 4px;">
                <table width="100%" cellpadding="0" cellspacing="0">
                  <tr>
                    <td width="33%" valign="top" style="padding:10px 6px;text-align:center;">
                      <div style="font-size:20px;">&#128202;</div>
                      <div style="margin-top:4px;font-size:12px;font-weight:700;color:#0f172a;font-family:Arial,sans-serif;">Analytics</div>
                    </td>
                    <td width="33%" valign="top" style="padding:10px 6px;text-align:center;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
                      <div style="font-size:20px;">&#128196;</div>
                      <div style="margin-top:4px;font-size:12px;font-weight:700;color:#0f172a;font-family:Arial,sans-serif;">Rule Explorer</div>
                    </td>
                    <td width="33%" valign="top" style="padding:10px 6px;text-align:center;">
                      <div style="font-size:20px;">&#9889;</div>
                      <div style="margin-top:4px;font-size:12px;font-weight:700;color:#0f172a;font-family:Arial,sans-serif;">Intake Queue</div>
                    </td>
                  </tr>
                </table>
              </td>
            </tr>

            <!-- ============ CTA ============ -->
            <tr>
              <td style="padding:12px 32px 28px;text-align:center;">
                <a href="#" style="display:inline-block;background-color:#0f766e;color:#ffffff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 28px;border-radius:8px;font-family:Arial,sans-serif;">
                  Open the Console
                </a>
              </td>
            </tr>

            <!-- ============ FOOTER BANNER ============ -->
            <tr>
              <td style="background-color:#0b2b27;padding:18px 32px;text-align:center;">
                <span style="color:#ffffff;font-size:13px;font-weight:700;font-family:Arial,sans-serif;">CareRelay</span>
                <p style="margin:6px 0 0;color:#8fb0ac;font-size:10.5px;line-height:1.5;font-family:Arial,sans-serif;">
                  Automated message - please do not reply. &copy; {year} CareRelay.
                </p>
              </td>
            </tr>

          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _render_text(display_name: str, hospital_name: str, hospital_id: str, username: str, role: str) -> str:
    first_name = display_name.split(" ")[0] if display_name else "there"
    return (
        f"CareRelay - Clinic Command Console\n"
        f"===================================\n\n"
        f"Welcome aboard, {first_name}.\n\n"
        f"Your staff account for {hospital_name} is live. Prior-authorization cases, "
        "analytics, and the rule explorer are ready whenever you are.\n\n"
        "YOUR SIGN-IN DETAILS\n"
        "---------------------\n"
        f"Hospital ID : {hospital_id}\n"
        f"Username    : {username}\n"
        f"Role        : {role}\n\n"
        f"Your Hospital ID is letters/numbers only and is shared by every staff account at "
        f"{hospital_name}. If you did not request this account, please contact your clinic "
        "administrator right away.\n\n"
        "WHAT YOU CAN DO\n"
        "---------------\n"
        "- Live Analytics: track approvals and outcomes in real time\n"
        "- Rule Explorer: see exactly which payer rule decided a case\n"
        "- Intake Queue: every WhatsApp case, triaged automatically\n\n"
        "---\n"
        "CareRelay - conversational prior-authorization for clinics, built on AWS End User "
        "Messaging (WhatsApp/RCS/SMS) and Amazon Bedrock AgentCore.\n"
        "This is an automated message - please do not reply to this email.\n"
    )


def send_onboarding_email(
    to_address: str,
    display_name: str,
    hospital_name: str,
    hospital_id: str,
    username: str,
    role: str,
) -> Optional[str]:
    """Send the onboarding email via SES. Returns the SES message id, or
    None if sending was skipped/failed (never raises - see callers)."""
    if not to_address:
        log_event(logger, "warning", "onboarding_email.skipped.no_recipient")
        return None
    if not config.SES_SENDER:
        log_event(logger, "warning", "onboarding_email.skipped.no_sender_configured")
        return None

    subject = f"Welcome to CareRelay - {hospital_name} staff account created"
    html = _render_html(display_name, hospital_name, hospital_id, username, role)
    text = _render_text(display_name, hospital_name, hospital_id, username, role)

    client = aws_clients.ses()
    resp = client.send_email(
        FromEmailAddress=config.SES_SENDER,
        Destination={"ToAddresses": [to_address]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html, "Charset": "UTF-8"},
                    "Text": {"Data": text, "Charset": "UTF-8"},
                },
            }
        },
    )
    message_id = resp.get("MessageId")
    log_event(logger, "info", "onboarding_email.sent", message_id=message_id, to=to_address)
    return message_id
