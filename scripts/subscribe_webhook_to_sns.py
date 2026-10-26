#!/usr/bin/env python3
"""Subscribe the CareRelay-WebhookReceiver Lambda to the CareRelay-InboundTopic
SNS topic, and grant SNS permission to invoke it.

This is the final wiring step so that once AWS End User Messaging Social
is configured with this topic as its WABA event destination (a manual
console step - see scripts/deploy_webhook_receiver.py's docstring and
README), inbound WhatsApp messages actually reach webhook_receiver.

Usage:
    python scripts/subscribe_webhook_to_sns.py
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
FUNCTION_NAME = "CareRelay-WebhookReceiver"
STATEMENT_ID = "CareRelaySnsInvoke"


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    sts = aws_clients._session().client("sts")  # noqa: SLF001
    account_id = sts.get_caller_identity()["Account"]
    region = config.AWS_REGION
    topic_arn = f"arn:aws:sns:{region}:{account_id}:{TOPIC_NAME}"

    lambda_client = aws_clients.lambda_client()
    try:
        fn = lambda_client.get_function(FunctionName=FUNCTION_NAME)
    except lambda_client.exceptions.ResourceNotFoundException:
        print(
            f"ERROR: Lambda function '{FUNCTION_NAME}' not found. Run "
            "scripts/deploy_webhook_receiver.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    function_arn = fn["Configuration"]["FunctionArn"]

    print(f"[lambda] Granting SNS invoke permission on '{FUNCTION_NAME}'...")
    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId=STATEMENT_ID,
            Action="lambda:InvokeFunction",
            Principal="sns.amazonaws.com",
            SourceArn=topic_arn,
        )
        print("[lambda] Permission granted.")
    except lambda_client.exceptions.ResourceConflictException:
        print("[lambda] Permission already granted, skipping.")

    sns_client = aws_clients._session().client("sns")  # noqa: SLF001
    existing = sns_client.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]
    already_subscribed = any(
        s["Protocol"] == "lambda" and s["Endpoint"] == function_arn for s in existing
    )
    if already_subscribed:
        print(f"[sns] '{FUNCTION_NAME}' is already subscribed to '{TOPIC_NAME}'.")
    else:
        print(f"[sns] Subscribing '{FUNCTION_NAME}' to '{TOPIC_NAME}'...")
        resp = sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol="lambda",
            Endpoint=function_arn,
        )
        print(f"[sns] Subscription ARN: {resp['SubscriptionArn']}")

    print(
        "\nDone. SNS -> webhook_receiver wiring is complete.\n"
        "REMAINING MANUAL STEP (cannot be scripted): in the AWS console, "
        "under AWS End User Messaging Social, link a WhatsApp Business "
        "Account (WABA) and set this topic as its event destination:\n"
        f"  {topic_arn}\n"
        "See 'Add a message and event destination to AWS End User Messaging "
        "Social' in the AWS docs."
    )


if __name__ == "__main__":
    main()
