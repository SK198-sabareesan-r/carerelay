#!/usr/bin/env python3
"""Run the CareRelay agent pipeline locally against REAL AWS services,
with no CDK deploy and no AgentCore Runtime required.

This exercises exactly what the deployed system would do for one patient
case, using real Bedrock (Claude Sonnet 4.6 for both text and vision), real
S3, real Transcribe, and optionally real SES/WhatsApp sends - but running
the Strands supervisor
directly in-process instead of through AgentCore Runtime, and skipping
DynamoDB persistence unless --table-* args are given (so you can test
without having deployed PriorAuthTable/PayerRulesTable yet).

Why this exists: per project decision, the CDK deploy (which creates the
AgentCore Runtime, ECR repo, API Gateway, etc. - the costed resources) is
deferred to the very end, right before the demo recording. This script lets
you validate Bedrock access, the Strands multi-agent pipeline, Textract-
replacement vision extraction, Transcribe, SES, and WhatsApp sends well
before that, using only pay-per-call services.

Usage:
    # Text-only case (no card/voice media) - cheapest smoke test:
    python scripts/local_pipeline_test.py --cpt 29881 --payer PAYER-ACME

    # With a real insurance card photo already uploaded to S3:
    python scripts/local_pipeline_test.py --cpt 29881 --payer PAYER-ACME \\
        --card-bucket my-test-bucket --card-key cards/sample1.jpg

    # Also send the drafted outputs for real (WhatsApp/SES) - BE CAREFUL,
    # this sends a real message/email:
    python scripts/local_pipeline_test.py --cpt 29881 --payer PAYER-ACME \\
        --send-whatsapp +911234567890 --send-email

Credentials: loaded from .env at the repo root (AWS_ACCESS_KEY_ID /
AWS_SECRET_ACCESS_KEY), same as cdk/app.py. No CDK/CloudFormation calls are
made by this script.
"""
import argparse
import io
import json
import os
import sys

# Force UTF-8 stdout/stderr on Windows, where the default console codec
# (cp1252) cannot encode emoji the model may include in its narration -
# without this, every sub-agent tool call silently fails mid-stream with a
# charmap UnicodeEncodeError, which can cascade into the supervisor
# fabricating a final answer instead of surfacing the failure (see
# docs/ARCHITECTURE.md "Why this script forces UTF-8").
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))

from common.dotenv import load_repo_dotenv  # noqa: E402

load_repo_dotenv()

from common import aws_clients, config, channels  # noqa: E402
from common.logging_utils import get_logger, log_event  # noqa: E402

sys.path.insert(0, _REPO_ROOT)
from agent_app.main import _build_case_prompt, invoke  # noqa: E402

logger = get_logger("local_pipeline_test")


def check_bedrock_access() -> None:
    """Fail fast with a clear message if either configured model isn't
    callable, rather than letting the agent fail deep inside a tool-use loop."""
    client = aws_clients.bedrock_runtime()
    for label, model_id in (
        ("text (BEDROCK_MODEL_ID)", config.BEDROCK_MODEL_ID),
        ("vision (BEDROCK_VISION_MODEL_ID)", config.BEDROCK_VISION_MODEL_ID),
    ):
        try:
            client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": "Reply with the single word OK."}]}],
                inferenceConfig={"maxTokens": 10},
            )
            print(f"  [OK] {label} = {model_id}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] {label} = {model_id}\n         {exc}")
            raise SystemExit(
                f"\nBedrock access check failed for {model_id}. Common causes:\n"
                "  - Model access not granted for this model/region in the Bedrock console\n"
                "  - Wrong AWS_REGION in .env (some models are region-limited)\n"
                "  - IAM user lacks bedrock:InvokeModel / InvokeModelWithResponseStream"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cpt", required=True, help="CPT/procedure code, e.g. 29881 or D2740")
    parser.add_argument("--payer", required=True, help="Payer ID, e.g. PAYER-ACME")
    parser.add_argument("--procedure-name", default=None)
    parser.add_argument("--patient-name", default="Test Patient")
    parser.add_argument("--card-bucket", default=None, help="S3 bucket holding a real insurance card photo")
    parser.add_argument("--card-key", default=None, help="S3 key of the card photo")
    parser.add_argument("--voice-bucket", default=None, help="S3 bucket holding a real voice note")
    parser.add_argument("--voice-key", default=None, help="S3 key of the voice note")
    parser.add_argument("--voice-format", default="ogg")
    parser.add_argument(
        "--skip-bedrock-check", action="store_true",
        help="Skip the upfront Bedrock reachability check (not recommended).",
    )
    parser.add_argument(
        "--send-whatsapp", metavar="E164_NUMBER", default=None,
        help="Actually send the drafted patient message to this WhatsApp number. "
        "Requires WHATSAPP_PHONE_NUMBER_ID in .env. Sends a REAL message.",
    )
    parser.add_argument(
        "--send-email", action="store_true",
        help="Actually send the drafted audit summary via SES. Requires SES_SENDER "
        "and SES_COMMAND_RECIPIENTS in .env (verified identities if in the SES sandbox). "
        "Sends a REAL email.",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("STEP 1 - Bedrock reachability check")
    print("=" * 70)
    if args.skip_bedrock_check:
        print("  (skipped)")
    else:
        check_bedrock_access()

    payload = {
        "case_id": "local-test-case",
        "patient_name": args.patient_name,
        "cpt_code": args.cpt,
        "procedure_name": args.procedure_name or args.cpt,
        "payer_id": args.payer,
        "documents_on_file": [],
    }
    if args.card_bucket and args.card_key:
        payload["card_s3_bucket"] = args.card_bucket
        payload["card_s3_key"] = args.card_key
    if args.voice_bucket and args.voice_key:
        payload["voice_s3_bucket"] = args.voice_bucket
        payload["voice_s3_key"] = args.voice_key
        payload["voice_media_format"] = args.voice_format

    print("\n" + "=" * 70)
    print("STEP 2 - Build case prompt")
    print("=" * 70)
    prompt = _build_case_prompt(payload)
    print(prompt)

    print("\n" + "=" * 70)
    print("STEP 3 - Run the agent pipeline via main.invoke()")
    print("=" * 70)
    print("(Routing through main.invoke(), not the supervisor directly, so this")
    print(" exercises the SAME post-hoc cross-check against the deterministic")
    print(" rules engine that the real deployed system runs - see")
    print(" agent_app/main.py:_verify_against_rules_engine.)\n")

    response = invoke(payload)

    if response.get("verification_error"):
        print("[REJECTED] The agent's claimed verification result did not match")
        print("the deterministic rules engine and was REJECTED:\n")
        print(f"  {response['verification_error']}\n")
        print("Raw narration (for debugging):")
        print(response.get("narration", ""))
        raise SystemExit(1)

    case_result_dict = response.get("case_result")
    if case_result_dict is None:
        print("\n[WARNING] No structured output. Raw narration:")
        print(response.get("narration", ""))
        raise SystemExit(1)

    print("\n" + "=" * 70)
    print("STEP 4 - Structured case result (verified against rules_engine)")
    print("=" * 70)
    print(json.dumps(case_result_dict, indent=2, default=str))

    verification = case_result_dict["verification"]
    print("\nSummary:")
    print(f"  outcome          = {verification['outcome']}")
    print(f"  matched_rule_id  = {verification['matched_rule_id']}")
    print(f"  missing_documents= {verification['missing_documents']}")
    print(f"  payer_simulated  = {verification['payer_simulated']}")

    # Reconstruct a lightweight object so the rest of the script (WhatsApp/
    # SES send steps) can keep using attribute access like before.
    class _CaseResultView:
        def __init__(self, d):
            self.messages = _MessagesView(d["messages"])

    class _MessagesView:
        def __init__(self, d):
            self.__dict__.update(d)

    case_result = _CaseResultView(case_result_dict)

    if args.send_whatsapp:
        print("\n" + "=" * 70)
        print(f"STEP 5 - Sending REAL WhatsApp message to {args.send_whatsapp}")
        print("=" * 70)
        msg = channels.build_whatsapp_buttons(
            to=args.send_whatsapp,
            body=case_result.messages.patient_message_body,
            buttons=case_result.messages.patient_message_buttons or [{"id": "ack", "title": "Acknowledged"}],
        )
        message_id = channels.send_whatsapp(msg, config.WHATSAPP_PHONE_NUMBER_ID)
        print(f"  sent, message_id={message_id}")

    if args.send_email:
        print("\n" + "=" * 70)
        print("STEP 6 - Sending REAL SES audit email")
        print("=" * 70)
        recipients = config.ses_command_recipients()
        if not recipients or not config.SES_SENDER:
            print("  [SKIPPED] SES_SENDER / SES_COMMAND_RECIPIENTS not configured in .env")
        else:
            aws_clients.ses().send_email(
                FromEmailAddress=config.SES_SENDER,
                Destination={"ToAddresses": recipients},
                Content={
                    "Simple": {
                        "Subject": {"Data": f"[CareRelay local test] {case_result.messages.audit_headline}"[:200]},
                        "Body": {
                            "Text": {
                                "Data": "\n".join(case_result.messages.audit_detail_lines),
                            }
                        },
                    }
                },
            )
            print(f"  sent to {recipients}")

    print("\nDone.")


if __name__ == "__main__":
    main()
