#!/usr/bin/env python3
"""Seed the deployed PayerRulesTable from seed/payer_rules.json.

This is the deterministic rule data behind every prior-authorization
decision in CareRelay (see agent_app/rules_engine.py). Run this once after
`cdk deploy` so the real table has rule data instead of silently falling
back to rules_engine.py's in-code fallback set.

Usage:
    python scripts/seed_payer_rules.py
    python scripts/seed_payer_rules.py --table CareRelay-Storage-PayerRulesTable...
    python scripts/seed_payer_rules.py --file seed/payer_rules.json --dry-run

Credentials: uses the same resolution as the rest of the project
(lambdas/common/aws_clients.py) - set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY
or AWS_PROFILE in .env. This script loads .env itself, the same way
cdk/app.py does, so you don't need to export anything into your shell first.
"""
import argparse
import json
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_SEED_FILE = os.path.join(_REPO_ROOT, "seed", "payer_rules.json")

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


def load_rules(seed_file: str) -> list:
    with open(seed_file, "r", encoding="utf-8") as fh:
        rules = json.load(fh)
    for rule in rules:
        missing = {"payer_id", "cpt_code", "rule_id", "requires_prior_auth"} - set(rule)
        if missing:
            raise ValueError(f"Rule {rule} is missing required fields: {missing}")
    return rules


def seed(table_name: str, rules: list, dry_run: bool = False) -> None:
    if dry_run:
        print(f"[dry-run] Would write {len(rules)} rule(s) to table '{table_name}':")
        for r in rules:
            print(f"  - {r['rule_id']}: {r['payer_id']} / {r['cpt_code']} -> {r['procedure_name']}")
        return

    table = aws_clients.dynamodb_resource().Table(table_name)
    with table.batch_writer(overwrite_by_pkeys=["payer_id", "cpt_code"]) as batch:
        for rule in rules:
            batch.put_item(Item=rule)
    print(f"Seeded {len(rules)} payer rule(s) into '{table_name}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--table",
        default=config.PAYER_RULES_TABLE,
        help="PayerRulesTable name (defaults to PAYER_RULES_TABLE from .env/config, "
        "or the 'PayerRulesTableName' CDK stack output).",
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
    args = parser.parse_args()

    if not args.table or args.table.endswith("-local"):
        print(
            "ERROR: no real table name configured. Pass --table <PayerRulesTableName> "
            "(from the CDK 'CareRelay-Storage' stack output) or set PAYER_RULES_TABLE in .env.",
            file=sys.stderr,
        )
        sys.exit(1)

    rules = load_rules(args.file)
    seed(args.table, rules, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
