#!/usr/bin/env python3
"""CareRelay CDK application entrypoint.

Stands up the full patient prior-authorization intake network:

    StorageStack    -> S3 (intake media/signed reports) + DynamoDB tables
                       (intake events w/ Stream, patients, prior-auth cases,
                       payer rules) + KMS signing key for the audit report.
    MessagingStack  -> SNS topic that the WABA event destination publishes to.
    ComputeStack    -> the Strands multi-agent backend on Amazon Bedrock
                       AgentCore Runtime (built as a container image), plus
                       two thin Lambdas (webhook_receiver, channel_dispatcher)
                       that handle AWS CDS plumbing (SNS/S3/DynamoDB in,
                       WhatsApp/RCS/SES out) around that single agent call.

A single `cdk deploy --all` provisions everything.

IMPORTANT - account/region resolution:
This project intentionally does NOT rely on the AWS CLI's active/default
profile or CDK's ambient CDK_DEFAULT_ACCOUNT/CDK_DEFAULT_REGION (which are
populated from whatever credentials happen to be active when you run `cdk`).
Instead, the deploy target account/region are resolved the same way the
Lambdas resolve them at runtime - via lambdas/common/aws_clients, which
prefers explicit AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY from your .env over
any CLI profile. This guarantees `cdk deploy` always targets the account
configured in .env, never whatever account your CLI happens to default to.
See docs/DEPLOYMENT.md.
"""
import os
import sys

import aws_cdk as cdk

# Make the repo's lambdas/common package importable so we can reuse its
# credential-resolution logic instead of duplicating it here.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))

from common.dotenv import load_repo_dotenv  # noqa: E402

# CDK does not load .env on its own - without this, `cdk synth`/`cdk deploy`
# would fall back to whatever credentials the environment/CLI happens to
# have active, which is exactly what this project must avoid.
load_repo_dotenv()

from common import aws_clients, config  # noqa: E402

from stacks.storage_stack import StorageStack
from stacks.messaging_stack import MessagingStack
from stacks.compute_stack import ComputeStack


def _resolve_account() -> str:
    """Resolve the target AWS account from OUR credential chain (.env's
    explicit keys, or the configured AWS_PROFILE as a fallback) - not from
    CDK_DEFAULT_ACCOUNT, which reflects whatever the CLI's active profile is."""
    try:
        sts = aws_clients._client("sts")
        return sts.get_caller_identity()["Account"]
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Could not resolve the target AWS account from the credentials "
            "configured in .env (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or "
            "AWS_PROFILE). Set these before running `cdk deploy`. "
            f"Underlying error: {exc}"
        ) from exc


def _env() -> cdk.Environment:
    return cdk.Environment(account=_resolve_account(), region=config.AWS_REGION)


app = cdk.App()
env = _env()

prefix = app.node.try_get_context("prefix") or "CareRelay"

storage = StorageStack(app, f"{prefix}-Storage", env=env)

messaging = MessagingStack(app, f"{prefix}-Messaging", env=env)

ComputeStack(
    app,
    f"{prefix}-Compute",
    media_bucket=storage.media_bucket,
    intake_events_table=storage.intake_events_table,
    patients_table=storage.patients_table,
    prior_auth_table=storage.prior_auth_table,
    payer_rules_table=storage.payer_rules_table,
    staff_users_table=storage.staff_users_table,
    signing_key=storage.signing_key,
    inbound_topic=messaging.inbound_topic,
    env=env,
)

cdk.Tags.of(app).add("project", "CareRelay")
cdk.Tags.of(app).add("hackathon", "aws-cds-agentic-ai")

app.synth()
