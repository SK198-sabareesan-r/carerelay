"""Lazily-created, cached boto3 clients.

Credential resolution order:
  1. Explicit access key / secret key from config (config.AWS_ACCESS_KEY_ID /
     config.AWS_SECRET_ACCESS_KEY), if both are set. This lets a local .env
     with real keys drive boto3 directly without touching ~/.aws/credentials.
  2. Named AWS CLI profile in config.AWS_PROFILE (set via
     `aws configure --profile <name>`, see docs/DEPLOYMENT.md).
  3. Default boto3 resolution - inside Lambda this is always the function's
     IAM execution role; locally it falls back to ~/.aws/credentials or the
     AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY env vars if boto3 finds them.

Clients are created on first use so importing this module never requires AWS
credentials (important for local unit tests).
"""
import functools
import os

try:
    import boto3
except ImportError:  # pragma: no cover - only hit if boto3 missing locally
    boto3 = None

from . import config


def _require_boto3():
    if boto3 is None:
        raise RuntimeError(
            "boto3 is not installed. It is bundled in Lambda; for local use "
            "run `pip install -r requirements.txt`."
        )
    return boto3


def _running_in_lambda() -> bool:
    """True inside AWS Lambda or the AgentCore Runtime container, where we
    always want to use the execution role rather than enforce any local
    credential policy."""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME") or os.environ.get("AWS_EXECUTION_ENV"))


@functools.lru_cache(maxsize=None)
def _session():
    kwargs = {"region_name": config.AWS_REGION}

    if config.AWS_ACCESS_KEY_ID and config.AWS_SECRET_ACCESS_KEY:
        # Explicit keys win. botocore resolves profile_name from the
        # AWS_PROFILE/AWS_DEFAULT_PROFILE env vars internally regardless of
        # what we pass to Session(), so we must clear those env vars here,
        # not just omit profile_name from kwargs, or it tries (and fails)
        # to look up a profile that may not exist in ~/.aws/credentials.
        os.environ.pop("AWS_PROFILE", None)
        os.environ.pop("AWS_DEFAULT_PROFILE", None)
        kwargs["aws_access_key_id"] = config.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = config.AWS_SECRET_ACCESS_KEY
        if config.AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = config.AWS_SESSION_TOKEN
    elif config.AWS_PROFILE:
        kwargs["profile_name"] = config.AWS_PROFILE
    elif not _running_in_lambda():
        # Local (CDK/scripts) with no explicit keys and no configured
        # profile: fail fast and loudly instead of silently falling back to
        # whatever account the CLI's default/active profile happens to be -
        # that ambient fallback is exactly what this project must avoid.
        raise RuntimeError(
            "No AWS credentials configured. Set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in .env (or AWS_PROFILE to an explicit "
            "named profile). Refusing to fall back to the CLI's ambient "
            "default/active profile."
        )
    # Inside Lambda/AgentCore with none of the above set: fall through to
    # boto3's default resolution, which uses the execution role.

    return _require_boto3().Session(**kwargs)


@functools.lru_cache(maxsize=None)
def _bedrock_session():
    """Separate boto3 Session used ONLY for Bedrock calls, when
    BEDROCK_AWS_ACCESS_KEY_ID/BEDROCK_AWS_SECRET_ACCESS_KEY are configured.

    Exists because an account/key can be valid for every other AWS service
    this project uses (S3, DynamoDB, SES, Transcribe, End User Messaging,
    KMS) while being restricted from invoking Bedrock models. Falls back to
    the main _session() if the Bedrock-specific keys aren't set, so this is
    a no-op for anyone not using the split."""
    if not (config.BEDROCK_AWS_ACCESS_KEY_ID and config.BEDROCK_AWS_SECRET_ACCESS_KEY):
        return _session()

    kwargs = {
        "region_name": config.BEDROCK_REGION or config.AWS_REGION,
        "aws_access_key_id": config.BEDROCK_AWS_ACCESS_KEY_ID,
        "aws_secret_access_key": config.BEDROCK_AWS_SECRET_ACCESS_KEY,
    }
    if config.BEDROCK_AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = config.BEDROCK_AWS_SESSION_TOKEN
    # Same AWS_PROFILE env var leak as _session() - clear it so these
    # explicit keys aren't shadowed by a stray profile lookup.
    os.environ.pop("AWS_PROFILE", None)
    os.environ.pop("AWS_DEFAULT_PROFILE", None)
    return _require_boto3().Session(**kwargs)


@functools.lru_cache(maxsize=None)
def _client(service: str, region_override: str = ""):
    if region_override:
        return _session().client(service, region_name=region_override)
    return _session().client(service)


@functools.lru_cache(maxsize=None)
def _resource(service: str):
    return _session().resource(service)


def s3():
    return _client("s3")


def dynamodb_resource():
    return _resource("dynamodb")


@functools.lru_cache(maxsize=None)
def bedrock_runtime():
    """Bedrock model invocation client - uses the Bedrock-specific
    credentials if configured (see config.BEDROCK_AWS_ACCESS_KEY_ID),
    otherwise falls back to the main session."""
    region = config.BEDROCK_REGION or config.AWS_REGION
    return _bedrock_session().client("bedrock-runtime", region_name=region)


def social_messaging():
    return _client("socialmessaging")


def sms_voice():
    return _client("pinpoint-sms-voice-v2")


def transcribe():
    return _client("transcribe", config.TRANSCRIBE_REGION)


def ses():
    return _client("sesv2")


def kms():
    return _client("kms")


def connect():
    return _client("connect")


def lambda_client():
    return _client("lambda")


def agentcore_runtime():
    """Client for invoking the deployed Strands agent on AgentCore Runtime."""
    return _client("bedrock-agentcore")
