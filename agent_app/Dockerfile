# CareRelay agent backend - Strands multi-agent app on Bedrock AgentCore Runtime.
#
# Build from the REPO ROOT (not from agent_app/), because this package
# imports `lambdas.common` (shared config/clients/channel builders) in
# addition to its own agent_app code:
#
#   docker build -f agent_app/Dockerfile -t carerelay-agent:latest .
#
# See docs/DEPLOYMENT.md for the full build -> ECR push -> create_agent_runtime
# flow (also scripted in scripts/deploy_agent_runtime.py).
FROM --platform=linux/amd64 python:3.11-slim

WORKDIR /app

# Install agent dependencies first for better layer caching.
COPY agent_app/requirements.txt ./agent_app/requirements.txt
RUN pip install --no-cache-dir -r agent_app/requirements.txt

# Copy the shared common library (config, boto3 clients, channel builders,
# models) and the agent application code.
COPY lambdas/common ./lambdas/common
COPY lambdas/__init__.py ./lambdas/__init__.py
COPY agent_app ./agent_app

EXPOSE 8080

CMD ["python", "-m", "agent_app.main"]
