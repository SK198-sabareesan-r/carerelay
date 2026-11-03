"""CareRelay FULL TEARDOWN.

Deletes every CareRelay AWS resource discovered on account 221894799392 /
ap-south-1, in dependency-safe order. Idempotent: safe to re-run; already-gone
resources are skipped.

Uses ONLY the main .env credentials (AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY).
Does NOT touch the Bedrock account/creds (BEDROCK_AWS_*), as instructed.

Run:  python scripts/teardown_all.py --yes
Without --yes it prints the plan and exits (dry run).
"""
import os, re, sys, time, pathlib
import boto3
from botocore.exceptions import ClientError

ROOT = pathlib.Path(__file__).resolve().parents[1]
for line in ROOT.joinpath(".env").read_text().splitlines():
    m = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line)
    if m and m.group(2).strip():
        os.environ.setdefault(m.group(1), m.group(2).strip())
if not os.environ.get("AWS_PROFILE"):
    os.environ.pop("AWS_PROFILE", None)

REGION = os.environ.get("AWS_REGION", "ap-south-1")
S = boto3.Session(
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    region_name=REGION,
)
LIVE = "--yes" in sys.argv

# Exact resource identifiers from discovery.
APPRUNNER_ARN = "arn:aws:apprunner:ap-south-1:221894799392:service/carerelay-agent/6dca09f245734b76958ba0c92295eff6"
ECR_REPOS = ["carerelay-agent"]
AMPLIFY_APP_ID = "deqb6ko771kra"
REST_API_ID = "b16m4614vd"
LAMBDAS = ["CareRelay-WebhookReceiver", "CareRelay-ChannelDispatcher", "CareRelay-DashboardApi"]
SNS_TOPIC = "arn:aws:sns:ap-south-1:221894799392:CareRelay-InboundTopic"
DDB_TABLES = [
    "CareRelay-AppointmentsTable", "CareRelay-IntakeEventsTable", "CareRelay-PatientsTable",
    "CareRelay-PayerRulesTable", "CareRelay-PriorAuthTable", "CareRelay-StaffUsersTable",
]
S3_BUCKETS = ["carerelay-console-221894799392", "carerelay-media-221894799392"]
SES_IDENTITY = "robotoroboto443@gmail.com"
IAM_ROLES = [
    "CareRelay-AgentCoreRole", "CareRelay-AppRunnerECRRole", "CareRelay-AppRunnerTaskRole",
    "CareRelay-ChannelDispatcherRole", "CareRelay-DashboardApiRole", "CareRelay-WebhookReceiverRole",
]
IAM_USER = "CDS"
IAM_USER_INLINE_POLICY = "CareRelayComms"


def step(msg):
    print(f"\n>>> {msg}")


def do(desc, fn):
    """Run a delete action, swallowing not-found errors; honor dry-run."""
    if not LIVE:
        print(f"    [DRY-RUN] would: {desc}")
        return
    try:
        fn()
        print(f"    OK: {desc}")
    except ClientError as e:
        code = e.response["Error"].get("Code", "")
        if code in ("ResourceNotFoundException", "NotFoundException", "NoSuchEntity",
                    "NoSuchBucket", "NoSuchEntityException", "ResourceNotFound",
                    "InvalidParameterValueException") and "not" in e.response["Error"].get("Message", "").lower():
            print(f"    SKIP (gone): {desc}")
        elif code in ("ResourceNotFoundException", "NotFoundException", "NoSuchEntity",
                      "NoSuchBucket"):
            print(f"    SKIP (gone): {desc}")
        else:
            print(f"    WARN {code}: {desc} :: {e.response['Error'].get('Message','')[:160]}")
    except Exception as e:
        print(f"    WARN {type(e).__name__}: {desc} :: {str(e)[:160]}")


# 1. App Runner (biggest cost) -------------------------------------------------
step("App Runner service")
do("delete App Runner service carerelay-agent",
   lambda: S.client("apprunner").delete_service(ServiceArn=APPRUNNER_ARN))

# 2. Amplify -------------------------------------------------------------------
step("Amplify app")
do(f"delete Amplify app {AMPLIFY_APP_ID}",
   lambda: S.client("amplify").delete_app(appId=AMPLIFY_APP_ID))

# 3. API Gateway ---------------------------------------------------------------
step("API Gateway REST API")
do(f"delete REST API {REST_API_ID}",
   lambda: S.client("apigateway").delete_rest_api(restApiId=REST_API_ID))

# 4. Lambdas -------------------------------------------------------------------
step("Lambda functions")
for fn_name in LAMBDAS:
    do(f"delete lambda {fn_name}",
       lambda n=fn_name: S.client("lambda").delete_function(FunctionName=n))

# 5. SNS -----------------------------------------------------------------------
step("SNS topic + subscriptions")
def _del_sns():
    sns = S.client("sns")
    try:
        for sub in sns.list_subscriptions_by_topic(TopicArn=SNS_TOPIC).get("Subscriptions", []):
            arn = sub.get("SubscriptionArn", "")
            if arn.startswith("arn:"):
                sns.unsubscribe(SubscriptionArn=arn)
    except ClientError:
        pass
    sns.delete_topic(TopicArn=SNS_TOPIC)
do(f"delete SNS topic {SNS_TOPIC}", _del_sns)

# 6. DynamoDB ------------------------------------------------------------------
step("DynamoDB tables")
for t in DDB_TABLES:
    do(f"delete DynamoDB table {t}",
       lambda n=t: S.client("dynamodb").delete_table(TableName=n))

# 7. S3 (empty then delete) ----------------------------------------------------
step("S3 buckets (empty + delete)")
def _empty_and_delete(bucket):
    s3 = S.client("s3")
    # delete all object versions + markers (works for versioned & non-versioned)
    paginator = s3.get_paginator("list_object_versions")
    try:
        for page in paginator.paginate(Bucket=bucket):
            objs = [{"Key": o["Key"], "VersionId": o["VersionId"]}
                    for o in page.get("Versions", [])]
            objs += [{"Key": o["Key"], "VersionId": o["VersionId"]}
                     for o in page.get("DeleteMarkers", [])]
            if objs:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("NoSuchBucket",):
            # fall back to plain object listing (bucket may not be versioned)
            try:
                p2 = s3.get_paginator("list_objects_v2")
                for page in p2.paginate(Bucket=bucket):
                    objs = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                    if objs:
                        s3.delete_objects(Bucket=bucket, Delete={"Objects": objs})
            except ClientError:
                pass
    s3.delete_bucket(Bucket=bucket)
for b in S3_BUCKETS:
    do(f"empty + delete S3 bucket {b}", lambda n=b: _empty_and_delete(n))

# 8. SES identity --------------------------------------------------------------
step("SES identity")
do(f"delete SES identity {SES_IDENTITY}",
   lambda: S.client("sesv2").delete_email_identity(EmailIdentity=SES_IDENTITY))

# 9. ECR (delete images then repo) --------------------------------------------
step("ECR repositories")
for repo in ECR_REPOS:
    do(f"delete ECR repo {repo} (force)",
       lambda r=repo: S.client("ecr").delete_repository(repositoryName=r, force=True))

# 10. IAM roles (detach/delete inline + managed, then role) -------------------
step("IAM roles")
def _nuke_role(role):
    iam = S.client("iam")
    for pol in iam.list_role_policies(RoleName=role).get("PolicyNames", []):
        iam.delete_role_policy(RoleName=role, PolicyName=pol)
    for pol in iam.list_attached_role_policies(RoleName=role).get("AttachedPolicies", []):
        iam.detach_role_policy(RoleName=role, PolicyArn=pol["PolicyArn"])
    for ip in iam.list_instance_profiles_for_role(RoleName=role).get("InstanceProfiles", []):
        iam.remove_role_from_instance_profile(InstanceProfileName=ip["InstanceProfileName"], RoleName=role)
    iam.delete_role(RoleName=role)
for r in IAM_ROLES:
    do(f"delete IAM role {r}", lambda n=r: _nuke_role(n))

# 11. IAM user inline policy (leave the user + its keys intact) ----------------
step("IAM user CDS inline policy CareRelayComms")
do(f"delete inline policy {IAM_USER_INLINE_POLICY} on user {IAM_USER}",
   lambda: S.client("iam").delete_user_policy(UserName=IAM_USER, PolicyName=IAM_USER_INLINE_POLICY))

print("\n" + ("TEARDOWN COMPLETE." if LIVE else "DRY RUN COMPLETE (pass --yes to execute)."))
