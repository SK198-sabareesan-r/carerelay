#!/usr/bin/env python3
"""Check whether config.SES_SENDER has completed SES email-identity
verification yet (the user must click the link AWS emailed them - this
script can't do that step, only report status).

Usage:
    python scripts/check_ses_identity.py
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
    email = config.SES_SENDER
    if not email:
        print("SES_SENDER is not set in .env.", file=sys.stderr)
        sys.exit(1)

    client = aws_clients.ses()
    try:
        resp = client.get_email_identity(EmailIdentity=email)
    except client.exceptions.NotFoundException:
        print(f"No SES identity found for '{email}'. Run scripts/setup_auth_infra.py --ses-only first.")
        sys.exit(1)

    verified = resp.get("VerifiedForSendingStatus")
    print(f"Identity: {email}")
    print(f"VerifiedForSendingStatus: {verified}")
    if verified:
        print("Ready to send - SendEmail calls from this identity will succeed.")
    else:
        print("NOT verified yet - open the inbox and click the AWS SES verification link, then re-run this check.")

    account = client.get_account()
    print(f"Account sending enabled: {account.get('SendingEnabled')}")
    print(f"Production access enabled: {account.get('ProductionAccessEnabled')}")
    if not account.get("ProductionAccessEnabled"):
        print(
            "NOTE: this account is in the SES sandbox - you can only send to OTHER verified "
            "identities until production access is requested/granted. For a hackathon demo, "
            "verify each recipient address you plan to send to (e.g. your own test inbox) the "
            "same way: client.create_email_identity(EmailIdentity=<address>)."
        )


if __name__ == "__main__":
    main()
