#!/usr/bin/env python3
"""Create the S3 media bucket (insurance card photos, voice notes, signed
reports) directly via boto3, bypassing `cdk deploy` (same pattern as the
other setup_*_infra.py scripts).

Matches cdk/stacks/storage_stack.py's MediaBucket: SSE-S3 encryption, all
public access blocked, SSL enforced. Bucket name comes from config.MEDIA_BUCKET
(.env MEDIA_BUCKET). Idempotent - skips creation if the bucket already exists.

Uses the MAIN .env credentials only (never the Bedrock split keys).

Usage:
    python scripts/setup_media_bucket.py
"""
import json
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
            if value:
                os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    bucket = config.MEDIA_BUCKET
    if not bucket:
        print("ERROR: MEDIA_BUCKET not set in .env.", file=sys.stderr)
        sys.exit(1)

    region = config.AWS_REGION
    s3 = aws_clients._session().client("s3")  # noqa: SLF001 - main session, never Bedrock

    # Exists already?
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if bucket in existing:
        print(f"[s3] Bucket '{bucket}' already exists - skipping create.")
    else:
        print(f"[s3] Creating bucket '{bucket}' in {region}...")
        kwargs = {"Bucket": bucket}
        # us-east-1 must NOT send a LocationConstraint; every other region must.
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        s3.get_waiter("bucket_exists").wait(Bucket=bucket)
        print(f"[s3] Bucket '{bucket}' created.")

    # Harden: block all public access.
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    # Default SSE-S3 encryption.
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    # Enforce TLS via bucket policy (deny non-SSL requests).
    ssl_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "DenyInsecureTransport",
            "Effect": "Deny",
            "Principal": "*",
            "Action": "s3:*",
            "Resource": [f"arn:aws:s3:::{bucket}", f"arn:aws:s3:::{bucket}/*"],
            "Condition": {"Bool": {"aws:SecureTransport": "false"}},
        }],
    }
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps(ssl_policy))
    print(f"[s3] Hardened '{bucket}': public access blocked, SSE-S3 on, TLS enforced.")


if __name__ == "__main__":
    main()
