# CareRelay

**Conversational prior-authorization for clinics**, powered by a **Strands multi-agent** backend on **Amazon Bedrock AgentCore Runtime**, with **AWS Communication Developer Services (CDS)** — WhatsApp, RCS/SMS, and SES — as the messaging backbone.

Built for the **AWS CDS Agentic AI Hackathon (Sept. 2026)**.

A patient sends a photo of their insurance card and a voice note describing their procedure over **WhatsApp**. A Strands multi-agent pipeline extracts the card details, checks the payer's prior-authorization rules deterministically, and replies with a status update — all without the patient ever leaving the chat. The clinic's doctor/approver gets an **RCS action card** to approve the visit slot, and billing staff get a **KMS-signed audit email** for every case. Clinic staff manage the whole queue from a web console with their own hospital-scoped login.

---

## Why this fits AWS CDS

- **WhatsApp (AWS End User Messaging Social)** — patient intake (photo + voice note) and status replies with interactive buttons. Meta owns the WhatsApp network itself (the WhatsApp Business Account); AWS End User Messaging Social is the bridge service that relays those messages into AWS. Per [AWS's own architecture](https://docs.aws.amazon.com/social-messaging/latest/userguide/managing-event-destinations.html), inbound events are delivered through an **Amazon SNS** topic as the required "event destination" — `CareRelay-InboundTopic` fans out to the `webhook_receiver` Lambda. SNS has no WhatsApp-specific logic; it's plain AWS plumbing sitting between the Meta-facing service and our Lambda code.
- **RCS, falling back to SMS (AWS End User Messaging)** — doctor/clinic approval cards.
- **Amazon SES** — KMS-signed audit report emails to billing/ops staff, and a staff-onboarding email when a hospital registers.
- **Amazon Bedrock AgentCore Runtime** — hosts the Strands multi-agent backend as a container-based agent runtime, invoked per case by the `channel_dispatcher` Lambda.

No step in the actual coverage decision is made by a language model — see [Deterministic rules, not model guesses](#deterministic-rules-not-model-guesses) below.

---

## Multi-agent architecture (Strands)

A **Supervisor** agent coordinates three specialist agents using Strands' "agents as tools" pattern — the specialists are plain Strands `Agent` instances passed directly into the supervisor's `tools` list:

```
Supervisor (carerelay_supervisor)
  │
  ├─ 1. Intake Agent        -> extract_insurance_card (vision) + transcribe_voice_note
  │                             returns: ExtractedCard fields, symptom summary
  │
  ├─ 2. Verification Agent  -> check_prior_auth (rules_engine.py, deterministic)
  │                             + call_payer_ivr (simulated payer eligibility check)
  │                             returns: outcome, missing_documents, rationale
  │                             (ground truth - supervisor must not alter it)
  │
  └─ 3. Notification Agent  -> draft_patient_message, draft_doctor_approval_card,
                                draft_audit_summary
                                (drafts content only - never sends anything itself)
```

The supervisor's output is constrained to a structured `CaseResult` schema (`agent_app/schemas.py`) — the agent cannot return free-text prose as its final answer. `agent_app/main.py` additionally **independently re-runs `rules_engine.evaluate()`** against the agent's reported outcome before accepting it (`_verify_against_rules_engine`), rejecting the result if the model's narration doesn't match what the deterministic rules engine actually computed. This guards against a model hallucinating a rule citation or outcome.

### Deterministic rules, not model guesses

`agent_app/rules_engine.py` is a plain-Python rule evaluator over the `PayerRulesTable` (CPT code + payer -> requires-prior-auth / required documents). No agent or LLM call ever decides coverage — the Verification Agent's `check_prior_auth` tool calls this engine and returns its result verbatim. This was a deliberate design choice: a hackathon judge (or a real clinic) should be able to trust that "approved" means the deterministic rule table said so, not that a model guessed it.

---

## Repository layout

```
agent_app/                 Strands multi-agent backend (hosted on Bedrock AgentCore Runtime)
  agents/                  supervisor.py, intake_agent.py, verification_agent.py, notification_agent.py
  tools/                   documents.py (vision card extraction), messaging.py (draft_* tools), verification.py
  rules_engine.py          Deterministic payer/CPT coverage rules (no model in the loop)
  schemas.py               CaseResult / ExtractedCard / VerificationResult - the agent's structured contract
  main.py                  AgentCore entrypoint + independent rules-engine cross-check
  model_config.py          Bedrock model selection (shared boto3 session, see lambdas/common/aws_clients.py)

lambdas/
  common/                  Shared config, AWS client builders, logging, channel senders (WhatsApp/RCS/SMS/SES)
  webhook_receiver/        Receives WhatsApp/RCS webhook events, fetches media to S3, writes DynamoDB
  channel_dispatcher/      DynamoDB Stream consumer -> invokes the AgentCore Runtime -> sends
                            WhatsApp reply + RCS approval card + SES audit email
  dashboard_api/           Read-only case/stats API for the frontend, plus hospital-scoped
                            staff signup/login (PBKDF2-hashed passwords) and the onboarding
                            email template

cdk/                       AWS CDK v2 (Python) - StorageStack, MessagingStack, ComputeStack
  stacks/

frontend/                  React + TypeScript + Vite staff console ("Clinic Command Console")
  src/views/                 Login, Signup, Analytics (home), Cases, Rule Explorer
  src/lib/                   api.ts (live/mock data toggle), auth.ts (session), mockData.ts

scripts/                   Local setup/test utilities (see below) - no CDK deploy required to use them
seed/                      Demo staff account seed data
```

---

## Two interfaces, two personas

- **Patient → WhatsApp.** No app install. Sends a card photo + voice note, gets status updates and action buttons back in the same chat.
- **Doctor/clinic approver → RCS action card** (falls back to SMS). Approve/deny buttons for the visit slot.
- **Clinic staff (front desk, billing, admin) → web console.** Hospital-scoped login (signup collects hospital name/address/email/phone; login uses the generated alphanumeric Hospital ID + username + password), lands on an analytics home page, with case queue and payer rule explorer views.

Email (SES) is **never** sent to patients or payers — it's used only for the two internal/staff-facing flows: the staff onboarding email and the audit report email. See the module docstring in `lambdas/dashboard_api/onboarding_email.py` and `lambdas/channel_dispatcher/handler.py`.

---

## Quick start

Prerequisites: Python 3.11+, Node.js 18+, AWS CLI configured.

```bash
# 1. Install backend deps
python -m venv venv && venv\Scripts\Activate.ps1      # Windows (bash: source venv/bin/activate)
pip install -r requirements.txt

# 2. Configure
cp .env.example .env     # fill in AWS creds, Bedrock model id, WhatsApp/RCS/SMS/SES identities

# 3. Frontend
cd frontend && npm install && npm run build
```

### Current deployment status (direct-to-AWS, no `cdk deploy` yet)

**`cdk deploy` is deliberately deferred** (the AgentCore Runtime container build is the one genuinely costed piece). Everything else has already been stood up directly via boto3 scripts in `scripts/`, so the console and the inbound-message plumbing are real and running against AWS today - not mocked.

Run these once, in order, to reproduce the current live environment (each is idempotent - safe to re-run):

```bash
# --- Staff console backend ---
python scripts/setup_auth_infra.py          # StaffUsersTable + verify SES sender identity
python scripts/setup_case_infra.py          # PriorAuthTable + PayerRulesTable
python scripts/seed_payer_rules.py          # seed/payer_rules.json -> PayerRulesTable
python scripts/seed_prior_auth_cases.py     # seed/prior_auth_cases.json -> PriorAuthTable (demo cases)
python scripts/seed_staff_users.py          # seed/staff_users.json -> StaffUsersTable (demo logins)
python scripts/deploy_dashboard_api.py      # Lambda: CareRelay-DashboardApi
python scripts/deploy_api_gateway.py        # API Gateway REST API in front of it (prints the base URL)

# --- Inbound WhatsApp intake pipeline ---
python scripts/setup_intake_infra.py        # IntakeEventsTable (streamed) + PatientsTable
python scripts/setup_sns_topic.py           # CareRelay-InboundTopic SNS topic
python scripts/deploy_webhook_receiver.py   # Lambda: CareRelay-WebhookReceiver
python scripts/deploy_channel_dispatcher.py # Lambda: CareRelay-ChannelDispatcher + DynamoDB Stream trigger
python scripts/subscribe_webhook_to_sns.py  # subscribes WebhookReceiver to the SNS topic
```

After this, the frontend's live API base (`frontend/src/lib/api.ts:LIVE_API_BASE_DEFAULT`) points at the deployed API Gateway URL automatically - no manual config needed to demo the console.

**What is proven working right now** (verified with real AWS calls, not just code review):
- Console: signup/login, case list/detail/create, status updates with a timestamped activity log, payer rule authoring - all backed by real DynamoDB, over a real API Gateway endpoint.
- Inbound pipeline: a simulated WhatsApp-shaped message published to the SNS topic is correctly received by `webhook_receiver`, written to `IntakeEventsTable`, and triggers `channel_dispatcher` via the DynamoDB Stream - confirmed via CloudWatch Logs showing the full chain executing.

**What is NOT yet live** (the two pieces genuinely gated on cost/manual setup):
1. **Amazon Bedrock AgentCore Runtime** (the Strands agent container) - not deployed, since this is the `cdk deploy` step being deferred. `channel_dispatcher` already handles this gracefully: with `AGENT_RUNTIME_ARN` unset, it logs `agent.invoke.skipped.no_runtime_arn` and exits cleanly instead of erroring. Deploy with `cdk deploy --all` (see `cdk/stacks/compute_stack.py`) when ready, then set `AGENT_RUNTIME_ARN` in `.env` and re-run `scripts/deploy_channel_dispatcher.py`.
2. **A real WhatsApp Business Account (WABA) linked via AWS End User Messaging Social.** This is a manual, console-driven step that cannot be scripted - it requires a Meta Business account, phone number verification, and an AWS-side linking flow. Until this is done, the SNS topic has no real inbound traffic (only the simulated test message used for verification above). To complete it:
   - In the AWS console, go to **AWS End User Messaging Social** → link/onboard a WhatsApp Business Account.
   - Under that WABA's settings, add a **message and event destination** pointing at the SNS topic ARN printed by `scripts/setup_sns_topic.py` (`arn:aws:sns:<region>:<account>:CareRelay-InboundTopic`).
   - See AWS's own guide: ["Add a message and event destination to AWS End User Messaging Social"](https://docs.aws.amazon.com/social-messaging/latest/userguide/managing-event-destinations-add.html).

### Local pipeline test (no AWS deploy needed at all)

```bash
python scripts/local_pipeline_test.py
```

Runs the full agent pipeline (Strands supervisor + rules engine) against a sample case entirely locally.

---

## Security notes

- Staff passwords are hashed with PBKDF2-HMAC-SHA256 (260,000 iterations), never stored in plaintext.
- The dashboard API is unauthenticated-by-default for demo convenience, including the staff-initiated write routes (`POST /cases`, `PATCH /cases/{id}/status`, `POST /payer-rules`) — see the security note in `lambdas/dashboard_api/handler.py`. Add a Cognito/Lambda authorizer before any real deployment; until then, the `actor` field on activity log entries is self-reported by the client, not a verified identity.
- `patient_phone_masked` is pre-masked at write time; the dashboard API never returns a raw phone number.
- Audit report emails are signed with an asymmetric KMS key (RSASSA_PKCS1_V1_5_SHA_256) so recipients can verify the report wasn't altered.
- Multi-tenancy is currently scoped to staff auth only (signup/login are hospital-scoped via a composite `(hospital_id, username)` key). Case data is not yet filtered per hospital — documented explicitly in code comments rather than left as an unstated gap.

---

## License

MIT. See [`LICENSE`](LICENSE).
