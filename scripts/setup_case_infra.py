#!/usr/bin/env python3
"""One-time local setup: create the PriorAuthTable and PayerRulesTable in
DynamoDB directly (bypassing `cdk deploy`, which is deferred - see
scripts/setup_auth_infra.py for the same pattern applied to StaffUsersTable).

Uses the MAIN AWS credentials (never the Bedrock-only split credentials -
DynamoDB calls always go through common.aws_clients._session()).

Tables created here match cdk/stacks/storage_stack.py's definitions:
    PriorAuthTable  - partition key case_id, PAY_PER_REQUEST
    PayerRulesTable - partition key payer_id, sort key cpt_code, PAY_PER_REQUEST

When `cdk deploy` eventually runs, it creates SEPARATE tables with
CDK-generated names - re-point PRIOR_AUTH_TABLE/PAYER_RULES_TABLE in .env at
whichever should be live.

Usage:
    python scripts/setup_case_infra.py
"""
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


def create_prior_auth_table(table_name: str) -> None:
    client = aws_clients._session().client("dynamodb")  # noqa: SLF001 - main session, never Bedrock

    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")
        return

    print(f"[dynamodb] Creating table '{table_name}' (partition key case_id, on-demand billing)...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "case_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "case_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    print(f"[dynamodb] Table '{table_name}' is ACTIVE.")


def create_payer_rules_table(table_name: str) -> None:
    client = aws_clients._session().client("dynamodb")  # noqa: SLF001

    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")
        return

    print(f"[dynamodb] Creating table '{table_name}' (partition key payer_id, sort key cpt_code, on-demand billing)...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "payer_id", "AttributeType": "S"},
            {"AttributeName": "cpt_code", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "payer_id", "KeyType": "HASH"},
            {"AttributeName": "cpt_code", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    print(f"[dynamodb] Table '{table_name}' is ACTIVE.")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print(
            "ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env (main credentials, "
            "not BEDROCK_AWS_ACCESS_KEY_ID). Refusing to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    for name, env_var in (
        (config.PRIOR_AUTH_TABLE, "PRIOR_AUTH_TABLE"),
        (config.PAYER_RULES_TABLE, "PAYER_RULES_TABLE"),
    ):
        if not name or name.endswith("-local"):
            print(
                f"ERROR: {env_var} is not set to a real table name in .env (currently '{name}'). "
                f"Set {env_var}=CareRelay-{env_var.replace('_', '')} in .env first.",
                file=sys.stderr,
            )
            sys.exit(1)

    create_prior_auth_table(config.PRIOR_AUTH_TABLE)
    create_payer_rules_table(config.PAYER_RULES_TABLE)


if __name__ == "__main__":
    main()
