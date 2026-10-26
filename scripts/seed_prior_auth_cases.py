#!/usr/bin/env python3
"""Seed the deployed PriorAuthTable from seed/prior_auth_cases.json.

This is demo case data - the same five cases frontend/src/lib/mockData.ts
has used all along (so mock mode and live mode show consistent names/cases),
plus three additional cases reaching further back in time so the Intake
Queue's date-range filter has real data to demonstrate.

Each entry's `days_ago`/`minutes_ago` is resolved to a real created_at
timestamp at seed time (relative to "now"), and each activity_log entry's
`offset_minutes` is resolved to an absolute timestamp relative to that
case's created_at - so re-running this script always produces a case list
that looks like genuine recent activity, not a frozen historical snapshot.

Usage:
    python scripts/seed_prior_auth_cases.py
    python scripts/seed_prior_auth_cases.py --dry-run
"""
import argparse
import datetime
import json
import os
import re
import sys
from decimal import Decimal

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_SEED_FILE = os.path.join(_REPO_ROOT, "seed", "prior_auth_cases.json")

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


def _iso(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _decimalize(obj):
    """DynamoDB's boto3 resource layer rejects native Python floats - every
    numeric value (e.g. extracted_card.confidence) must be a Decimal."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimalize(v) for v in obj]
    return obj


def build_item(raw: dict, now: datetime.datetime) -> dict:
    created_at = now - datetime.timedelta(days=raw["days_ago"], minutes=raw["minutes_ago"])

    activity_log = []
    for entry in raw.get("activity_log", []):
        ts = created_at + datetime.timedelta(minutes=entry["offset_minutes"])
        activity_log.append({
            "timestamp": _iso(ts),
            "event": entry["event"],
            "actor": entry["actor"],
            "detail": entry["detail"],
        })

    return _decimalize({
        "case_id": raw["case_id"],
        "created_at": _iso(created_at),
        "status": raw["status"],
        "channel": raw["channel"],
        "patient_name": raw["patient_name"],
        "patient_phone_masked": raw["patient_phone_masked"],
        "cpt_code": raw["cpt_code"],
        "procedure_name": raw["procedure_name"],
        "payer_id": raw["payer_id"],
        "extracted_card": raw["extracted_card"],
        "verification": raw["verification"],
        "messages": raw["messages"],
        "perceived_facts": raw["perceived_facts"],
        "activity_log": activity_log,
    })


def load_cases(seed_file: str) -> list:
    with open(seed_file, "r", encoding="utf-8") as fh:
        return json.load(fh)


def seed(table_name: str, cases: list, dry_run: bool = False) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    items = [build_item(c, now) for c in cases]

    if dry_run:
        print(f"[dry-run] Would write {len(items)} case(s) to table '{table_name}':")
        for i in items:
            print(f"  - {i['case_id']}: {i['patient_name']} ({i['status']}) created_at={i['created_at']}")
        return

    table = aws_clients.dynamodb_resource().Table(table_name)
    for item in items:
        table.put_item(Item=item)
    print(f"Seeded {len(items)} prior-auth case(s) into '{table_name}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        default=config.PRIOR_AUTH_TABLE,
        help="PriorAuthTable name (defaults to PRIOR_AUTH_TABLE from .env/config).",
    )
    parser.add_argument(
        "--file",
        default=_DEFAULT_SEED_FILE,
        help=f"Path to the seed JSON file (default: {_DEFAULT_SEED_FILE}).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print without writing.")
    args = parser.parse_args()

    if not args.table or args.table.endswith("-local"):
        print(
            "ERROR: no real table name configured. Pass --table <PriorAuthTableName> "
            "or set PRIOR_AUTH_TABLE in .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    cases = load_cases(args.file)
    seed(args.table, cases, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
