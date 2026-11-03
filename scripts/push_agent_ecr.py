#!/usr/bin/env python3
"""Build the CareRelay agent Docker image and push it to Amazon ECR.

Steps (idempotent):
  1. Ensure the ECR repo `carerelay-agent` exists.
  2. `docker login` to ECR using the MAIN .env credentials (never Bedrock).
  3. `docker build -f agent_app/Dockerfile -t <repo>:latest .` from repo root.
  4. `docker push <repo>:latest`.

Prints the pushed image URI at the end (use it when creating an App Runner
service or AgentCore runtime).

Usage:
    python scripts/push_agent_ecr.py
"""
import base64
import os
import re
import subprocess
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

REPO_NAME = "carerelay-agent"
TAG = "latest"


def _run(cmd, **kwargs):
    print(f"[run] {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    subprocess.run(cmd, check=True, **kwargs)


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    region = config.AWS_REGION
    session = aws_clients._session()  # noqa: SLF001 - main session, never Bedrock
    account_id = session.client("sts").get_caller_identity()["Account"]
    ecr = session.client("ecr")

    registry = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
    image_uri = f"{registry}/{REPO_NAME}:{TAG}"

    # 1. Ensure repo exists.
    try:
        ecr.describe_repositories(repositoryNames=[REPO_NAME])
        print(f"[ecr] Repository '{REPO_NAME}' already exists.")
    except ecr.exceptions.RepositoryNotFoundException:
        print(f"[ecr] Creating repository '{REPO_NAME}'...")
        ecr.create_repository(repositoryName=REPO_NAME, imageScanningConfiguration={"scanOnPush": True})

    # 2. Docker login to ECR.
    print("[ecr] Fetching auth token...")
    tok = ecr.get_authorization_token()["authorizationData"][0]
    user_pass = base64.b64decode(tok["authorizationToken"]).decode()
    username, password = user_pass.split(":", 1)
    _run(["docker", "login", "--username", username, "--password-stdin", registry],
         input=password.encode())

    # 3. Build from repo root (Dockerfile imports lambdas.common).
    _run(["docker", "build", "-f", os.path.join("agent_app", "Dockerfile"),
          "-t", image_uri, "."], cwd=_REPO_ROOT)

    # 4. Push.
    _run(["docker", "push", image_uri])

    print(f"\nDone. Pushed image: {image_uri}")


if __name__ == "__main__":
    main()
