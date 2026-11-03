# CareRelay: Turning Insurance Prior-Authorization Into a WhatsApp Conversation with AWS Agentic AI

> How I built a multi-agent system on AWS that reads an insurance card, transcribes a voice note, verifies coverage against a deterministic rules engine, and routes approvals across WhatsApp and email — guided by one principle: **code decides, AI talks.**

![CareRelay — prior-authorization as a conversation](REPLACE_WITH: docs/thumbnail.png)
*Suggested caption: CareRelay turns clinic prior-authorization into a guided chat on WhatsApp.*

---

## The problem that started it

If you've ever had a medical procedure delayed, there's a good chance the culprit wasn't your doctor — it was **prior-authorization**.

After a consultation, a follow-up procedure often has to be approved by the patient's insurer before it can be scheduled. In practice that means clinic staff sitting on hold with payers, re-typing member IDs off a photo of an insurance card, faxing clinical notes, and playing phone tag for days. Meanwhile the patient is left in the dark — many don't even learn their appointment time until coverage finally clears.

I kept coming back to one question:

> **What if the entire prior-auth back-and-forth happened in the channel patients already use every day — a chat thread — while staff got a clean, auditable cockpit instead of a phone queue?**

That question became **CareRelay**.

---

## What CareRelay does, in one paragraph

A hospital signs up, staff start a follow-up from a web console, and the patient simply has a conversation over WhatsApp — they send a photo of their insurance card and a short voice note describing their symptoms. Behind that conversation, a team of AI agents does the paperwork: OCR reads the card, Amazon Transcribe turns the voice note into a symptom summary, and a **deterministic rules engine** makes the actual coverage decision. If prior-auth is needed, CareRelay opens an email thread with the payer. A doctor approves with a single tap, and only then is the appointment time released to the patient.

![End-to-end architecture](REPLACE_WITH: docs/architecture.png)
*Suggested caption: The CareRelay architecture — channels in, multi-agent core, deterministic decisioning, and an auditable staff console.*

---

## The design principle: "code decides, AI talks"

The single most important decision in this project was **not** letting the language model decide whether a procedure is covered.

In a regulated workflow like healthcare, "the AI approved it" is not an acceptable answer. So I split responsibilities cleanly:

- **The AI handles perception and language** — reading insurance cards, transcribing speech, and writing the human-friendly messages.
- **A deterministic rules engine owns every decision** — it maps a payer and CPT code to a policy and returns a structured outcome *plus the exact rule text that produced it*.

The agent then *narrates* that result. It never invents it. Every outcome ties back to a specific, quotable rule like:

```
Rule ACME-29881-v1: Requires imaging within 90 days per ACME policy section 4.2
```

That separation is what makes the system trustworthy — and it's a pattern I'd reuse for any high-stakes agentic application.

---

## The complete flow, end to end

### 1. Hospital sign-up and onboarding

Everything starts on the sign-up screen. A hospital registers with its name, address, contact email, and phone (captured with an explicit country code), plus the first staff member's details and role.

From the hospital name, CareRelay generates an **alphanumeric Hospital ID** that every staff account at that clinic shares — this is what makes the platform **multi-tenant**: each hospital's cases, rules, and conversations are scoped to its own ID. On successful sign-up, a branded onboarding email goes out over **Amazon SES**, sent under the hospital's own name so it reads as the clinic's communication.

![Sign-up and onboarding](REPLACE_WITH: screenshot of the Sign-up / Login screen)
*Suggested caption: Hospital sign-up generates a multi-tenant Hospital ID and triggers an SES onboarding email.*

### 2. Starting a follow-up

From the console, staff start a follow-up with the patient's name and WhatsApp number (with country code), the recommended procedure, an optional CPT code, insured vs. self-pay, and the intended appointment time — **deliberately withheld from the patient** until coverage clears. The appointment is the leverage that keeps the loop moving.

Notably, staff never type the insurer, member ID, or group number. Those are read automatically from the card the patient sends.

![Start a follow-up](REPLACE_WITH: screenshot of the "Start a follow-up" form)
*Suggested caption: Staff kick off a case; insurance details are never typed by hand.*

### 3. The patient conversation on WhatsApp

The patient receives a WhatsApp message from the clinic asking for two things: a clear photo of their insurance card (**front and back**) and a short voice note describing their symptoms. CareRelay waits until it has **both sides** of the card before processing, so a half-complete submission never produces a half-wrong decision. The conversation is **idempotent** — one inbound photo means one action, so the prompt never loops.

![WhatsApp conversation](REPLACE_WITH: screenshot of the patient WhatsApp thread — card photos + voice note + agent reply)
*Suggested caption: The patient-facing experience is just a chat — card, voice note, done.*

### 4. Automatic intake — OCR and transcription

As soon as both card sides and the voice note arrive, the agents go to work. **OCR** reads the front and back of the card and merges them into a single structured record (insurer, member ID, group number, payer ID). **Amazon Transcribe** turns the voice note into a symptom summary. The extracted fields populate the case in the console automatically — no manual data entry.

![Auto-extracted fields](REPLACE_WITH: screenshot of the case detail with populated card fields + transcribed symptoms)
*Suggested caption: Card fields and a symptom summary, extracted automatically.*

### 5. Verification — the deterministic rules engine

A Verification agent runs the case through the rules engine. It canonicalizes the payer (mapping an insurer name or payer ID read off the card to a known policy), evaluates the CPT-level rule, and returns one of a few structured outcomes — **approved**, **prior-auth required**, or **incomplete information** — along with any missing documents and a verbatim rule rationale.

![Rules-engine outcome](REPLACE_WITH: screenshot of the verification outcome + rule rationale + missing documents)
*Suggested caption: Every decision is explainable and auditable — the rule text is right there.*

### 6. Payer correspondence over email

If prior-auth is required, a Notification agent opens an email thread with the payer over **Amazon SES** and moves the case to **Awaiting Payer**. Both inbound and outbound payer emails are captured with timestamps and shown in the console as an evidence trail.

![Payer email thread](REPLACE_WITH: screenshot of the payer email thread / evidence view)
*Suggested caption: The whole negotiation with the insurer, logged with timestamps.*

### 7. Human-in-the-loop doctor approval

When documentation is complete, staff move the case to **Pending Doctor Approval** — which dispatches an approval card to the doctor over WhatsApp. The doctor taps approve, and the case advances to **Approved**. The physician stays in control of the clinical decision; CareRelay handles everything around it.

![Doctor approval card](REPLACE_WITH: screenshot of the doctor's WhatsApp approval card)
*Suggested caption: A one-tap clinical approval card, delivered over WhatsApp.*

### 8. Releasing the appointment

Only after approval does staff message the patient their appointment time, moving the case to **Scheduled**. The patient has gone from "send me your card" to a confirmed, insurance-cleared appointment — entirely within a chat thread.

**The full case lifecycle:**

```
Open → Awaiting Documents → Awaiting Payer → Pending Doctor Approval → Approved → Scheduled
                                                                              (or → Denied)
```

![Staff dashboard](REPLACE_WITH: screenshot of the dashboard — case list + status analytics)
*Suggested caption: The staff cockpit — analytics, intake queue, and the full case lifecycle at a glance.*

---

## How I built it (and which AWS services, and why)

CareRelay is a cloud-native, event-driven system with a **Strands multi-agent core**.

**Channels in, channels out**
- **AWS End User Messaging (WhatsApp)** — the patient-facing channel for card photos, voice notes, and replies. WhatsApp is where patients already are.
- **AWS End User Messaging (RCS / SMS)** — a second rich channel for reaching patients and approvers, with SMS as a universal fallback.
- **Amazon SES** — all transactional and payer email: onboarding at sign-up and the full prior-auth thread with insurers. One verified, auditable outbound path.

**The agent brain**
- **Strands Agents SDK** — orchestrates a Supervisor agent over specialized agents: Intake (OCR + transcription), Verification (rules engine), and Notification (email + channel dispatch).
- **Amazon Bedrock** — the vision + language model that reads insurance-card images and drives the conversation.
- **Amazon Bedrock AgentCore** — the managed agent-runtime target for hosting the Strands agents.
- **Amazon Transcribe** — converts patient voice notes into text symptom summaries.

**Decisioning**
- A standalone **rules engine** — my own deterministic code that owns every coverage decision and emits a verbatim rationale. This is the heart of *code decides, AI talks.*

**Eventing, state, and storage**
- **Amazon API Gateway** — the HTTPS front door for inbound webhooks and the console API.
- **AWS Lambda** — event-driven compute: a webhook receiver, a channel dispatcher, and a dashboard API. Serverless scales to zero between messages.
- **Amazon SNS** — fans inbound events out to handlers, decoupling ingestion from processing.
- **Amazon DynamoDB (with Streams)** — the system of record for staff accounts, cases, messages, payer rules, and the audit trail.
- **Amazon S3** — stores card images and voice-note audio.
- **AWS KMS** — encrypts sensitive data at rest.

**Delivery and packaging**
- **Amazon ECR** — container registry for the agent image.
- **AWS Amplify** — hosts the React + TypeScript + Vite staff console.

**Why this shape?** Event-driven serverless (API Gateway → SNS → Lambda → DynamoDB Streams) gives resilience and lets you add channels one at a time, while the agent layer stays focused on perception and language and the rules engine stays focused on decisions. Each service does one job well.

---

## Challenges I ran into

- **Making an AI system trustworthy for a regulated workflow.** The fix was architectural: the rules engine owns the decision, the agents own the conversation. Every outcome maps back to a quotable rule.
- **Reliable extraction from messy inputs.** Cards arrive as angled phone photos, front and back separately. I merged both sides into one structured record and made the flow wait for both before processing — and hardened storage handling so transcription never silently failed.
- **Idempotency and duplicate events.** A single inbound photo could be processed multiple times and re-trigger the "send your card" prompt. I hardened event handling so one message means one action, and the conversation never loops.
- **Keeping the dashboard honest.** I reconciled status counts, collapsed noisy categories into a few meaningful ones, and made the WhatsApp and email panels real-time and faithful to what actually happened on the channels.
- **Human-in-the-loop routing.** I added a dedicated *Pending Doctor Approval* transition that dispatches the doctor's card at exactly the right moment, with approver routing driven by configuration rather than hard-coded values.

---

## What I learned

- For regulated, high-stakes workflows, the winning pattern is to **narrow the AI's job**: use it for perception and language, and keep the decision in deterministic, auditable code.
- **Event-driven design pays off** — API Gateway + SNS + Lambda + DynamoDB Streams made the system resilient and easy to extend channel by channel.
- **Conversation UX is a feature, not a wrapper.** Getting idempotency, "both sides of the card," and withheld appointment times right is what made the flow feel trustworthy.

---

## What's next

- Deeper payer integrations (structured EDI/API where available) alongside the email fallback.
- Richer RCS experiences — carousels and quick-reply approval cards for doctors.
- A self-service policy editor so clinics can encode payer rules without code.
- Analytics on turnaround time and approval rates to quantify how much faster care gets scheduled.

---

## See the code

CareRelay is open source (MIT). The full source — the Strands agents, the rules engine, the Lambdas, the CDK infrastructure, and the React console — is on GitHub:

**👉 https://github.com/sk198-sabareesan-r/carerelay**

If you're building agentic systems on AWS, I'd love your feedback — especially on the "code decides, AI talks" split. That boundary between what the model is allowed to *say* versus what it's allowed to *decide* is, I think, the most important design question in production agentic AI.

---

*Built with AWS End User Messaging (WhatsApp, RCS/SMS), Amazon SES, Amazon Bedrock, Amazon Bedrock AgentCore, Amazon Transcribe, AWS Lambda, Amazon DynamoDB, Amazon SNS, Amazon S3, Amazon API Gateway, Amazon ECR, AWS KMS, AWS Amplify, and the Strands Agents SDK.*

*If you found this useful, a few claps help it reach other builders. Follow for more AWS agentic AI write-ups.*
