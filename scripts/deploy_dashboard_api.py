#!/usr/bin/env python3
"""Deploy the dashboard_api Lambda directly via boto3, bypassing `cdk
deploy` (deferred per project decision - see scripts/setup_auth_infra.py and
scripts/setup_case_infra.py for the same pattern applied to DynamoDB).

Packages lambdas/ (the Lambda code) plus agent_app/__init__.py and
agent_app/rules_engine.py (so POST /cases can run the SAME deterministic
rules_engine.evaluate() the Strands agent pipeline uses - NOT the full
agent_app package, which would pull in the Strands SDK unnecessarily;
rules_engine.py has zero third-party dependencies by design, see its
module docstring "NO LLM CALLS IN THIS FILE").

Creates (if missing) or updates (if present):
    - IAM role "CareRelay-DashboardApiRole" with:
        AWSLambdaBasicExecutionRole (CloudWatch Logs)
        inline policy: dynamodb read/write on PriorAuthTable/PayerRulesTable/
                        StaffUsersTable, s3:GetObject on MEDIA_BUCKET,
                        ses:SendEmail/SendRawEmail (onboarding email)
    - Lambda function "CareRelay-DashboardApi" (Python 3.12, zip upload)

This script is idempotent - re-run any time handler.py changes to push an
update (UpdateFunctionCode + UpdateFunctionConfiguration).

Usage:
    python scripts/deploy_dashboard_api.py
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
_AGENT_APP_DIR = os.path.join(_REPO_ROOT, "agent_app")

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

FUNCTION_NAME = "CareRelay-DashboardApi"
ROLE_NAME = "CareRelay-DashboardApiRole"
HANDLER = "dashboard_api.handler.handler"
RUNTIME = "python3.12"
TIMEOUT_SECONDS = 30
MEMORY_MB = 512

_EXCLUDED_DIR_NAMES = {"__pycache__", "channel_dispatcher", "webhook_receiver"}


def build_zip() -> bytes:
    """Zip lambdas/ (minus channel_dispatcher/webhook_receiver, which this
    deployment doesn't need and which would otherwise require their own
    env vars/permissions) plus agent_app/__init__.py + rules_engine.py."""
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

        zf.write(os.path.join(_AGENT_APP_DIR, "__init__.py"), "agent_app/__init__.py")
        zf.write(os.path.join(_AGENT_APP_DIR, "rules_engine.py"), "agent_app/rules_engine.py")

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
            Description="Execution role for the CareRelay dashboard_api Lambda (direct boto3 deploy, bypasses CDK).",
        )
        role_arn = resp["Role"]["Arn"]
        # New roles need a few seconds before they're assumable by Lambda.
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
                "Sid": "DynamoDbAccess",
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:Scan",
                    "dynamodb:Query",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.PRIOR_AUTH_TABLE}",
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.PAYER_RULES_TABLE}",
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.STAFF_USERS_TABLE}",
                ],
            },
            {
                "Sid": "S3MediaRead",
                "Effect": "Allow",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{config.MEDIA_BUCKET}/*"],
            },
            {
                "Sid": "SesSend",
                "Effect": "Allow",
                "Action": ["ses:SendEmail", "ses:SendRawEmail"],
                "Resource": ["*"],
            },
            {
                # Lets POST /cases/{id}/message (_handle_send_message) reply
                # to a patient over WhatsApp directly from the console.
                "Sid": "SocialMessagingSend",
                "Effect": "Allow",
                "Action": [
                    "social-messaging:SendWhatsAppMessage",
                    # Needed by channels._resolve_aws_phone_number_id to translate
                    # Meta's numeric phone_number_id (stored on the case) into
                    # AWS's own phone-number-id format SendWhatsAppMessage requires.
                    "social-messaging:ListLinkedWhatsAppBusinessAccounts",
                    "social-messaging:GetLinkedWhatsAppBusinessAccount",
                ],
                "Resource": "*",
            },
        ],
    }
    iam_client.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="CareRelayDashboardApiAccess",
        PolicyDocument=json.dumps(inline_policy),
    )
    return role_arn


def ensure_function(lambda_client, role_arn: str, zip_bytes: bytes) -> str:
    env_vars = {
        # NOTE: AWS_REGION is a Lambda-reserved env var (injected automatically
        # from the function's deployed region) - do not set it explicitly here,
        # CreateFunction/UpdateFunctionConfiguration will reject the request.
        "PRIOR_AUTH_TABLE": config.PRIOR_AUTH_TABLE,
        "PAYER_RULES_TABLE": config.PAYER_RULES_TABLE,
        "STAFF_USERS_TABLE": config.STAFF_USERS_TABLE,
        "MEDIA_BUCKET": config.MEDIA_BUCKET,
        "SES_SENDER": config.SES_SENDER,
        "SES_SANDBOX_OVERRIDE_RECIPIENT": config.SES_SANDBOX_OVERRIDE_RECIPIENT,
        "WHATSAPP_PHONE_NUMBER_ID": config.WHATSAPP_PHONE_NUMBER_ID,
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
                    Description="CareRelay dashboard_api - read/write API backing the frontend console (direct boto3 deploy, bypasses CDK).",
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
        print(
            "ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env (main credentials).",
            file=sys.stderr,
        )
        sys.exit(1)

    for name, env_var in (
        (config.PRIOR_AUTH_TABLE, "PRIOR_AUTH_TABLE"),
        (config.PAYER_RULES_TABLE, "PAYER_RULES_TABLE"),
        (config.STAFF_USERS_TABLE, "STAFF_USERS_TABLE"),
    ):
        if not name or name.endswith("-local"):
            print(f"ERROR: {env_var} is not a real table name ('{name}'). Run the setup_*_infra.py scripts first.", file=sys.stderr)
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
    print("\nDone. Next: run scripts/deploy_api_gateway.py to expose this function over HTTP.")


if __name__ == "__main__":
    main()
