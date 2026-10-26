#!/usr/bin/env python3
"""Create (or reuse) an API Gateway REST API directly via boto3, wired to
the CareRelay-DashboardApi Lambda (see scripts/deploy_dashboard_api.py),
bypassing `cdk deploy` (deferred per project decision).

Routes created (mirrors cdk/stacks/compute_stack.py's dashboard routes):
    GET    /cases
    POST   /cases
    GET    /cases/{id}
    PATCH  /cases/{id}/status
    GET    /payer-rules
    POST   /payer-rules
    GET    /stats
    POST   /auth/signup
    POST   /auth/login

All routes proxy to the same Lambda (AWS_PROXY integration) with CORS
enabled (OPTIONS preflight + Access-Control-Allow-* response headers,
already set by handler.py's _respond()).

This script is idempotent - re-running finds the existing REST API by name
and just redeploys the stage, so changing routes here and re-running is
safe.

Usage:
    python scripts/deploy_api_gateway.py
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
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config  # noqa: E402

API_NAME = "CareRelay-DashboardApi"
STAGE_NAME = "prod"
LAMBDA_FUNCTION_NAME = "CareRelay-DashboardApi"

# (path_parts, methods) - path_parts is a tuple of static/`{param}` segments
# relative to the API root. Every method proxies to the same Lambda.
_ROUTES = [
    (("cases",), ["GET", "POST"]),
    (("cases", "{id}"), ["GET"]),
    (("cases", "{id}", "status"), ["PATCH"]),
    (("cases", "{id}", "message"), ["POST"]),
    (("followups",), ["POST"]),
    (("payer-rules",), ["GET", "POST"]),
    (("stats",), ["GET"]),
    (("auth", "signup"), ["POST"]),
    (("auth", "login"), ["POST"]),
]


def find_existing_api(apigw_client) -> str:
    paginator = apigw_client.get_paginator("get_rest_apis")
    for page in paginator.paginate():
        for api in page.get("items", []):
            if api["name"] == API_NAME:
                return api["id"]
    return ""


def ensure_api(apigw_client) -> str:
    api_id = find_existing_api(apigw_client)
    if api_id:
        print(f"[apigw] Reusing existing REST API '{API_NAME}': {api_id}")
        return api_id

    print(f"[apigw] Creating REST API '{API_NAME}'...")
    resp = apigw_client.create_rest_api(
        name=API_NAME,
        description="CareRelay dashboard_api - direct boto3 deploy, bypasses CDK.",
        endpointConfiguration={"types": ["REGIONAL"]},
    )
    return resp["id"]


def get_or_create_resource(apigw_client, api_id: str, root_id: str, path_parts: tuple) -> str:
    """Walks path_parts from the root, creating any resource segment that
    doesn't exist yet, and returns the final resource id."""
    resources = apigw_client.get_resources(restApiId=api_id, limit=500)["items"]
    by_path = {r["path"]: r["id"] for r in resources}

    current_path = ""
    current_id = root_id
    for part in path_parts:
        current_path = current_path + "/" + part
        if current_path in by_path:
            current_id = by_path[current_path]
            continue
        resp = apigw_client.create_resource(
            restApiId=api_id, parentId=current_id, pathPart=part
        )
        current_id = resp["id"]
        by_path[current_path] = current_id
    return current_id


def ensure_method(apigw_client, api_id: str, resource_id: str, http_method: str, lambda_arn: str, region: str) -> None:
    try:
        apigw_client.get_method(restApiId=api_id, resourceId=resource_id, httpMethod=http_method)
        print(f"  [method] {http_method} already configured, skipping method setup.")
        return
    except apigw_client.exceptions.NotFoundException:
        pass

    apigw_client.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=http_method,
        authorizationType="NONE",
    )
    uri = f"arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations"
    apigw_client.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod=http_method,
        type="AWS_PROXY",
        integrationHttpMethod="POST",
        uri=uri,
    )
    print(f"  [method] {http_method} -> Lambda proxy configured.")


def ensure_cors_options(apigw_client, api_id: str, resource_id: str, methods: list) -> None:
    allow_methods = ",".join(methods + ["OPTIONS"])
    try:
        apigw_client.get_method(restApiId=api_id, resourceId=resource_id, httpMethod="OPTIONS")
        print("  [cors] OPTIONS already configured, skipping.")
        return
    except apigw_client.exceptions.NotFoundException:
        pass

    apigw_client.put_method(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="OPTIONS",
        authorizationType="NONE",
    )
    apigw_client.put_integration(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="OPTIONS",
        type="MOCK",
        requestTemplates={"application/json": '{"statusCode": 200}'},
    )
    apigw_client.put_method_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="OPTIONS",
        statusCode="200",
        responseParameters={
            "method.response.header.Access-Control-Allow-Headers": False,
            "method.response.header.Access-Control-Allow-Methods": False,
            "method.response.header.Access-Control-Allow-Origin": False,
        },
    )
    apigw_client.put_integration_response(
        restApiId=api_id,
        resourceId=resource_id,
        httpMethod="OPTIONS",
        statusCode="200",
        responseParameters={
            "method.response.header.Access-Control-Allow-Headers": "'content-type'",
            "method.response.header.Access-Control-Allow-Methods": f"'{allow_methods}'",
            "method.response.header.Access-Control-Allow-Origin": "'*'",
        },
    )
    print(f"  [cors] OPTIONS preflight configured (allow: {allow_methods}).")


def grant_lambda_invoke_permission(lambda_client, lambda_function_name: str, api_id: str, region: str, account_id: str) -> None:
    statement_id = "CareRelayApiGatewayInvoke"
    source_arn = f"arn:aws:execute-api:{region}:{account_id}:{api_id}/*/*"
    try:
        lambda_client.add_permission(
            FunctionName=lambda_function_name,
            StatementId=statement_id,
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=source_arn,
        )
        print(f"[lambda] Granted API Gateway invoke permission (source: {source_arn}).")
    except lambda_client.exceptions.ResourceConflictException:
        print("[lambda] Invoke permission already granted, skipping.")


def main() -> None:
    if not config.AWS_ACCESS_KEY_ID or not config.AWS_SECRET_ACCESS_KEY:
        print("ERROR: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set in .env.", file=sys.stderr)
        sys.exit(1)

    region = config.AWS_REGION
    session = aws_clients._session()  # noqa: SLF001
    apigw_client = session.client("apigateway")
    lambda_client = aws_clients.lambda_client()
    sts_client = session.client("sts")

    account_id = sts_client.get_caller_identity()["Account"]

    try:
        fn = lambda_client.get_function(FunctionName=LAMBDA_FUNCTION_NAME)
    except lambda_client.exceptions.ResourceNotFoundException:
        print(
            f"ERROR: Lambda function '{LAMBDA_FUNCTION_NAME}' not found. "
            "Run scripts/deploy_dashboard_api.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    lambda_arn = fn["Configuration"]["FunctionArn"]

    api_id = ensure_api(apigw_client)
    root_id = [r["id"] for r in apigw_client.get_resources(restApiId=api_id)["items"] if r["path"] == "/"][0]

    for path_parts, methods in _ROUTES:
        print(f"[apigw] Route /{'/'.join(path_parts)} -> {methods}")
        resource_id = get_or_create_resource(apigw_client, api_id, root_id, path_parts)
        for method in methods:
            ensure_method(apigw_client, api_id, resource_id, method, lambda_arn, region)
        ensure_cors_options(apigw_client, api_id, resource_id, methods)

    grant_lambda_invoke_permission(lambda_client, LAMBDA_FUNCTION_NAME, api_id, region, account_id)

    print(f"[apigw] Deploying stage '{STAGE_NAME}'...")
    apigw_client.create_deployment(restApiId=api_id, stageName=STAGE_NAME)

    base_url = f"https://{api_id}.execute-api.{region}.amazonaws.com/{STAGE_NAME}"
    print(f"\nDone. API base URL: {base_url}")
    print("Set this as VITE_API_BASE_URL (frontend/.env) or paste it into the console's Settings panel.")


if __name__ == "__main__":
    main()
