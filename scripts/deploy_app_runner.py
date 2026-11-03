#!/usr/bin/env python3
"""Deploy the CareRelay agent container (pushed to ECR by
scripts/push_agent_ecr.py) as an AWS App Runner service.

Why App Runner and not AgentCore Runtime: the AgentCore maxAgents quota on
this account is 0 (needs an AWS support ticket), so the agent is hosted on
App Runner instead - a plain always-on HTTPS container. The channel_dispatcher
Lambda invokes it via AGENT_RUNNER_URL (see handler._invoke_agent_http); the
agent's BedrockAgentCoreApp serves POST /invocations on port 8080.

This script (idempotent):
  1. Ensures two IAM roles:
       CareRelay-AppRunnerECRRole  (App Runner pulls the image from ECR)
       CareRelay-AppRunnerTaskRole (the running container's AWS permissions:
                                    S3 media read, Transcribe, Bedrock invoke)
  2. Creates the App Runner service from <ecr>/carerelay-agent:latest, or
     starts a new deployment if the service already exists.
  3. Injects the runtime env/config from .env - INCLUDING the Bedrock-only
     credentials (BEDROCK_AWS_ACCESS_KEY_ID/SECRET) so the agent can invoke
     Bedrock models, plus MEDIA_BUCKET, table names, region, model ids.
  4. Writes the resulting https URL back into .env as AGENT_RUNNER_URL and
     prints it (feed it to scripts/deploy_channel_dispatcher.py).

Usage:
    python scripts/deploy_app_runner.py
"""
import json
import os
import re
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = re.match(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            if value:
                os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402

SERVICE_NAME = "carerelay-agent"
REPO_NAME = "carerelay-agent"
TAG = "latest"
ECR_ROLE = "CareRelay-AppRunnerECRRole"
TASK_ROLE = "CareRelay-AppRunnerTaskRole"
PORT = "8080"


def _ensure_ecr_access_role(iam) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow",
                       "Principal": {"Service": "build.apprunner.amazonaws.com"},
                       "Action": "sts:AssumeRole"}],
    }
    try:
        arn = iam.get_role(RoleName=ECR_ROLE)["Role"]["Arn"]
        print(f"[iam] Role '{ECR_ROLE}' exists: {arn}")
    except iam.exceptions.NoSuchEntityException:
        print(f"[iam] Creating '{ECR_ROLE}'...")
        arn = iam.create_role(RoleName=ECR_ROLE,
                              AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        time.sleep(10)
    iam.attach_role_policy(
        RoleName=ECR_ROLE,
        PolicyArn="arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess",
    )
    return arn


def _ensure_task_role(iam) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow",
                       "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                       "Action": "sts:AssumeRole"}],
    }
    try:
        arn = iam.get_role(RoleName=TASK_ROLE)["Role"]["Arn"]
        print(f"[iam] Role '{TASK_ROLE}' exists: {arn}")
    except iam.exceptions.NoSuchEntityException:
        print(f"[iam] Creating '{TASK_ROLE}'...")
        arn = iam.create_role(RoleName=TASK_ROLE,
                              AssumeRolePolicyDocument=json.dumps(trust))["Role"]["Arn"]
        time.sleep(10)
    region = config.AWS_REGION
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "S3MediaRead", "Effect": "Allow",
             "Action": ["s3:GetObject", "s3:PutObject"],
             "Resource": [f"arn:aws:s3:::{config.MEDIA_BUCKET}/*"]},
            {"Sid": "Transcribe", "Effect": "Allow",
             "Action": ["transcribe:StartTranscriptionJob", "transcribe:GetTranscriptionJob"],
             "Resource": "*"},
            {"Sid": "Bedrock", "Effect": "Allow",
             "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"],
             "Resource": "*"},
            {"Sid": "DynamoRules", "Effect": "Allow",
             "Action": ["dynamodb:Scan", "dynamodb:GetItem"],
             "Resource": [f"arn:aws:dynamodb:{region}:*:table/{config.PAYER_RULES_TABLE}"]},
        ],
    }
    iam.put_role_policy(RoleName=TASK_ROLE, PolicyName="CareRelayAppRunnerTaskAccess",
                        PolicyDocument=json.dumps(policy))
    return arn


def _runtime_env() -> dict:
    """Runtime env vars baked into the App Runner service. Includes the
    Bedrock-only credentials so the agent can invoke Bedrock models even
    though the task role's account key cannot (the documented split)."""
    env = {
        "AWS_REGION": config.AWS_REGION,
        "MEDIA_BUCKET": config.MEDIA_BUCKET,
        "PAYER_RULES_TABLE": config.PAYER_RULES_TABLE,
        "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", ""),
        "BEDROCK_VISION_MODEL_ID": os.environ.get("BEDROCK_VISION_MODEL_ID", ""),
        "BEDROCK_REGION": os.environ.get("BEDROCK_REGION", ""),
        "TRANSCRIBE_REGION": os.environ.get("TRANSCRIBE_REGION", ""),
        "LOG_LEVEL": config.LOG_LEVEL,
    }
    # Bedrock split credentials (optional) - only if set.
    for k in ("BEDROCK_AWS_ACCESS_KEY_ID", "BEDROCK_AWS_SECRET_ACCESS_KEY", "BEDROCK_AWS_SESSION_TOKEN"):
        v = os.environ.get(k, "")
        if v:
            env[k] = v
    # Main credentials so S3/Transcribe/DynamoDB work even if the task role
    # propagation lags (the agent's aws_clients prefers explicit keys).
    env["AWS_ACCESS_KEY_ID"] = config.AWS_ACCESS_KEY_ID
    env["AWS_SECRET_ACCESS_KEY"] = config.AWS_SECRET_ACCESS_KEY
    return {k: v for k, v in env.items() if v}


def _write_runner_url_to_env(url: str) -> None:
    env_path = os.path.join(_REPO_ROOT, ".env")
    lines = []
    found = False
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if re.match(r"^\s*AGENT_RUNNER_URL\s*=", line):
                lines.append(f"AGENT_RUNNER_URL={url}\n")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"\nAGENT_RUNNER_URL={url}\n")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print(f"[env] Wrote AGENT_RUNNER_URL={url} into .env")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    session = aws_clients._session()  # noqa: SLF001 - main session, never Bedrock
    account_id = session.client("sts").get_caller_identity()["Account"]
    region = config.AWS_REGION
    image_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{REPO_NAME}:{TAG}"
    iam = session.client("iam")
    apprunner = session.client("apprunner")

    ecr_role_arn = _ensure_ecr_access_role(iam)
    task_role_arn = _ensure_task_role(iam)
    print("[iam] Waiting for role propagation...")
    time.sleep(8)

    env_vars = _runtime_env()
    print(f"[apprunner] Runtime env keys: {sorted(env_vars.keys())}")

    # Already exists? -> start a new deployment.
    existing = apprunner.list_services().get("ServiceSummaryList", [])
    svc = next((s for s in existing if s["ServiceName"] == SERVICE_NAME), None)
    if svc:
        print(f"[apprunner] Service exists ({svc['Status']}); starting a new deployment...")
        apprunner.start_deployment(ServiceArn=svc["ServiceArn"])
        service_arn = svc["ServiceArn"]
        service_url = apprunner.describe_service(ServiceArn=service_arn)["Service"]["ServiceUrl"]
    else:
        print(f"[apprunner] Creating service '{SERVICE_NAME}' from {image_uri}...")
        resp = apprunner.create_service(
            ServiceName=SERVICE_NAME,
            SourceConfiguration={
                "AuthenticationConfiguration": {"AccessRoleArn": ecr_role_arn},
                "AutoDeploymentsEnabled": False,
                "ImageRepository": {
                    "ImageIdentifier": image_uri,
                    "ImageRepositoryType": "ECR",
                    "ImageConfiguration": {
                        "Port": PORT,
                        "RuntimeEnvironmentVariables": env_vars,
                    },
                },
            },
            InstanceConfiguration={
                "Cpu": "1 vCPU",
                "Memory": "2 GB",
                "InstanceRoleArn": task_role_arn,
            },
            HealthCheckConfiguration={
                "Protocol": "TCP", "Interval": 10, "Timeout": 5,
                "HealthyThreshold": 1, "UnhealthyThreshold": 5,
            },
        )
        service_arn = resp["Service"]["ServiceArn"]
        service_url = resp["Service"]["ServiceUrl"]

    full_url = f"https://{service_url}"
    print(f"[apprunner] Service ARN: {service_arn}")
    print(f"[apprunner] Service URL: {full_url}")
    _write_runner_url_to_env(full_url)
    print("\nDone. App Runner is provisioning (a few minutes to RUNNING).")
    print("Next: python scripts/deploy_channel_dispatcher.py  (now picks up AGENT_RUNNER_URL).")


if __name__ == "__main__":
    main()
