"""Compute layer: the AgentCore Runtime (Strands multi-agent backend) and the
two thin CDS-facing Lambdas.

    webhook_receiver   - SNS subscriber. Parses inbound WhatsApp events
                         (insurance card photo / voice note / text), pulls
                         media into S3, writes a raw intake event to
                         DynamoDB. Also exposed via API Gateway for direct
                         webhook posts and local testing.
    channel_dispatcher - DynamoDB Stream consumer. Batches a patient's
                         rapid message burst, invokes the AgentCore Runtime
                         (the Strands supervisor) once per case, persists the
                         resulting PriorAuthTable case, and sends the drafted
                         messages out over WhatsApp (patient), RCS (doctor),
                         and SES (signed audit report).

The agent backend itself (agent_app/) is packaged as a container image and
run on Amazon Bedrock AgentCore Runtime (aws_bedrockagentcore.CfnRuntime),
NOT as a Lambda - this is the "deploy the complete backend on AgentCore"
requirement. The two Lambdas only handle CDS plumbing (SNS/S3/DynamoDB in,
WhatsApp/RCS/SES out) and the single invoke_agent_runtime call in between.
"""
import os

from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_lambda_event_sources as sources,
    aws_apigateway as apigw,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
    aws_iam as iam,
    aws_ecr_assets as ecr_assets,
    aws_bedrockagentcore as agentcore,
)
from constructs import Construct

# Path to the lambdas/ directory (repo_root/lambdas) and the repo root
# (needed so the AgentCore image build can also COPY lambdas/common).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))
LAMBDAS_DIR = os.path.join(REPO_ROOT, "lambdas")
AGENT_APP_DIR = os.path.join(REPO_ROOT, "agent_app")


class ComputeStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        media_bucket: s3.Bucket,
        intake_events_table: dynamodb.Table,
        patients_table: dynamodb.Table,
        prior_auth_table: dynamodb.Table,
        payer_rules_table: dynamodb.Table,
        staff_users_table: dynamodb.Table,
        signing_key: kms.Key,
        inbound_topic: sns.Topic,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        agent_runtime_name = "carerelay_agent"

        # ====================================================================
        # 1. AgentCore Runtime: the Strands multi-agent backend
        # ====================================================================
        agent_image = ecr_assets.DockerImageAsset(
            self,
            "AgentImage",
            directory=REPO_ROOT,
            file="agent_app/Dockerfile",
            platform=ecr_assets.Platform.LINUX_AMD64,
        )

        agent_execution_role = iam.Role(
            self,
            "AgentRuntimeExecutionRole",
            assumed_by=iam.ServicePrincipal(
                "bedrock-agentcore.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": self.account},
                    "ArnLike": {
                        "aws:SourceArn": f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:*"
                    },
                },
            ),
            description="Execution role for the CareRelay Strands agent on AgentCore Runtime.",
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="ECRImageAccess",
                actions=["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"],
                resources=[
                    f"arn:aws:ecr:{self.region}:{self.account}:repository/*"
                ],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(sid="ECRTokenAccess", actions=["ecr:GetAuthorizationToken"], resources=["*"])
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:DescribeLogStreams", "logs:CreateLogGroup"],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                resources=[
                    f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
                ],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["logs:DescribeLogGroups"],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:*"],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                    "xray:GetSamplingRules",
                    "xray:GetSamplingTargets",
                ],
                resources=["*"],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:PutMetricData"],
                resources=["*"],
                conditions={"StringEquals": {"cloudwatch:namespace": "bedrock-agentcore"}},
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="GetAgentAccessToken",
                actions=[
                    "bedrock-agentcore:GetWorkloadAccessToken",
                    "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                ],
                resources=[
                    f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                    (
                        f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:"
                        f"workload-identity-directory/default/workload-identity/{agent_runtime_name}-*"
                    ),
                ],
            )
        )
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                sid="BedrockModelInvocation",
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/*",
                    f"arn:aws:bedrock:{self.region}:{self.account}:*",
                ],
            )
        )
        # The agent container's own tools need Transcribe/S3/DynamoDB access
        # (rules engine reads PayerRulesTable; documents.py reads/writes the
        # media bucket and calls Transcribe directly; card extraction uses
        # the Bedrock vision model, already covered by BedrockModelInvocation
        # above - no Textract permission needed).
        media_bucket.grant_read_write(agent_execution_role)
        payer_rules_table.grant_read_data(agent_execution_role)
        agent_execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                ],
                resources=["*"],
            )
        )

        agent_runtime = agentcore.CfnRuntime(
            self,
            "AgentRuntime",
            agent_runtime_name=agent_runtime_name,
            role_arn=agent_execution_role.role_arn,
            agent_runtime_artifact=agentcore.CfnRuntime.AgentRuntimeArtifactProperty(
                container_configuration=agentcore.CfnRuntime.ContainerConfigurationProperty(
                    container_uri=agent_image.image_uri,
                )
            ),
            network_configuration=agentcore.CfnRuntime.NetworkConfigurationProperty(
                network_mode="PUBLIC",
            ),
            description="CareRelay Strands multi-agent backend (Intake/Verification/Notification).",
            environment_variables={
                "AWS_REGION": self.region,
                "BEDROCK_MODEL_ID": os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6"),
                "BEDROCK_VISION_MODEL_ID": os.environ.get(
                    "BEDROCK_VISION_MODEL_ID", "global.anthropic.claude-sonnet-4-6"
                ),
                "BEDROCK_REGION": os.environ.get("BEDROCK_REGION", ""),
                "TRANSCRIBE_REGION": os.environ.get("TRANSCRIBE_REGION", ""),
                "MEDIA_BUCKET": media_bucket.bucket_name,
                "PAYER_RULES_TABLE": payer_rules_table.table_name,
            },
        )
        agent_runtime.node.add_dependency(agent_execution_role)

        # ====================================================================
        # 2. Thin Lambdas: CDS plumbing only
        # ====================================================================
        common_env = {
            "MEDIA_BUCKET": media_bucket.bucket_name,
            "INTAKE_EVENTS_TABLE": intake_events_table.table_name,
            "PATIENTS_TABLE": patients_table.table_name,
            "PRIOR_AUTH_TABLE": prior_auth_table.table_name,
            "PAYER_RULES_TABLE": payer_rules_table.table_name,
            "STAFF_USERS_TABLE": staff_users_table.table_name,
            "KMS_SIGNING_KEY_ID": signing_key.key_id,
            "AGENT_RUNTIME_ARN": agent_runtime.attr_agent_runtime_arn,
            "BEDROCK_REGION": os.environ.get("BEDROCK_REGION", ""),
            "TRANSCRIBE_REGION": os.environ.get("TRANSCRIBE_REGION", ""),
            "WHATSAPP_PHONE_NUMBER_ID": os.environ.get("WHATSAPP_PHONE_NUMBER_ID", ""),
            "META_API_VERSION": os.environ.get("META_API_VERSION", "v20.0"),
            "META_APP_SECRET": os.environ.get("META_APP_SECRET", ""),
            "META_WEBHOOK_VERIFY_TOKEN": os.environ.get("META_WEBHOOK_VERIFY_TOKEN", ""),
            "RCS_PHONE_NUMBER_ID": os.environ.get("RCS_PHONE_NUMBER_ID", ""),
            "SMS_ORIGINATION_NUMBER": os.environ.get("SMS_ORIGINATION_NUMBER", ""),
            "CLINIC_APPROVER_NUMBERS": os.environ.get("CLINIC_APPROVER_NUMBERS", ""),
            "SES_SENDER": os.environ.get("SES_SENDER", ""),
            "SES_COMMAND_RECIPIENTS": os.environ.get("SES_COMMAND_RECIPIENTS", ""),
            "INTAKE_BATCH_WINDOW_SECONDS": os.environ.get("INTAKE_BATCH_WINDOW_SECONDS", "15"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
        }

        def code_asset() -> _lambda.Code:
            # Pure-Python Lambdas depending only on the boto3 bundled in the
            # Lambda runtime - package the directory directly, no Docker
            # build needed (mirrors the earlier NovaRelay approach).
            return _lambda.Code.from_asset(LAMBDAS_DIR)

        runtime = _lambda.Runtime.PYTHON_3_11
        shared_asset = code_asset()

        # ---- webhook_receiver ---------------------------------------------
        receiver_fn = _lambda.Function(
            self,
            "WebhookReceiver",
            runtime=runtime,
            handler="webhook_receiver.handler.handler",
            code=shared_asset,
            timeout=Duration.seconds(60),
            memory_size=512,
            environment=common_env,
        )

        # ---- channel_dispatcher (invokes AgentCore Runtime) ----------------
        dispatcher_fn = _lambda.Function(
            self,
            "ChannelDispatcher",
            runtime=runtime,
            handler="channel_dispatcher.handler.handler",
            code=shared_asset,
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=common_env,
        )

        # ---- dashboard_api (read-only API for the frontend/ application) ---
        dashboard_fn = _lambda.Function(
            self,
            "DashboardApi",
            runtime=runtime,
            handler="dashboard_api.handler.handler",
            code=shared_asset,
            timeout=Duration.seconds(30),
            memory_size=512,
            environment=common_env,
        )

        # ====================================================================
        # 3. IAM for the Lambdas
        # ====================================================================
        media_bucket.grant_read_write(receiver_fn)
        media_bucket.grant_read(dispatcher_fn)
        media_bucket.grant_read(dashboard_fn)  # presigned URLs for card photo / voice note

        intake_events_table.grant_read_write_data(receiver_fn)
        intake_events_table.grant_stream_read(dispatcher_fn)
        patients_table.grant_read_write_data(dispatcher_fn)
        prior_auth_table.grant_read_write_data(dispatcher_fn)
        prior_auth_table.grant_read_data(dashboard_fn)
        payer_rules_table.grant_read_data(dashboard_fn)
        staff_users_table.grant_read_write_data(dashboard_fn)  # signup writes, login reads

        signing_key.grant_sign(dispatcher_fn)

        # AWS End User Messaging Social (WhatsApp) - media fetch (receiver) + send (dispatcher)
        receiver_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["social-messaging:GetWhatsAppMessageMedia"],
                resources=["*"],
            )
        )
        dispatcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["social-messaging:SendWhatsAppMessage"],
                resources=["*"],
            )
        )

        # AWS End User Messaging SMS/RCS - doctor approval card
        dispatcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sms-voice:SendTextMessage"],
                resources=["*"],
            )
        )

        # Amazon SES - signed audit report delivery (dispatcher) + staff
        # onboarding email on signup (dashboard_api, see
        # lambdas/dashboard_api/onboarding_email.py)
        dispatcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )
        dashboard_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ses:SendEmail", "ses:SendRawEmail"],
                resources=["*"],
            )
        )

        # Invoke the AgentCore Runtime
        dispatcher_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[agent_runtime.attr_agent_runtime_arn, f"{agent_runtime.attr_agent_runtime_arn}/*"],
            )
        )

        # ====================================================================
        # 4. Event wiring
        # ====================================================================
        inbound_topic.add_subscription(subs.LambdaSubscription(receiver_fn))

        window = int(os.environ.get("INTAKE_BATCH_WINDOW_SECONDS", "15"))
        dispatcher_fn.add_event_source(
            sources.DynamoEventSource(
                intake_events_table,
                starting_position=_lambda.StartingPosition.LATEST,
                batch_size=100,
                max_batching_window=Duration.seconds(window),
                retry_attempts=2,
                report_batch_item_failures=True,
            )
        )

        # ====================================================================
        # 5. API Gateway (direct webhook / local testing)
        # ====================================================================
        api = apigw.LambdaRestApi(
            self,
            "WebhookApi",
            handler=receiver_fn,
            proxy=False,
            description="CareRelay inbound WhatsApp webhook (direct POST / local testing).",
        )
        webhook = api.root.add_resource("webhook")
        webhook.add_method("POST")
        webhook.add_method("GET")  # Meta verification challenge

        # ---- Dashboard API (read-only, CORS-enabled for the frontend/ app) ---
        #
        # SECURITY: intentionally unauthenticated so the frontend app runs
        # with zero setup. dashboard_api never returns raw patient phone
        # numbers (masked at write time) and is strictly read-only. Add an
        # authorizer before any real deployment - see docs/DASHBOARD.md.
        dashboard_integration = apigw.LambdaIntegration(dashboard_fn)
        cors = apigw.CorsOptions(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["GET", "OPTIONS"],
        )
        cors_post = apigw.CorsOptions(
            allow_origins=apigw.Cors.ALL_ORIGINS,
            allow_methods=["POST", "OPTIONS"],
        )

        cases = api.root.add_resource("cases", default_cors_preflight_options=cors)
        cases.add_method("GET", dashboard_integration)
        case_by_id = cases.add_resource("{id}", default_cors_preflight_options=cors)
        case_by_id.add_method("GET", dashboard_integration)

        payer_rules = api.root.add_resource("payer-rules", default_cors_preflight_options=cors)
        payer_rules.add_method("GET", dashboard_integration)

        stats = api.root.add_resource("stats", default_cors_preflight_options=cors)
        stats.add_method("GET", dashboard_integration)

        # ---- Staff auth (signup / login) --------------------------------------
        auth = api.root.add_resource("auth")
        signup = auth.add_resource("signup", default_cors_preflight_options=cors_post)
        signup.add_method("POST", dashboard_integration)
        login = auth.add_resource("login", default_cors_preflight_options=cors_post)
        login.add_method("POST", dashboard_integration)

        CfnOutput(self, "WebhookApiUrl", value=api.url)
        CfnOutput(
            self,
            "DashboardApiUrl",
            value=api.url,
            description="Base URL for the frontend/ app's VITE_API_BASE_URL (points here, e.g. .../cases).",
        )
        CfnOutput(self, "WebhookReceiverFn", value=receiver_fn.function_name)
        CfnOutput(self, "ChannelDispatcherFn", value=dispatcher_fn.function_name)
        CfnOutput(self, "DashboardApiFn", value=dashboard_fn.function_name)
        CfnOutput(self, "AgentRuntimeArn", value=agent_runtime.attr_agent_runtime_arn)
        CfnOutput(self, "AgentImageUri", value=agent_image.image_uri)
