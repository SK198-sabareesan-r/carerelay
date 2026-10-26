#!/usr/bin/env python3
"""Create the InboundTopic SNS topic directly via boto3, bypassing `cdk
deploy` (deferred per project decision - see scripts/setup_auth_infra.py
and scripts/setup_case_infra.py for the same pattern).

Matches cdk/stacks/messaging_stack.py's InboundTopic definition - this is
the topic AWS End User Messaging Social's WhatsApp Business Account (WABA)
event destination would be pointed at in a full deployment, fanning out
inbound patient messages to the webhook_receiver Lambda. Creating it now
(ahead of webhook_receiver's own deployment) lets the SNS topic ARN exist
and be referenced/tested independently.

Usage:
    python scripts/setup_sns_topic.py
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

TOPIC_NAME = "CareRelay-InboundTopic"
DISPLAY_NAME = "CareRelay inbound patient intake events"


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    sns_client = aws_clients._session().client("sns")  # noqa: SLF001

    print(f"[sns] Creating (or reusing) topic '{TOPIC_NAME}'...")
    resp = sns_client.create_topic(
        Name=TOPIC_NAME,
        Attributes={"DisplayName": DISPLAY_NAME},
    )
    topic_arn = resp["TopicArn"]
    print(f"[sns] Topic ARN: {topic_arn}")
    print(
        "\nSet this as the WABA event destination SNS topic once AWS End User "
        "Messaging Social is configured (see cdk/stacks/messaging_stack.py for "
        "the original CDK-managed definition)."
    )


if __name__ == "__main__":
    main()
