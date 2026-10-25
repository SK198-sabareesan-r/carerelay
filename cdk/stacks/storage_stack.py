"""Storage layer: S3 media bucket, DynamoDB tables, and the KMS signing key.

- media_bucket        : insurance card photos, symptom voice notes, signed PDFs
- intake_events_table : raw inbound WhatsApp messages; its Stream drives intake processing
- patients_table      : patient profile + latest intake status
- prior_auth_table    : one row per prior-authorization case (the audit trail)
- payer_rules_table   : deterministic CPT/payer prior-auth rules (the "code decides" data)
- staff_users_table   : clinic staff accounts for the console sign-in (hashed passwords only)
- signing_key         : asymmetric KMS key used to sign the audit PDF/report
"""
from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_kms as kms,
)
from constructs import Construct


class StorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---- S3: insurance cards, voice notes, signed reports ---------------
        self.media_bucket = s3.Bucket(
            self,
            "MediaBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    # Card photos / voice notes are only needed transiently
                    # for intake; expire to minimize PHI retention.
                    id="expire-intake-media",
                    prefix="intake/",
                    expiration=Duration.days(30),
                )
            ],
        )

        # ---- DynamoDB: raw inbound WhatsApp events (with Stream) ------------
        self.intake_events_table = dynamodb.Table(
            self,
            "IntakeEventsTable",
            partition_key=dynamodb.Attribute(
                name="pk", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="sk", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---- DynamoDB: patient profile -----------------------------------
        self.patients_table = dynamodb.Table(
            self,
            "PatientsTable",
            partition_key=dynamodb.Attribute(
                name="patient_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---- DynamoDB: prior-authorization cases (the audit trail) ----------
        self.prior_auth_table = dynamodb.Table(
            self,
            "PriorAuthTable",
            partition_key=dynamodb.Attribute(
                name="case_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.prior_auth_table.add_global_secondary_index(
            index_name="by-status",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="created_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # ---- DynamoDB: deterministic payer/CPT prior-auth rules --------------
        self.payer_rules_table = dynamodb.Table(
            self,
            "PayerRulesTable",
            partition_key=dynamodb.Attribute(
                name="payer_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="cpt_code", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---- DynamoDB: clinic staff accounts (console sign-in) ---------------
        # Composite key (hospital_id, username) - multiple hospitals can each
        # register their own staff without username collisions, and every
        # account belongs to exactly one hospital/organization. Item also
        # carries hospital_address/hospital_email/hospital_phone (collected
        # once at signup) alongside display_name/role/password_hash/
        # password_salt (PBKDF2, see lambdas/dashboard_api/handler.py:
        # _hash_password) - never plaintext. This is a basic staff-portal
        # credential store appropriate for a clinic command console, not a
        # hospital-grade identity system (no NPI/license verification, no
        # MFA) - see docs/DASHBOARD.md for the production-auth note
        # (Cognito/SSO recommended for real deployment).
        #
        # NOTE ON SCOPE: this table and the signup/login routes ARE
        # hospital-scoped. PriorAuthTable/case data is NOT yet filtered by
        # hospital_id (channel_dispatcher does not tag cases with it) - see
        # docs/DASHBOARD.md "Multi-tenancy status" for what's left.
        #
        # NOTE ON THIS TABLE SPECIFICALLY: a table with this exact name/key
        # schema (CareRelay-StaffUsersTable) was already created directly via
        # scripts/setup_auth_infra.py (bypassing `cdk deploy`, which is
        # deferred - see project decision log) so signup/login could be
        # tested against real AWS before the full stack deploys. When `cdk
        # deploy` eventually runs, THIS construct creates a SEPARATE table -
        # point STAFF_USERS_TABLE in .env at whichever one should be live
        # (the CDK output "StaffUsersTableName", or keep using the
        # standalone one) rather than assuming they're the same resource.
        self.staff_users_table = dynamodb.Table(
            self,
            "StaffUsersTable",
            partition_key=dynamodb.Attribute(
                name="hospital_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="username", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ---- KMS: asymmetric signing key for the audit report ----------------
        self.signing_key = kms.Key(
            self,
            "ReportSigningKey",
            key_spec=kms.KeySpec.RSA_2048,
            key_usage=kms.KeyUsage.SIGN_VERIFY,
            removal_policy=RemovalPolicy.DESTROY,
            alias="carerelay-report-signing",
            description="Signs CareRelay prior-auth audit reports (SES/report_generator).",
        )

        CfnOutput(self, "MediaBucketName", value=self.media_bucket.bucket_name)
        CfnOutput(self, "IntakeEventsTableName", value=self.intake_events_table.table_name)
        CfnOutput(self, "PatientsTableName", value=self.patients_table.table_name)
        CfnOutput(self, "PriorAuthTableName", value=self.prior_auth_table.table_name)
        CfnOutput(self, "PayerRulesTableName", value=self.payer_rules_table.table_name)
        CfnOutput(self, "StaffUsersTableName", value=self.staff_users_table.table_name)
        CfnOutput(self, "SigningKeyArn", value=self.signing_key.key_arn)
