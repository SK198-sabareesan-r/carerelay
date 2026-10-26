#!/usr/bin/env python3
"""Create the AppointmentsTable directly via boto3, bypassing `cdk deploy`
(deferred - same pattern as the other setup_*_infra.py scripts).

Schema: partition key appointment_id. Items look like:
    {
      "appointment_id": "appt-...",
      "patient_phone": "919500799295",          # bare digits, matches InboundIntakeMessage.sender
      "phone_number_id": "phone-number-id-...", # AWS format, used to send the reminder
      "patient_name": "...",
      "procedure_name": "...",
      "appointment_time": "2026-10-27T10:00:00Z",
      "reminder_sent": false,
      "status": "SCHEDULED" | "RESCHEDULE_REQUESTED",
      "created_at": "...Z",
    }

Usage:
    python scripts/setup_appointments_infra.py
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


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    table_name = config.APPOINTMENTS_TABLE
    if not table_name or table_name.endswith("-local"):
        print(
            f"ERROR: APPOINTMENTS_TABLE is not set to a real table name in .env (currently '{table_name}'). "
            "Set APPOINTMENTS_TABLE=CareRelay-AppointmentsTable in .env first.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = aws_clients._session().client("dynamodb")  # noqa: SLF001
    existing = client.list_tables().get("TableNames", [])
    if table_name in existing:
        print(f"[dynamodb] Table '{table_name}' already exists - skipping create.")
        return

    print(f"[dynamodb] Creating table '{table_name}' (partition key appointment_id, on-demand billing)...")
    client.create_table(
        TableName=table_name,
        AttributeDefinitions=[{"AttributeName": "appointment_id", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "appointment_id", "KeyType": "HASH"}],
        BillingMode="PAY_PER_REQUEST",
    )
    client.get_waiter("table_exists").wait(TableName=table_name)
    print(f"[dynamodb] Table '{table_name}' is ACTIVE.")


if __name__ == "__main__":
    main()
