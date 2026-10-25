# CareRelay

**Conversational prior-authorization for clinics**, powered by a **Strands multi-agent** backend on **Amazon Bedrock AgentCore Runtime**, with **AWS Communication Developer Services (CDS)** — WhatsApp, RCS/SMS, and SES — as the messaging backbone.

Built for the **AWS CDS Agentic AI Hackathon (Sept. 2026)**.

A patient sends a photo of their insurance card and a voice note describing their procedure over **WhatsApp**. A Strands multi-agent pipeline extracts the card details, checks the payer's prior-authorization rules deterministically, and replies with a status update — all without the patient ever leaving the chat. The clinic's doctor/approver gets an **RCS action card** to approve the visit slot, and billing staff get a **KMS-signed audit email** for every case. Clinic staff manage the whole queue from a web console with their own hospital-scoped login.

---

## Why this fits AWS CDS

- **WhatsApp (AWS End User Messaging Social)** — patient intake (photo + voice note) and status replies with interactive buttons.
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

Prerequisites: Python 3.11+, Node.js 18+, AWS CLI configured, AWS CDK v2 (`npm i -g aws-cdk`), Docker (for the AgentCore Runtime container build).

```bash
# 1. Install backend deps
python -m venv venv && venv\Scripts\Activate.ps1      # Windows (bash: source venv/bin/activate)
pip install -r requirements.txt

# 2. Configure
cp .env.example .env     # fill in AWS creds, Bedrock model id, WhatsApp/RCS/SMS/SES identities

# 3. Frontend
cd frontend && npm install && npm run build

# 4. Deploy (full stack - see cdk/ for StorageStack/MessagingStack/ComputeStack)
cd cdk
cdk bootstrap
cdk deploy --all
```

### Testing locally before deploying (no `cdk deploy` needed)

This project deliberately defers the full CDK deploy until everything else is verified against real AWS, to control cost. The `scripts/` directory has standalone utilities that exercise the real AWS services directly:

```bash
# Create just the staff-auth DynamoDB table + verify the SES sender identity
python scripts/setup_auth_infra.py

# Check SES identity verification / sandbox status
python scripts/check_ses_identity.py

# Seed demo staff accounts (see user_creds.json, gitignored, for the plaintext demo logins)
python scripts/seed_staff_users.py

# Run the full agent pipeline against a sample case, no deploy required
python scripts/local_pipeline_test.py
```

---

## Security notes

- Staff passwords are hashed with PBKDF2-HMAC-SHA256 (260,000 iterations), never stored in plaintext.
- The dashboard API is unauthenticated-by-default for demo convenience on the read-only `/cases`, `/stats`, `/payer-rules` routes — see the security note in `lambdas/dashboard_api/handler.py`. Add a Cognito/Lambda authorizer before any real deployment.
- `patient_phone_masked` is pre-masked at write time; the dashboard API never returns a raw phone number.
- Audit report emails are signed with an asymmetric KMS key (RSASSA_PKCS1_V1_5_SHA_256) so recipients can verify the report wasn't altered.
- Multi-tenancy is currently scoped to staff auth only (signup/login are hospital-scoped via a composite `(hospital_id, username)` key). Case data is not yet filtered per hospital — documented explicitly in code comments rather than left as an unstated gap.

---

## License

MIT. See [`LICENSE`](LICENSE).
