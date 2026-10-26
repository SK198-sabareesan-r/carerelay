#!/usr/bin/env python3
"""Deploy the webhook_receiver Lambda directly via boto3, bypassing `cdk
deploy` (deferred per project decision - same pattern as
scripts/deploy_dashboard_api.py).

Packages lambdas/ (minus dashboard_api and channel_dispatcher, which this
deployment doesn't need). Creates/updates:
    - IAM role "CareRelay-WebhookReceiverRole"
    - Lambda function "CareRelay-WebhookReceiver"

Does NOT create the SNS subscription or API Gateway webhook route itself -
see scripts/subscribe_webhook_to_sns.py for wiring this function to the
CareRelay-InboundTopic SNS topic.

Usage:
    python scripts/deploy_webhook_receiver.py
"""
import io
import json
import os
import re
import sys
import time
import zipfile

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_LAMBDAS_DIR = os.path.join(_REPO_ROOT, "lambdas")

sys.path.insert(0, _LAMBDAS_DIR)


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = re.match(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402

FUNCTION_NAME = "CareRelay-WebhookReceiver"
ROLE_NAME = "CareRelay-WebhookReceiverRole"
HANDLER = "webhook_receiver.handler.handler"
RUNTIME = "python3.12"
TIMEOUT_SECONDS = 60
MEMORY_MB = 512

_EXCLUDED_DIR_NAMES = {"__pycache__", "dashboard_api", "channel_dispatcher"}


def build_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(_LAMBDAS_DIR):
            dirs[:] = [d for d in dirs if d not in _EXCLUDED_DIR_NAMES]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                full_path = os.path.join(root, fname)
                arc_path = os.path.relpath(full_path, _LAMBDAS_DIR)
                zf.write(full_path, arc_path)
    buf.seek(0)
    return buf.read()


def ensure_role(iam_client) -> str:
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }

    try:
        resp = iam_client.get_role(RoleName=ROLE_NAME)
        role_arn = resp["Role"]["Arn"]
        print(f"[iam] Role '{ROLE_NAME}' already exists: {role_arn}")
    except iam_client.exceptions.NoSuchEntityException:
        print(f"[iam] Creating role '{ROLE_NAME}'...")
        resp = iam_client.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for the CareRelay webhook_receiver Lambda (direct boto3 deploy, bypasses CDK).",
        )
        role_arn = resp["Role"]["Arn"]
        print("[iam] Waiting for role propagation...")
        time.sleep(10)

    iam_client.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )

    account_id = aws_clients._session().client("sts").get_caller_identity()["Account"]  # noqa: SLF001
    region = config.AWS_REGION
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DynamoDbWrite",
                "Effect": "Allow",
                "Action": ["dynamodb:PutItem", "dynamodb:GetItem"],
                "Resource": [
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.INTAKE_EVENTS_TABLE}",
                ],
            },
            {
                "Sid": "S3MediaWrite",
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{config.MEDIA_BUCKET}/*"],
            },
            {
                "Sid": "SocialMessagingMediaFetch",
                "Effect": "Allow",
                "Action": [
                    "social-messaging:GetWhatsAppMessageMedia",
                    # Needed for the acknowledgment send (_maybe_send_acknowledgment
                    # -> channels.send_whatsapp -> _resolve_aws_phone_number_id).
                    "social-messaging:SendWhatsAppMessage",
                    "social-messaging:ListLinkedWhatsAppBusinessAccounts",
                    "social-messaging:GetLinkedWhatsAppBusinessAccount",
                ],
                "Resource": "*",
            },
        ],
    }
    iam_client.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="CareRelayWebhookReceiverAccess",
        PolicyDocument=json.dumps(inline_policy),
    )
    return role_arn


def ensure_function(lambda_client, role_arn: str, zip_bytes: bytes) -> str:
    env_vars = {
        "INTAKE_EVENTS_TABLE": config.INTAKE_EVENTS_TABLE,
        "MEDIA_BUCKET": config.MEDIA_BUCKET,
        "META_API_VERSION": config.META_API_VERSION,
        "META_APP_SECRET": config.META_APP_SECRET,
        "META_WEBHOOK_VERIFY_TOKEN": config.META_WEBHOOK_VERIFY_TOKEN,
        "LOG_LEVEL": config.LOG_LEVEL,
    }

    try:
        lambda_client.get_function(FunctionName=FUNCTION_NAME)
        exists = True
    except lambda_client.exceptions.ResourceNotFoundException:
        exists = False

    if exists:
        print(f"[lambda] Updating existing function '{FUNCTION_NAME}'...")
        lambda_client.update_function_code(FunctionName=FUNCTION_NAME, ZipFile=zip_bytes)
        waiter = lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=FUNCTION_NAME)
        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Runtime=RUNTIME,
            Handler=HANDLER,
            Timeout=TIMEOUT_SECONDS,
            MemorySize=MEMORY_MB,
            Environment={"Variables": env_vars},
        )
        waiter.wait(FunctionName=FUNCTION_NAME)
    else:
        print(f"[lambda] Creating function '{FUNCTION_NAME}'...")
        for attempt in range(5):
            try:
                lambda_client.create_function(
                    FunctionName=FUNCTION_NAME,
                    Runtime=RUNTIME,
                    Role=role_arn,
                    Handler=HANDLER,
                    Code={"ZipFile": zip_bytes},
                    Timeout=TIMEOUT_SECONDS,
                    MemorySize=MEMORY_MB,
                    Environment={"Variables": env_vars},
                    Description="CareRelay webhook_receiver - SNS/API Gateway inbound WhatsApp intake (direct boto3 deploy, bypasses CDK).",
                )
                break
            except lambda_client.exceptions.InvalidParameterValueException as exc:
                if "role" in str(exc).lower() and attempt < 4:
                    print(f"[lambda] Role not yet assumable, retrying in 5s... ({exc})")
                    time.sleep(5)
                    continue
                raise
        waiter = lambda_client.get_waiter("function_active")
        waiter.wait(FunctionName=FUNCTION_NAME)

    resp = lambda_client.get_function(FunctionName=FUNCTION_NAME)
    return resp["Configuration"]["FunctionArn"]


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    if not config.INTAKE_EVENTS_TABLE or config.INTAKE_EVENTS_TABLE.endswith("-local"):
        print("ERROR: INTAKE_EVENTS_TABLE is not a real table name. Run scripts/setup_intake_infra.py first.", file=sys.stderr)
        sys.exit(1)

    print("[package] Building deployment zip...")
    zip_bytes = build_zip()
    print(f"[package] Zip size: {len(zip_bytes) / 1024:.1f} KB")

    iam_client = aws_clients._session().client("iam")  # noqa: SLF001
    role_arn = ensure_role(iam_client)
    print(f"[iam] Role ARN: {role_arn}")

    lambda_client = aws_clients.lambda_client()
    function_arn = ensure_function(lambda_client, role_arn, zip_bytes)
    print(f"[lambda] Function ARN: {function_arn}")
    print("\nDone. Next: run scripts/subscribe_webhook_to_sns.py to wire this up to the SNS topic.")


if __name__ == "__main__":
    main()
