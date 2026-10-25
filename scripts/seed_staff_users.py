#!/usr/bin/env python3
"""Seed the deployed StaffUsersTable with dummy clinic-staff accounts.

Run this once after `cdk deploy` so the console's /login and /signup pages
have real accounts to sign in with, without you having to sign up manually.
Credentials come from seed/staff_users.json (plaintext passwords ONLY in
this local seed file - never written to DynamoDB in plaintext; this script
hashes each password with the exact same PBKDF2 routine dashboard_api uses
to verify logins, by importing it directly rather than re-implementing it).

Usage:
    python scripts/seed_staff_users.py
    python scripts/seed_staff_users.py --table CareRelay-Storage-StaffUsersTable...
    python scripts/seed_staff_users.py --dry-run

Credentials: uses the same resolution as the rest of the project
(lambdas/common/aws_clients.py) - set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
or AWS_PROFILE in .env. This script loads .env itself.
"""
import argparse
import json
import os
import re
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_SEED_FILE = os.path.join(_REPO_ROOT, "seed", "staff_users.json")

sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))


def _load_dotenv(path: str) -> None:
    """Mirrors cdk/app.py's _load_dotenv - loads .env into os.environ
    without overriding any vars already set in the real shell/CI env."""
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
from dashboard_api.handler import _hash_password, _hospital_id  # noqa: E402 - reuse the real hashing/slug routines
from dashboard_api import onboarding_email  # noqa: E402


_REQUIRED_FIELDS = {
    "hospital_name",
    "hospital_address",
    "hospital_email",
    "hospital_phone",
    "username",
    "password",
    "display_name",
    "role",
}


def load_users(seed_file: str) -> list:
    with open(seed_file, "r", encoding="utf-8") as fh:
        users = json.load(fh)
    for user in users:
        missing = _REQUIRED_FIELDS - set(user)
        if missing:
            raise ValueError(f"User {user.get('username')} is missing required fields: {missing}")
    return users


def seed(table_name: str, users: list, dry_run: bool = False, send_emails: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] Would write {len(users)} staff account(s) to table '{table_name}':")
        for u in users:
            print(f"  - [{u['hospital_name']}] {u['username']} ({u['display_name']}, {u['role']})")
        return

    table = aws_clients.dynamodb_resource().Table(table_name)
    for user in users:
        hashed = _hash_password(user["password"])
        hospital_id = _hospital_id(user["hospital_name"])
        table.put_item(Item={
            "hospital_id": hospital_id,
            "hospital_name": user["hospital_name"],
            "hospital_address": user["hospital_address"],
            "hospital_email": user["hospital_email"],
            "hospital_phone": user["hospital_phone"],
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **hashed,
        })
        if send_emails:
            try:
                onboarding_email.send_onboarding_email(
                    to_address=user["hospital_email"],
                    display_name=user["display_name"],
                    hospital_name=user["hospital_name"],
                    hospital_id=hospital_id,
                    username=user["username"],
                    role=user["role"],
                )
                print(f"  -> onboarding email sent to {user['hospital_email']}")
            except Exception as exc:  # noqa: BLE001
                print(f"  -> onboarding email FAILED for {user['hospital_email']}: {exc}")
    print(f"Seeded {len(users)} staff account(s) into '{table_name}'.")
    print("Passwords are hashed (PBKDF2) before being written - never stored in plaintext.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        default=config.STAFF_USERS_TABLE,
        help="StaffUsersTable name (defaults to STAFF_USERS_TABLE from .env/config, "
        "or the 'StaffUsersTableName' CDK stack output).",
    )
    parser.add_argument(
        "--file",
        default=_DEFAULT_SEED_FILE,
        help=f"Path to the seed JSON file (default: {_DEFAULT_SEED_FILE}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without touching DynamoDB.",
    )
    parser.add_argument(
        "--send-emails",
        action="store_true",
        help="Also send the onboarding email to each account's hospital_email via SES. "
        "Requires SES_SENDER to be a verified identity (see scripts/check_ses_identity.py) "
        "and, while the account is in the SES sandbox, each hospital_email must ALSO be a "
        "verified identity or SendEmail will fail.",
    )
    args = parser.parse_args()

    if not args.table or args.table.endswith("-local"):
        print(
            "ERROR: no real table name configured. Pass --table <StaffUsersTableName> "
            "(from the CDK 'CareRelay-Storage' stack output) or set STAFF_USERS_TABLE in .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    users = load_users(args.file)
    seed(args.table, users, dry_run=args.dry_run, send_emails=args.send_emails)


if __name__ == "__main__":
    main()
