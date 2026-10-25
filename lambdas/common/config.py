"""Central configuration, read from environment variables.

Every value has a safe default so the modules import cleanly in local tests
without any AWS environment configured.

Credential precedence (see aws_clients.py for how these are consumed):
  1. AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY (explicit keys, e.g. from .env)
  2. AWS_PROFILE (a named AWS CLI profile)
  3. boto3's own default resolution (Lambda execution role, ~/.aws/credentials, etc.)

Inside a deployed Lambda or the AgentCore Runtime container, none of the
three AWS_* credential variables below should be set - the execution role
is used instead. They exist for local development only.
"""
import os


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# --- AWS account / region / credentials (local development only) ---
AWS_REGION = _get("AWS_REGION", _get("AWS_DEFAULT_REGION", "ap-south-1"))
# Explicit access key/secret, e.g. loaded from a local .env. Takes priority
# over AWS_PROFILE if both are set. Leave both blank in any deployed
# Lambda/container - the execution role is used instead.
AWS_ACCESS_KEY_ID = _get("AWS_ACCESS_KEY_ID", _get("ACCESS_KEY", ""))
AWS_SECRET_ACCESS_KEY = _get("AWS_SECRET_ACCESS_KEY", _get("SECRET_KEY", ""))
AWS_SESSION_TOKEN = _get("AWS_SESSION_TOKEN", "")
# Named AWS CLI profile, used only if explicit keys above are not set.
AWS_PROFILE = _get("AWS_PROFILE", "")

# --- Optional SEPARATE credentials for Bedrock only -------------------
# Some accounts/keys are restricted from invoking Bedrock models while
# still being valid for every other AWS service used in this project
# (S3, DynamoDB, SES, Transcribe, End User Messaging, KMS, etc). If set,
# these take priority over AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY ONLY for
# the bedrock-runtime client (see aws_clients.bedrock_runtime()). Every
# other client keeps using the main AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
# above. Leave both blank to just use the main credentials for Bedrock too.
BEDROCK_AWS_ACCESS_KEY_ID = _get("BEDROCK_AWS_ACCESS_KEY_ID", "")
BEDROCK_AWS_SECRET_ACCESS_KEY = _get("BEDROCK_AWS_SECRET_ACCESS_KEY", "")
BEDROCK_AWS_SESSION_TOKEN = _get("BEDROCK_AWS_SESSION_TOKEN", "")

# --- Storage ---
MEDIA_BUCKET = _get("MEDIA_BUCKET", "carerelay-media-local")
PATIENTS_TABLE = _get("PATIENTS_TABLE", "carerelay-patients-local")
INTAKE_EVENTS_TABLE = _get("INTAKE_EVENTS_TABLE", "carerelay-intake-events-local")
PRIOR_AUTH_TABLE = _get("PRIOR_AUTH_TABLE", "carerelay-prior-auth-local")
PAYER_RULES_TABLE = _get("PAYER_RULES_TABLE", "carerelay-payer-rules-local")
STAFF_USERS_TABLE = _get("STAFF_USERS_TABLE", "carerelay-staff-users-local")

# --- Amazon Bedrock (narration/summarization only - never decisioning) ---
# Claude Sonnet 4.6 (global cross-region inference) is natively multimodal
# (text + image + PDF), so the same model ID covers text generation AND
# insurance-card vision extraction (replaces Amazon Textract).
BEDROCK_MODEL_ID = _get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
BEDROCK_VISION_MODEL_ID = _get("BEDROCK_VISION_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
# Override only if Bedrock model access was granted in a different region
# than AWS_REGION (e.g. models enabled in us-east-1 while CDS runs in
# ap-south-1). Leave blank to use AWS_REGION.
BEDROCK_REGION = _get("BEDROCK_REGION", "")

# --- Amazon Transcribe (voice notes) ---
# Defaults to AWS_REGION; override if Transcribe is enabled in a different
# region on your account. (Insurance-card extraction now runs on the Bedrock
# vision model, not Textract - see BEDROCK_VISION_MODEL_ID above.)
TRANSCRIBE_REGION = _get("TRANSCRIBE_REGION", "")

# --- AWS End User Messaging Social (WhatsApp patient intake) ---
WHATSAPP_PHONE_NUMBER_ID = _get("WHATSAPP_PHONE_NUMBER_ID", "")
META_API_VERSION = _get("META_API_VERSION", "v20.0")
# Meta App Secret, used to verify the X-Hub-Signature-256 header on direct
# webhook posts (API Gateway path). Not needed for the SNS path, since AWS
# End User Messaging Social already validates the Meta signature before
# publishing to SNS. Leave blank to skip signature verification (e.g. when
# only using the SNS path, or for local testing).
META_APP_SECRET = _get("META_APP_SECRET", "")
# Meta webhook verify token, matched against hub.verify_token on the GET
# verification challenge (API Gateway path only).
META_WEBHOOK_VERIFY_TOKEN = _get("META_WEBHOOK_VERIFY_TOKEN", "")

# --- AWS End User Messaging SMS / RCS (doctor approval card) ---
RCS_PHONE_NUMBER_ID = _get("RCS_PHONE_NUMBER_ID", "")
SMS_ORIGINATION_NUMBER = _get("SMS_ORIGINATION_NUMBER", "")


def clinic_approver_numbers() -> list:
    raw = _get("CLINIC_APPROVER_NUMBERS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


# --- Amazon SES ---
SES_SENDER = _get("SES_SENDER", "")


def ses_command_recipients() -> list:
    raw = _get("SES_COMMAND_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]


# --- AWS KMS (audit report signing) ---
KMS_SIGNING_KEY_ID = _get("KMS_SIGNING_KEY_ID", "")

# --- Amazon Bedrock AgentCore Runtime (the Strands agent backend) ---
AGENT_RUNTIME_ARN = _get("AGENT_RUNTIME_ARN", "")

# --- Behavior ---
INTAKE_BATCH_WINDOW_SECONDS = int(_get("INTAKE_BATCH_WINDOW_SECONDS", "15"))
DOCTOR_APPROVAL_FUNCTION_NAME = _get("DOCTOR_APPROVAL_FUNCTION_NAME", "")
PAYER_VERIFICATION_FUNCTION_NAME = _get("PAYER_VERIFICATION_FUNCTION_NAME", "")
REPORT_FUNCTION_NAME = _get("REPORT_FUNCTION_NAME", "")
LOG_LEVEL = _get("LOG_LEVEL", "INFO")
