#!/usr/bin/env python3
"""One-time local setup: create the real StaffUsersTable in DynamoDB and
verify the SES sender identity, using the MAIN AWS credentials (NOT the
Bedrock-only split credentials - DynamoDB/SES calls always go through
common.aws_clients._session(), never _bedrock_session()).

This is intentionally separate from `cdk deploy` - per project decision,
the full CDK stack (AgentCore Runtime, ECR, API Gateway, etc - the costed
resources) is deferred to the end. This script only touches two cheap,
pay-per-request/zero-cost resources so the signup/login flow and onboarding
email can be tested against real AWS right now:

    1. DynamoDB table matching StorageStack's StaffUsersTable definition
       (composite key hospital_id/username, PAY_PER_REQUEST) - see
       cdk/stacks/storage_stack.py. If `cdk deploy` is run later, the CDK
       table is a separate resource; re-point STAFF_USERS_TABLE in .env at
       whichever one you want to use (CDK will create its own by default).
    2. An SES email identity for config.SES_SENDER (verification email is
       sent to that inbox - owner must click the link before SendEmail
       will work. See scripts/check_ses_identity.py to poll status).

Usage:
    python scripts/setup_auth_infra.py
    python scripts/setup_auth_infra.py --table-only
    python scripts/setup_auth_infra.py --ses-only
"""
import argparse
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
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402


def create_staff_users_table(table_name: str) -> None:
    client = aws_clients._session().client("dynamodb")  # noqa: SLF001 - main session, never Bedrock

    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")
        return

    print(f"[dynamodb] Creating table '{table_name}' (composite key hospital_id/username, on-demand billing)...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "hospital_id", "AttributeType": "S"},
            {"AttributeName": "username", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "hospital_id", "KeyType": "HASH"},
            {"AttributeName": "username", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    waiter = client.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    print(f"[dynamodb] Table '{table_name}' is ACTIVE.")


def verify_ses_identity(email: str) -> None:
    client = aws_clients.ses()  # sesv2, main session

    try:
        existing = client.get_email_identity(EmailIdentity=email)
        status = existing.get("VerifiedForSendingStatus")
        print(f"[ses] Identity '{email}' already registered. VerifiedForSendingStatus={status}")
        if not status:
            print(
                "[ses] Not yet verified - check the inbox for the AWS verification email and click the link, "
                "or run scripts/check_ses_identity.py to poll."
            )
        return
    except client.exceptions.NotFoundException:
        pass

    print(f"[ses] Creating SES email identity for '{email}' (verification email will be sent)...")
    client.create_email_identity(EmailIdentity=email)
    print(
        f"[ses] Verification email sent to {email}. SendEmail calls (audit report + onboarding "
        "email) will fail with MessageRejected until that email is opened and the verification "
        "link is clicked."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table-only", action="store_true", help="Only create the DynamoDB table.")
    parser.add_argument("--ses-only", action="store_true", help="Only verify the SES sender identity.")
    args = parser.parse_args()

    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print(
            "ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env (main credentials, "
            "not BEDROCK_AWS_ACCESS_KEY_ID). Refusing to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    do_table = not args.ses_only
    do_ses = not args.table_only

    if do_table:
        table_name = config.STAFF_USERS_TABLE
        if not table_name or table_name.endswith("-local"):
            print(
                "ERROR: STAFF_USERS_TABLE is not set to a real table name in .env "
                f"(currently '{table_name}'). Set STAFF_USERS_TABLE=CareRelay-StaffUsersTable "
                "(or any name you like) in .env first.",
                file=sys.stderr,
            )
            sys.exit(1)
        create_staff_users_table(table_name)

    if do_ses:
        if not config.SES_SENDER:
            print("ERROR: SES_SENDER is not set in .env.", file=sys.stderr)
            sys.exit(1)
        verify_ses_identity(config.SES_SENDER)


if __name__ == "__main__":
    main()
