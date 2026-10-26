#!/usr/bin/env python3
"""One-time local setup: create IntakeEventsTable (with DynamoDB Stream) and
PatientsTable directly via boto3, bypassing `cdk deploy` (deferred - see
scripts/setup_auth_infra.py and scripts/setup_case_infra.py for the same
pattern already applied to the other tables).

Matches cdk/stacks/storage_stack.py's definitions:
    IntakeEventsTable - composite key pk/sk, NEW_IMAGE stream, ttl attribute
    PatientsTable     - partition key patient_id

The IntakeEventsTable's Stream ARN is required by
scripts/deploy_channel_dispatcher.py to wire the DynamoDB Stream event
source - this script prints it at the end.

Usage:
    python scripts/setup_intake_infra.py
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


def create_intake_events_table(table_name: str) -> str:
    client = aws_clients._session().client("dynamodb")  # noqa: SLF001 - main session, never Bedrock

    existing = client.list_tables().get("TableNames", [])
    if table_name not in existing:
        print(f"[dynamodb] Creating table '{table_name}' (pk/sk, NEW_IMAGE stream, on-demand billing)...")
        client.create_table(
            TableName=table_name,
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
            StreamSpecification={"StreamEnabled": True, "StreamViewType": "NEW_IMAGE"},
        )
        client.get_waiter("table_exists").wait(TableName=table_name)
        print(f"[dynamodb] Table '{table_name}' is ACTIVE.")

        print("[dynamodb] Enabling TTL on 'ttl' attribute...")
        client.update_time_to_live(
            TableName=table_name,
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "ttl"},
        )
    else:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")

    desc = client.describe_table(TableName=table_name)["Table"]
    stream_arn = desc.get("LatestStreamArn")
    if not stream_arn:
        raise RuntimeError(
            f"Table '{table_name}' exists but has no Stream enabled. Streams can't be "
            "added to an existing table without recreating it - delete and re-run this "
            "script, or enable the stream manually in the console."
        )
    return stream_arn


def create_patients_table(table_name: str) -> None:
    client = aws_clients._session().client("dynamodb")  # noqa: SLF001

    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")
        return

    print(f"[dynamodb] Creating table '{table_name}' (partition key patient_id, on-demand billing)...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "patient_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "patient_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    print(f"[dynamodb] Table '{table_name}' is ACTIVE.")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    for name, env_var in (
        (config.INTAKE_EVENTS_TABLE, "INTAKE_EVENTS_TABLE"),
        (config.PATIENTS_TABLE, "PATIENTS_TABLE"),
    ):
        if not name or name.endswith("-local"):
            print(
                f"ERROR: {env_var} is not set to a real table name in .env (currently '{name}'). "
                f"Set {env_var}=CareRelay-{env_var.replace('_', '')} in .env first.",
                file=sys.stderr,
            )
            sys.exit(1)

    stream_arn = create_intake_events_table(config.INTAKE_EVENTS_TABLE)
    create_patients_table(config.PATIENTS_TABLE)

    print(f"\nIntakeEventsTable Stream ARN: {stream_arn}")
    print("Pass this to scripts/deploy_channel_dispatcher.py --stream-arn, or it will look it up itself.")


if __name__ == "__main__":
    main()
