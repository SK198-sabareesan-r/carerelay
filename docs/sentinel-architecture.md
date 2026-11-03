# CareRelay Sentinel — Architecture

CareRelay Sentinel is a multi-agent **evidence-reconciliation and
exception-investigation** layer that sits on top of the original CareRelay
prior-authorization workflow. Its job is to check, before a prior-auth case
advances, whether the submitted documentation is **complete, consistent,
source-linked, and safe for a human to act on** — and to stop a case that
isn't.

Its guiding principle is the same one that runs through CareRelay:

> **Code decides, AI talks.** The language model handles perception (reading
> documents) and narration (explaining findings). Every *decision* — what a
> payer requires, whether documents conflict, whether a case may advance — is
> made by deterministic code, and every such decision is traceable to a
> specific rule or document.

---

## The problem it solves

A prior-auth case arrives with several documents: an insurance card, a
procedure order, clinical notes, an imaging report, the payer policy. Care
gets delayed — or worse, an unsupported case advances — when those documents
quietly disagree, a required document is missing, or a field was read with low
confidence. Sentinel catches exactly these issues and produces a
human-verifiable readiness report instead of a silent "looks fine."

---

## The pipeline

```
          intake / document normalization
                        │
                        ▼
        ┌───────────────────────────────────┐
        │   Evidence Workflow (parallel)     │
        │   • policy retrieval               │
        │   • cross-document reconciliation  │
        │            fan-in ▼                │
        │   • deterministic readiness engine │
        └───────────────────────────────────┘
                        │ ReadinessReport (status + checks + discrepancies)
                        ▼
                Decider 2B (bounded router)
          ┌──────────────┬──────────────┬───────────────┐
          ▼              ▼              ▼               ▼
  CONTINUE_        REQUEST_       INVESTIGATE_     HUMAN_REVIEW_
  VERIFICATION     MISSING_       CONFLICT         REQUIRED
                   EVIDENCE          │
                        │            ▼
                        │     Exception Swarm
                        │     (Document · Policy ·
                        │      Consistency · Safety Critic)
                        ▼            │
              Safety Critic (deterministic floor + agent)
                        │
                        ▼
        Deterministic Safety & State Engine
        (validates the transition; blocks unresolved criticals)
                        │
                        ▼
              Ready for human review  ·  or held
```

---

## Components

### Deterministic services (`agent_app/services/`)
The "code decides" core. No model calls for any decision.

| Service | Responsibility |
|---|---|
| `evidence_extraction` | Normalize raw/structured documents (or live OCR + Transcribe) into one `CaseEvidence`, canonicalizing the payer. |
| `policy_retrieval` | Turn the matched payer rule into atomic, checkable `PolicyRequirement`s (each with a rule id + policy citation). |
| `reconciliation` | Detect cross-document field mismatches, low-confidence reads, and illegible documents. |
| `readiness_engine` | Compute per-requirement satisfied/unsatisfied checks and the overall `ReadinessStatus`. The single source of truth for "can this case progress?" |
| `state_transition` | Validate case-status transitions; block progressions toward authorization while a critical discrepancy is unresolved. |
| `audit_service` | Append-only, timestamped trail of every step (what the dashboard renders). |

### Specialist agents (`agent_app/agents/`)
Seven agents. Two carried over from CareRelay, five new. Every agent narrates
or perceives; none decides.

| Agent | Role |
|---|---|
| Intake *(existing)* | Extract card fields + transcribe the voice note. |
| Document Intelligence *(new)* | Classify and quality-check documents; produce a source-linked inventory. |
| Policy Research *(new)* | Retrieve and explain payer requirements, with citations. |
| Clinical Consistency *(new)* | Explain each detected conflict and propose a human follow-up. |
| Case Readiness *(new)* | Narrate the deterministic readiness verdict verbatim. |
| Safety Critic *(new)* | Independently challenge conclusions; force human review. Holds **no** decision tools by design. |
| Notification *(existing)* | Draft the patient/doctor/audit messages. |

### Orchestration (`agent_app/orchestration/`)
- **`case_graph`** — Graph-led coordinator. `run_case()` is the executable,
  deterministic control flow (offline-testable); `build_case_graph()` is a
  real Strands `GraphBuilder` graph of the same lifecycle.
- **`evidence_workflow`** — composed task-DAG running policy retrieval and
  reconciliation in parallel, then the readiness engine.
- **`decider_router`** — **Decider 2B**: a bounded router that selects exactly
  one of four next-actions (`CONTINUE_VERIFICATION`, `REQUEST_MISSING_EVIDENCE`,
  `INVESTIGATE_CONFLICT`, `HUMAN_REVIEW_REQUIRED`). It is rules-first and never
  approves coverage — it only chooses what the pipeline does next.
- **`exception_swarm`** — a real Strands `Swarm` (bounded handoffs/iterations)
  that investigates complex conflicts. It produces narrative only; it cannot
  clear a discrepancy.
- **`case_state`** — the serializable `CaseState` that flows through all of the
  above and carries the audit trail.

### Safety model (why it can be trusted)
Two independent floors guarantee an unsafe case can't advance:
1. The **readiness engine** sets `can_progress = false` whenever a critical
   requirement is unsatisfied or a critical conflict is open.
2. The **state-transition engine** refuses any progression toward
   authorization while `can_progress` is false — regardless of what an agent,
   the Decider, or a client request wants.

The Safety Critic adds an adversarial review on top, and can force human
review even when the deterministic checks pass.

---

## The Strands patterns used

| Pattern | Where | Why |
|---|---|---|
| **Graph** | main case lifecycle | developer-defined flow with conditional branches |
| **Workflow** (composed task-DAG) | parallel evidence analysis | independent tasks, pure speed-up |
| **Swarm** | complex-conflict investigation | autonomous specialist hand-offs, bounded |
| **Agents-as-tools** | retained from CareRelay where useful | supervisor/specialist arrangement |

A2A is intentionally not used in this version.

---

## The driving test scenario

A synthetic 5-document case (`tests/`) with three deliberately-injected issues:

1. **Procedure-code mismatch** — the order says CPT `29881`, the clinical
   notes say `29826`.
2. **Missing document** — the required imaging report is absent.
3. **Low-confidence read** — the member ID was extracted with low confidence.

The pipeline must detect all three, route via the Decider, (optionally)
investigate via the Swarm, produce a source-linked readiness report, **block
progression**, and then **clear the case** once corrected evidence is
re-submitted. All of this is covered by 30 offline, deterministic tests.

---

## Production safety fixes shipped alongside

- **Signed session tokens** (HMAC) issued at login/signup; every other API
  route requires a valid token.
- **Tenant isolation** — a case is visible only to its own hospital; identity
  and hospital are derived from the verified token, never from the request
  body.
- **Simulated payer responses are explicitly labelled** as demonstration-only,
  never presented as a genuine insurer confirmation.
- **Deterministic status-transition gate** rejects illegal or unsafe jumps.
- **Full API surface wired** (follow-ups, status, messaging, readiness, rule
  authoring) behind auth.
- **Data-retention safeguard** — PHI-bearing stores default to retain +
  point-in-time recovery; a demo flag restores disposable teardown.
