#!/usr/bin/env python3
"""Re-create the CareRelayComms inline IAM policy on the IAM user whose keys
are in .env (user 'CDS').

The earlier teardown removed this inline policy, which is why SES / End User
Messaging / Transcribe / etc. calls now fail with AccessDeniedException. This
restores exactly the permissions the CareRelay app needs to run against the
recreated resources. Scoped to the services the project uses; resources are
'*' where the service doesn't support tighter ARNs for these actions (SES
identities, End User Messaging), and otherwise left broad for the demo.

Uses the MAIN .env credentials only (never the Bedrock split keys).

Usage:
    python scripts/setup_iam_permissions.py
"""
import json
import os
import re
import sys

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
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402

IAM_USER = "CDS"
POLICY_NAME = "CareRelayComms"

# Compact policy: IAM user inline policies are capped at 2048 bytes, so
# full-service access is grouped into one wildcard statement and IAM role
# management into a second. Covers every CareRelay deploy/runtime need
# (S3, Lambda, SNS, API Gateway, Amplify, CloudFront, ECR, App Runner, SES,
# End User Messaging WhatsApp+SMS/RCS, Transcribe, KMS, Logs, Support) while
# staying well under the limit.
POLICY_DOCUMENT = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "FullServices",
            "Effect": "Allow",
            "Action": [
                "s3:*", "lambda:*", "sns:*", "apigateway:*", "amplify:*",
                "cloudfront:*", "ecr:*", "apprunner:*", "ses:*",
                "social-messaging:*", "sms-voice:*", "transcribe:*",
                "kms:*", "logs:*", "support:*",
            ],
            "Resource": "*",
        },
        {
            "Sid": "IamForDeploy",
            "Effect": "Allow",
            "Action": [
                "iam:CreateRole", "iam:GetRole", "iam:PutRolePolicy",
                "iam:AttachRolePolicy", "iam:CreatePolicy", "iam:PassRole",
                "iam:ListRolePolicies", "iam:ListAttachedRolePolicies",
                "iam:PutUserPolicy", "iam:ListUserPolicies",
            ],
            "Resource": "*",
        },
    ],
}


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    iam = aws_clients._session().client("iam")  # noqa: SLF001 - main session, never Bedrock
    print(f"[iam] Putting inline policy '{POLICY_NAME}' on user '{IAM_USER}'...")
    iam.put_user_policy(
        UserName=IAM_USER,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(POLICY_DOCUMENT),
    )
    print(f"[iam] Done. '{IAM_USER}' now has the CareRelay service permissions restored.")
    print("[iam] Current inline policies:", iam.list_user_policies(UserName=IAM_USER).get("PolicyNames"))


if __name__ == "__main__":
    main()
