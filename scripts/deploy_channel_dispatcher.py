#!/usr/bin/env python3
"""Deploy the channel_dispatcher Lambda directly via boto3, bypassing `cdk
deploy` (deferred - same pattern as scripts/deploy_dashboard_api.py and
scripts/deploy_webhook_receiver.py).

Also wires the IntakeEventsTable DynamoDB Stream as this function's event
source (equivalent to compute_stack.py's DynamoEventSource mapping).

NOTE: this function calls aws_clients.agentcore_runtime().invoke_agent_runtime()
when a case batch is ready - but AGENT_RUNTIME_ARN is intentionally left
UNSET here, because the AgentCore Runtime (the Strands agent container) is
NOT deployed yet (that's the costed `cdk deploy` piece, still deferred).
handler.py's _invoke_agent() already handles this gracefully: if
AGENT_RUNTIME_ARN is blank, it logs a warning and returns {} instead of
raising, so this Lambda deploys and runs safely - it just won't produce a
PriorAuthTable case until the agent backend exists. Re-run this script
with AGENT_RUNTIME_ARN set in .env once AgentCore Runtime is deployed.

Usage:
    python scripts/deploy_channel_dispatcher.py
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

FUNCTION_NAME = "CareRelay-ChannelDispatcher"
ROLE_NAME = "CareRelay-ChannelDispatcherRole"
HANDLER = "channel_dispatcher.handler.handler"
RUNTIME = "python3.12"
TIMEOUT_SECONDS = 300
MEMORY_MB = 512
EVENT_SOURCE_UUID_TAG = "CareRelay-ChannelDispatcher-IntakeStream"

_EXCLUDED_DIR_NAMES = {"__pycache__", "dashboard_api", "webhook_receiver"}


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

        # Static pharmacy directory for the prior-auth consent list picker
        # (see handler.py:_load_pharmacies) - bundled flat next to
        # handler.py since the zip's layout doesn't mirror the repo tree.
        pharmacies_path = os.path.join(_REPO_ROOT, "seed", "pharmacies.json")
        if os.path.exists(pharmacies_path):
            zf.write(pharmacies_path, "channel_dispatcher/seed_pharmacies.json")

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
            Description="Execution role for the CareRelay channel_dispatcher Lambda (direct boto3 deploy, bypasses CDK).",
        )
        role_arn = resp["Role"]["Arn"]
        print("[iam] Waiting for role propagation...")
        time.sleep(10)

    iam_client.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
    )
    iam_client.attach_role_policy(
        RoleName=ROLE_NAME,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaDynamoDBExecutionRole",
    )

    account_id = aws_clients._session().client("sts").get_caller_identity()["Account"]  # noqa: SLF001
    region = config.AWS_REGION
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DynamoDbAccess",
                "Effect": "Allow",
                # Scan is needed by _append_case_note (button/list-picker
                # reply handling) to find a sender's most recent case.
                "Action": ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem", "dynamodb:Scan"],
                "Resource": [
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.PRIOR_AUTH_TABLE}",
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.PATIENTS_TABLE}",
                ],
            },
            {
                "Sid": "DynamoDbStreamRead",
                "Effect": "Allow",
                "Action": [
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                    "dynamodb:DescribeStream",
                    "dynamodb:ListStreams",
                ],
                "Resource": [
                    f"arn:aws:dynamodb:{region}:{account_id}:table/{config.INTAKE_EVENTS_TABLE}/stream/*",
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
                "Resource": "*",
            },
            {
                "Sid": "SocialMessagingSend",
                "Effect": "Allow",
                "Action": [
                    "social-messaging:SendWhatsAppMessage",
                    # Needed by channels._resolve_aws_phone_number_id to translate
                    # Meta's numeric phone_number_id (from the inbound event) into
                    # AWS's own phone-number-id format SendWhatsAppMessage requires.
                    "social-messaging:ListLinkedWhatsAppBusinessAccounts",
                    "social-messaging:GetLinkedWhatsAppBusinessAccount",
                ],
                "Resource": "*",
            },
            {
                "Sid": "SmsVoiceSend",
                "Effect": "Allow",
                "Action": ["sms-voice:SendTextMessage", "sms-voice:SendRcsMessage"],
                "Resource": "*",
            },
            {
                "Sid": "AgentCoreInvoke",
                "Effect": "Allow",
                "Action": ["bedrock-agentcore:InvokeAgentRuntime"],
                "Resource": "*",
            },
            {
                "Sid": "KmsSign",
                "Effect": "Allow",
                "Action": ["kms:Sign"],
                "Resource": "*",
            },
        ],
    }
    iam_client.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="CareRelayChannelDispatcherAccess",
        PolicyDocument=json.dumps(inline_policy),
    )
    return role_arn


def ensure_function(lambda_client, role_arn: str, zip_bytes: bytes) -> str:
    env_vars = {
        "PRIOR_AUTH_TABLE": config.PRIOR_AUTH_TABLE,
        "PATIENTS_TABLE": config.PATIENTS_TABLE,
        "MEDIA_BUCKET": config.MEDIA_BUCKET,
        "WHATSAPP_PHONE_NUMBER_ID": config.WHATSAPP_PHONE_NUMBER_ID,
        "META_API_VERSION": config.META_API_VERSION,
        "RCS_AGENT_ID": config.RCS_AGENT_ID,
        "RCS_PHONE_NUMBER_ID": config.RCS_PHONE_NUMBER_ID,
        "SMS_ORIGINATION_NUMBER": config.SMS_ORIGINATION_NUMBER,
        "CLINIC_APPROVER_NUMBERS": os.environ.get("CLINIC_APPROVER_NUMBERS", ""),
        "SES_SENDER": config.SES_SENDER,
        "SES_COMMAND_RECIPIENTS": os.environ.get("SES_COMMAND_RECIPIENTS", ""),
        "SES_SANDBOX_OVERRIDE_RECIPIENT": config.SES_SANDBOX_OVERRIDE_RECIPIENT,
        "PAYER_PRIOR_AUTH_INBOX": os.environ.get("PAYER_PRIOR_AUTH_INBOX", ""),
        "CLINIC_NAME": os.environ.get("CLINIC_NAME", ""),
        "KMS_SIGNING_KEY_ID": config.KMS_SIGNING_KEY_ID,
        # Intentionally blank - AgentCore Runtime is not deployed yet (see
        # module docstring). _invoke_agent() in handler.py no-ops safely
        # when this is unset.
        "AGENT_RUNTIME_ARN": config.AGENT_RUNTIME_ARN,
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
                    Description="CareRelay channel_dispatcher - DynamoDB Stream consumer, invokes AgentCore + sends CDS replies (direct boto3 deploy, bypasses CDK).",
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


def ensure_stream_event_source(lambda_client, stream_arn: str) -> None:
    existing = lambda_client.list_event_source_mappings(FunctionName=FUNCTION_NAME)
    for mapping in existing["EventSourceMappings"]:
        if mapping.get("EventSourceArn") == stream_arn:
            print(f"[lambda] Stream event source already mapped (UUID {mapping['UUID']}, state {mapping['State']}).")
            return

    window = int(os.environ.get("INTAKE_BATCH_WINDOW_SECONDS", "15"))
    print(f"[lambda] Creating DynamoDB Stream event source mapping (batching window {window}s)...")
    resp = lambda_client.create_event_source_mapping(
        EventSourceArn=stream_arn,
        FunctionName=FUNCTION_NAME,
        StartingPosition="LATEST",
        BatchSize=100,
        MaximumBatchingWindowInSeconds=window,
        BisectBatchOnFunctionError=False,
        MaximumRetryAttempts=2,
        FunctionResponseTypes=["ReportBatchItemFailures"],
    )
    print(f"[lambda] Event source mapping created: {resp['UUID']} (state: {resp['State']})")


def get_intake_stream_arn(dynamodb_client) -> str:
    desc = dynamodb_client.describe_table(TableName=config.INTAKE_EVENTS_TABLE)["Table"]
    stream_arn = desc.get("LatestStreamArn")
    if not stream_arn:
        print(
            f"ERROR: Table '{config.INTAKE_EVENTS_TABLE}' has no Stream enabled. "
            "Run scripts/setup_intake_infra.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return stream_arn


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    for name, env_var in (
        (config.PRIOR_AUTH_TABLE, "PRIOR_AUTH_TABLE"),
        (config.PATIENTS_TABLE, "PATIENTS_TABLE"),
        (config.INTAKE_EVENTS_TABLE, "INTAKE_EVENTS_TABLE"),
    ):
        if not name or name.endswith("-local"):
            print(f"ERROR: {env_var} is not a real table name ('{name}'). Run the setup_*_infra.py scripts first.", file=sys.stderr)
            sys.exit(1)

    if not config.AGENT_RUNTIME_ARN:
        print(
            "NOTE: AGENT_RUNTIME_ARN is not set - this is expected (AgentCore Runtime is "
            "not deployed yet, per the deferred `cdk deploy` decision). This Lambda will "
            "deploy and run, but every batch will log 'agent.invoke.skipped.no_runtime_arn' "
            "and produce no case until AgentCore Runtime exists.\n"
        )

    print("[package] Building deployment zip...")
    zip_bytes = build_zip()
    print(f"[package] Zip size: {len(zip_bytes) / 1024:.1f} KB")

    iam_client = aws_clients._session().client("iam")  # noqa: SLF001
    role_arn = ensure_role(iam_client)
    print(f"[iam] Role ARN: {role_arn}")

    lambda_client = aws_clients.lambda_client()
    function_arn = ensure_function(lambda_client, role_arn, zip_bytes)
    print(f"[lambda] Function ARN: {function_arn}")

    ddb_client = aws_clients._session().client("dynamodb")  # noqa: SLF001
    stream_arn = get_intake_stream_arn(ddb_client)
    ensure_stream_event_source(lambda_client, stream_arn)

    print("\nDone.")


if __name__ == "__main__":
    main()
