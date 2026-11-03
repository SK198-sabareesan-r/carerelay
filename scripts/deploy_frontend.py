#!/usr/bin/env python3
"""Deploy the built CareRelay frontend (frontend/dist) to AWS Amplify Hosting
via the manual-zip deployment method (no Git connection needed).

Steps (idempotent):
  1. Ensure an Amplify app named 'carerelay-console' exists.
  2. Ensure a branch 'main' exists on it.
  3. create_deployment -> get a presigned zip upload URL.
  4. Zip frontend/dist and PUT it to that URL.
  5. start_deployment -> Amplify publishes it.
  6. Print the live https URL.

Build the frontend FIRST with the live API baked in:
    cd frontend
    $env:VITE_API_BASE_URL="https://<api-id>.execute-api.<region>.amazonaws.com/prod"
    npm run build

Uses the MAIN .env credentials only (never the Bedrock split keys).

Usage:
    python scripts/deploy_frontend.py
"""
import io
import os
import re
import sys
import time
import zipfile
import urllib.request

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

APP_NAME = "carerelay-console"
BRANCH = "main"


def _zip_dist() -> bytes:
    if not os.path.isdir(_DIST_DIR):
        print(f"ERROR: {_DIST_DIR} not found. Build the frontend first (npm run build).", file=sys.stderr)
        sys.exit(1)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(_DIST_DIR):
            for fname in files:
                full = os.path.join(root, fname)
                arc = os.path.relpath(full, _DIST_DIR)
                zf.write(full, arc)
    buf.seek(0)
    return buf.read()


def _ensure_app(amp) -> str:
    token = None
    while True:
        resp = amp.list_apps(nextToken=token) if token else amp.list_apps()
        for app in resp.get("apps", []):
            if app["name"] == APP_NAME:
                print(f"[amplify] Reusing app '{APP_NAME}': {app['appId']}")
                return app["appId"]
        token = resp.get("nextToken")
        if not token:
            break
    print(f"[amplify] Creating app '{APP_NAME}'...")
    # SPA rewrite so client-side routes (/cases/..) resolve to index.html.
    app = amp.create_app(
        name=APP_NAME,
        platform="WEB",
        customRules=[{"source": "/<*>", "target": "/index.html", "status": "404-200"}],
    )
    return app["app"]["appId"]


def _ensure_branch(amp, app_id: str) -> None:
    try:
        amp.get_branch(appId=app_id, branchName=BRANCH)
        print(f"[amplify] Branch '{BRANCH}' exists.")
    except amp.exceptions.NotFoundException:
        print(f"[amplify] Creating branch '{BRANCH}'...")
        amp.create_branch(appId=app_id, branchName=BRANCH, stage="PRODUCTION")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    amp = aws_clients._session().client("amplify")  # noqa: SLF001 - main session, never Bedrock

    app_id = _ensure_app(amp)
    _ensure_branch(amp, app_id)

    print("[amplify] Creating deployment (presigned upload URL)...")
    dep = amp.create_deployment(appId=app_id, branchName=BRANCH)
    upload_url = dep["zipUploadUrl"]
    job_id = dep["jobId"]

    zip_bytes = _zip_dist()
    print(f"[amplify] Uploading dist zip ({len(zip_bytes) / 1024:.1f} KB)...")
    req = urllib.request.Request(upload_url, data=zip_bytes, method="PUT",
                                 headers={"Content-Type": "application/zip"})
    with urllib.request.urlopen(req, timeout=120) as r:
        if r.status not in (200, 204):
            print(f"ERROR: upload failed with HTTP {r.status}", file=sys.stderr)
            sys.exit(1)

    print(f"[amplify] Starting deployment (job {job_id})...")
    amp.start_deployment(appId=app_id, branchName=BRANCH, jobId=job_id)

    # Poll briefly for completion.
    for _ in range(30):
        job = amp.get_job(appId=app_id, branchName=BRANCH, jobId=job_id)["job"]
        status = job["summary"]["status"]
        if status in ("SUCCEED", "FAILED", "CANCELLED"):
            print(f"[amplify] Deployment {status}.")
            break
        time.sleep(5)

    url = f"https://{BRANCH}.{app_id}.amplifyapp.com"
    print(f"\nDone. Frontend URL: {url}")


if __name__ == "__main__":
    main()
