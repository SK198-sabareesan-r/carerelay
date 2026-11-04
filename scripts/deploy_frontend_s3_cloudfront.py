#!/usr/bin/env python3
"""Deploy the built CareRelay frontend (frontend/dist) to S3 + CloudFront.

Used instead of Amplify because this account is at its Amplify app quota.
Idempotent - re-run after `npm run build` to publish an update (it re-uploads
dist/ and creates a CloudFront invalidation so the new assets go live).

Steps:
  1. Create/reuse an S3 bucket for the site, enable static website hosting,
     make objects public-readable via bucket policy (OAC-free, simplest).
  2. Upload frontend/dist with correct Content-Type per extension.
  3. Create/reuse a CloudFront distribution in front (HTTPS + SPA fallback:
     403/404 -> /index.html so client-side routes resolve).
  4. Invalidate the CloudFront cache and print the live https URL.

Build the frontend FIRST with the live API baked in:
    cd frontend
    $env:VITE_API_BASE_URL="https://<api-id>.execute-api.<region>.amazonaws.com/prod"
    npm run build

Uses the MAIN .env credentials only (never the Bedrock split keys).

Usage:
    python scripts/deploy_frontend_s3_cloudfront.py
"""
import json
import mimetypes
import os
import re
import sys
import time

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_DIST_DIR = os.path.join(_REPO_ROOT, "frontend", "dist")
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

SITE_BUCKET = "carerelay-console-site-221894799392"
CALLER_REF = "carerelay-console-cf"

_CONTENT_TYPES = {
    ".html": "text/html", ".css": "text/css", ".js": "application/javascript",
    ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".ico": "image/x-icon",
    ".woff": "font/woff", ".woff2": "font/woff2", ".map": "application/json",
    ".webp": "image/webp", ".txt": "text/plain",
}


def _content_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return _CONTENT_TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def ensure_bucket(s3, bucket: str, region: str) -> None:
    existing = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    if bucket in existing:
        print(f"[s3] Bucket '{bucket}' exists.")
    else:
        print(f"[s3] Creating bucket '{bucket}'...")
        kwargs = {"Bucket": bucket}
        if region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**kwargs)
        s3.get_waiter("bucket_exists").wait(Bucket=bucket)

    # Allow a public-read bucket policy (website origin).
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True,
                                        "BlockPublicPolicy": False, "RestrictPublicBuckets": False},
    )
    s3.put_bucket_website(
        Bucket=bucket,
        WebsiteConfiguration={"IndexDocument": {"Suffix": "index.html"},
                              "ErrorDocument": {"Key": "index.html"}},
    )
    s3.put_bucket_policy(Bucket=bucket, Policy=json.dumps({
        "Version": "2012-10-17",
        "Statement": [{"Sid": "PublicRead", "Effect": "Allow", "Principal": "*",
                       "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{bucket}/*"}],
    }))
    print(f"[s3] Website hosting + public-read policy set on '{bucket}'.")


def upload_dist(s3, bucket: str) -> None:
    if not os.path.isdir(_DIST_DIR):
        print(f"ERROR: {_DIST_DIR} not found. Build the frontend first (npm run build).", file=sys.stderr)
        sys.exit(1)
    count = 0
    for root, _dirs, files in os.walk(_DIST_DIR):
        for fname in files:
            full = os.path.join(root, fname)
            key = os.path.relpath(full, _DIST_DIR).replace("\\", "/")
            # index.html: no-cache so deploys show immediately; hashed assets: long cache.
            cache = "no-cache, no-store, must-revalidate" if key == "index.html" else "public, max-age=31536000, immutable"
            with open(full, "rb") as fh:
                s3.put_object(Bucket=bucket, Key=key, Body=fh.read(),
                              ContentType=_content_type(key), CacheControl=cache)
            count += 1
    print(f"[s3] Uploaded {count} files from dist/.")


def website_endpoint(bucket: str, region: str) -> str:
    # ap-south-1 uses the dash form: bucket.s3-website.<region>.amazonaws.com
    return f"{bucket}.s3-website.{region}.amazonaws.com"


def ensure_distribution(cf, bucket: str, region: str) -> tuple:
    origin_domain = website_endpoint(bucket, region)
    # Reuse an existing distribution whose origin is this bucket website.
    dists = cf.list_distributions().get("DistributionList", {}).get("Items", []) or []
    for d in dists:
        for o in d.get("Origins", {}).get("Items", []):
            if o.get("DomainName") == origin_domain:
                print(f"[cloudfront] Reusing distribution {d['Id']} ({d['DomainName']}).")
                return d["Id"], d["DomainName"]

    print("[cloudfront] Creating distribution...")
    config_block = {
        "CallerReference": f"{CALLER_REF}-{int(time.time())}",
        "Comment": "CareRelay console (S3 website origin)",
        "Enabled": True,
        "DefaultRootObject": "index.html",
        "Origins": {"Quantity": 1, "Items": [{
            "Id": "s3-website",
            "DomainName": origin_domain,
            "CustomOriginConfig": {
                "HTTPPort": 80, "HTTPSPort": 443,
                "OriginProtocolPolicy": "http-only",  # S3 website endpoint is HTTP-only
                "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
            },
        }]},
        "DefaultCacheBehavior": {
            "TargetOriginId": "s3-website",
            "ViewerProtocolPolicy": "redirect-to-https",
            "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
            "Compress": True,
            "ForwardedValues": {"QueryString": False, "Cookies": {"Forward": "none"}},
            "MinTTL": 0,
        },
        "CustomErrorResponses": {"Quantity": 2, "Items": [
            {"ErrorCode": 403, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 0},
            {"ErrorCode": 404, "ResponseCode": "200", "ResponsePagePath": "/index.html", "ErrorCachingMinTTL": 0},
        ]},
        "PriceClass": "PriceClass_All",
    }
    resp = cf.create_distribution(DistributionConfig=config_block)
    return resp["Distribution"]["Id"], resp["Distribution"]["DomainName"]


def invalidate(cf, dist_id: str) -> None:
    cf.create_invalidation(
        DistributionId=dist_id,
        InvalidationBatch={"CallerReference": f"inv-{int(time.time())}",
                           "Paths": {"Quantity": 1, "Items": ["/*"]}},
    )
    print("[cloudfront] Cache invalidation created (/*).")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    region = config.AWS_REGION
    session = aws_clients._session()  # noqa: SLF001 - main session, never Bedrock
    s3 = session.client("s3")
    cf = session.client("cloudfront")

    ensure_bucket(s3, SITE_BUCKET, region)
    upload_dist(s3, SITE_BUCKET)
    try:
        dist_id, domain = ensure_distribution(cf, SITE_BUCKET, region)
    except Exception as exc:  # noqa: BLE001 - CloudFront can be account-gated
        print(f"\n[cloudfront] Skipped: {str(exc)[:200]}")
        print("The site is still live over the S3 website endpoint (HTTP):")
        print(f"  http://{website_endpoint(SITE_BUCKET, region)}")
        return
    invalidate(cf, dist_id)

    print(f"\n[cloudfront] Distribution ID: {dist_id}")
    print(f"Frontend URL: https://{domain}")
    print("NOTE: a NEW distribution takes ~5-15 min to reach 'Deployed' before it serves reliably.")
    print(f"S3 website (immediately live, HTTP): http://{website_endpoint(SITE_BUCKET, region)}")


if __name__ == "__main__":
    main()
