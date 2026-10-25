"""Shared Bedrock model configuration for all CareRelay agents.

A single place to point every agent at the same (configurable) Bedrock model,
so swapping BEDROCK_MODEL_ID changes the whole system consistently.

IMPORTANT: this builds the Strands BedrockModel using the SAME boto3 session
as the rest of the project (lambdas/common/aws_clients.py), instead of
letting Strands construct its own bare boto3.Session(). That session
resolution is what makes explicit AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY in
.env take priority over any CLI profile (and correctly clears a blank
AWS_PROFILE env var, which otherwise makes boto3 raise ProfileNotFound).
Bypassing it here would silently fall back to whatever credentials boto3's
default chain finds, exactly the ambient-account risk this project avoids.
"""
from strands.models import BedrockModel

from lambdas.common import aws_clients, config


def default_model() -> BedrockModel:
    # Uses aws_clients._bedrock_session(), which is the SEPARATE Bedrock-only
    # credential set (config.BEDROCK_AWS_ACCESS_KEY_ID) if one is configured
    # in .env, falling back to the main session otherwise. This matters
    # because an account/key can be restricted from Bedrock while still
    # being valid for every other AWS service this project uses.
    #
    # Strands' BedrockModel rejects passing both `boto_session` and
    # `region_name` together (the session already carries a region). If
    # BEDROCK_REGION differs from AWS_REGION, override via
    # boto_client_config instead - the one region override BedrockModel
    # accepts alongside boto_session.
    session = aws_clients._bedrock_session()
    kwargs = {"model_id": config.BEDROCK_MODEL_ID, "boto_session": session}
    if config.BEDROCK_REGION and config.BEDROCK_REGION != config.AWS_REGION:
        from botocore.config import Config

        kwargs["boto_client_config"] = Config(region_name=config.BEDROCK_REGION)
    return BedrockModel(**kwargs)
