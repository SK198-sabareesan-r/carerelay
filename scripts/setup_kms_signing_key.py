#!/usr/bin/env python3
"""Recreate the asymmetric KMS signing key used to sign CareRelay audit
reports (the teardown deleted the original). Matches
cdk/stacks/storage_stack.py's ReportSigningKey: RSA_2048, SIGN_VERIFY,
alias 'carerelay-report-signing'.

Writes the key id back into .env as KMS_SIGNING_KEY_ID and prints it.
Idempotent - reuses the existing alias/key if present.

Uses the MAIN .env credentials only (never the Bedrock split keys).

Usage:
    python scripts/setup_kms_signing_key.py
"""
import os
import re
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))

ALIAS = "alias/carerelay-report-signing"


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


def _write_env(key_id: str) -> None:
    env_path = os.path.join(_REPO_ROOT, ".env")
    lines, found = [], False
    with open(env_path, "r", encoding="utf-8") as fh:
        for line in fh:
            if re.match(r"^\s*KMS_SIGNING_KEY_ID\s*=", line):
                lines.append(f"KMS_SIGNING_KEY_ID={key_id}\n")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"\nKMS_SIGNING_KEY_ID={key_id}\n")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print(f"[env] Wrote KMS_SIGNING_KEY_ID={key_id} into .env")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    kms = aws_clients._session().client("kms")  # noqa: SLF001 - main session, never Bedrock

    # Reuse if the alias already points at a key.
    try:
        for a in kms.list_aliases().get("Aliases", []):
            if a["AliasName"] == ALIAS and a.get("TargetKeyId"):
                key_id = a["TargetKeyId"]
                print(f"[kms] Alias '{ALIAS}' already -> key {key_id}; reusing.")
                _write_env(key_id)
                return
    except Exception as exc:  # noqa: BLE001
        print(f"[kms] list_aliases warning: {exc}")

    print("[kms] Creating RSA_2048 SIGN_VERIFY key...")
    resp = kms.create_key(
        KeyUsage="SIGN_VERIFY",
        KeySpec="RSA_2048",
        Description="Signs CareRelay prior-auth audit reports.",
    )
    key_id = resp["KeyMetadata"]["KeyId"]
    kms.create_alias(AliasName=ALIAS, TargetKeyId=key_id)
    print(f"[kms] Created key {key_id} with alias '{ALIAS}'.")
    _write_env(key_id)


if __name__ == "__main__":
    main()
