"""Minimal .env loader shared by cdk/app.py and local test/dev scripts.

Lambda and the AgentCore Runtime container never need this - their
environment variables are injected directly by the AWS execution
environment. This is for LOCAL use only (CDK synth/deploy, local testing
scripts), where nothing else loads .env into the process automatically.
"""
import os
import re


def load_dotenv(path: str) -> None:
    """Load KEY=VALUE lines from `path` into os.environ.

    Uses setdefault, so real shell/CI environment variables already set
    always take priority over .env - .env only fills in what's missing.
    Lines starting with # are comments; blank lines are ignored.
    """
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = re.match(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            os.environ.setdefault(key, value)


def load_repo_dotenv() -> None:
    """Load the .env file at the repository root.

    Works regardless of the caller's own file location, by walking up from
    this file's location (lambdas/common/dotenv.py -> lambdas -> repo root).
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(repo_root, ".env"))
