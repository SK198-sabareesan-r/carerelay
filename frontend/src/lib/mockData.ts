import type {
  CaseDetail,
  CaseSummary,
  DraftedMessages,
  PayerEmail,
  PayerRule,
  Stats,
  TranscriptMessage,
} from "../types/case";

/**
 * Deterministic mock dataset so the console is fully demo-able with zero
 * AWS setup (npm run dev, no backend required). Mirrors exactly what
 * dashboard_api would return for a real deployment - see
 * lambdas/dashboard_api/handler.py.
 */

const now = Date.now();
const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();

// Mutable in mock mode so "Add case"/"Add rule"/status updates in the UI
// persist for the rest of the session (mirrors the real DynamoDB writes the
// live API performs) without needing any backend.
export const mockCases: CaseSummary[] = [
  {
    case_id: "case-7f3a1c",
    created_at: minutesAgo(4),
    status: "APPROVED",
    channel: "whatsapp",
    patient_name: "R. Sharma",
    patient_phone_masked: "***4821",
    cpt_code: "29881",
    procedure_name: "Knee arthroscopy, meniscectomy",
    payer_id: "PAYER-ACME",
    verification: {
      outcome: "PRIOR_AUTH_REQUIRED",
      requires_prior_auth: true,
      missing_documents: [],
      matched_rule_id: "ACME-29881-v1",
      rationale: "Rule ACME-29881-v1: Requires imaging within 90 days per ACME policy section 4.2",
      payer_simulated: true,
      payer_eligible: true,
      approval_code: "SIM-F83020BD",
    },
    extracted_card: {
      payer_name: "ACME Health",
      member_id: "W847162930",
      group_number: "GRP-2291",
      payer_id: "PAYER-ACME",
      confidence: 96.4,
    },
  },
  {
    case_id: "case-9b2e44",
    created_at: minutesAgo(19),
    status: "AWAITING_DOCUMENTS",
    channel: "whatsapp",
    patient_name: "A. Fernandes",
    patient_phone_masked: "***0157",
    cpt_code: "D2740",
    procedure_name: "Crown - porcelain/ceramic",
    payer_id: "PAYER-ACME",
    verification: {
      outcome: "INCOMPLETE_INFO",
      requires_prior_auth: true,
      missing_documents: ["clinical_notes", "xray_or_mri"],
      matched_rule_id: "ACME-D2740-v1",
      rationale: "Rule ACME-D2740-v1: Requires pre-treatment X-ray per ACME dental policy section 7.1",
      payer_simulated: false,
      payer_eligible: null,
      approval_code: null,
    },
    extracted_card: {
      payer_name: "ACME Health",
      member_id: "W119283746",
      group_number: "GRP-0042",
      payer_id: "PAYER-ACME",
      confidence: 89.1,
    },
  },
  {
    case_id: "case-1a77de",
    created_at: minutesAgo(42),
    status: "APPROVED",
    channel: "whatsapp",
    patient_name: "K. Iyer",
    patient_phone_masked: "***3390",
    cpt_code: "D0150",
    procedure_name: "Comprehensive oral evaluation",
    payer_id: "PAYER-ACME",
    verification: {
      outcome: "NOT_REQUIRED",
      requires_prior_auth: false,
      missing_documents: [],
      matched_rule_id: "ACME-D0150-v1",
      rationale: "Rule ACME-D0150-v1: Routine dental exam, no prior-auth required under ACME policy",
      payer_simulated: false,
      payer_eligible: null,
      approval_code: null,
    },
    extracted_card: {
      payer_name: "ACME Health",
      member_id: "W558213099",
      group_number: "GRP-2291",
      payer_id: "PAYER-ACME",
      confidence: 94.8,
    },
  },
  {
    case_id: "case-c40f12",
    created_at: minutesAgo(70),
    status: "DENIED",
    channel: "rcs",
    patient_name: "M. Desai",
    patient_phone_masked: "***7742",
    cpt_code: "29881",
    procedure_name: "Knee arthroscopy, meniscectomy",
    payer_id: "PAYER-GLOBALHEALTH",
    verification: {
      outcome: "PRIOR_AUTH_REQUIRED",
      requires_prior_auth: true,
      missing_documents: [],
      matched_rule_id: "GH-29881-v1",
      rationale: "Rule GH-29881-v1: Requires 6 weeks documented conservative treatment per GlobalHealth policy",
      payer_simulated: true,
      payer_eligible: false,
      approval_code: null,
    },
    extracted_card: {
      payer_name: "GlobalHealth",
      member_id: "GH-220194",
      group_number: "GRP-9910",
      payer_id: "PAYER-GLOBALHEALTH",
      confidence: 91.0,
    },
  },
  {
    case_id: "case-3e88a0",
    created_at: minutesAgo(95),
    status: "OPEN",
    channel: "whatsapp",
    patient_name: "S. Nair",
    patient_phone_masked: "***5521",
    cpt_code: "77067",
    procedure_name: "Screening mammography, bilateral",
    payer_id: "PAYER-GLOBALHEALTH",
    verification: {
      outcome: "NOT_REQUIRED",
      requires_prior_auth: false,
      missing_documents: [],
      matched_rule_id: "GH-77067-v1",
      rationale: "Rule GH-77067-v1: Preventive screening, no prior-auth required under GlobalHealth policy",
      payer_simulated: false,
      payer_eligible: null,
      approval_code: null,
    },
    extracted_card: {
      payer_name: "GlobalHealth",
      member_id: "GH-837201",
      group_number: "GRP-4471",
      payer_id: "PAYER-GLOBALHEALTH",
      confidence: 97.2,
    },
  },
];

const mockMessages: Record<string, CaseDetail["messages"]> = {
  "case-7f3a1c": {
    patient_message_body:
      "Good news - your insurance coverage for the knee procedure has been verified (approval code SIM-F83020BD). Your doctor's office has been notified to confirm your appointment slot.",
    patient_message_buttons: [{ id: "ack", title: "Thank you" }],
    doctor_card_body:
      "Patient: R. Sharma\nProcedure: Knee arthroscopy, meniscectomy (29881)\nPrior authorization verified with payer.",
    doctor_card_buttons: [
      { id: "approve_slot", title: "Approve Treatment Slot" },
      { id: "request_notes", title: "Request Extra Notes" },
    ],
    audit_headline: "Prior auth required for R. Sharma",
    audit_detail_lines: [
      "Case ID: case-7f3a1c",
      "Payer: PAYER-ACME  |  CPT: 29881",
      "Outcome: PRIOR_AUTH_REQUIRED",
      "Rule rationale: Rule ACME-29881-v1: Requires imaging within 90 days per ACME policy section 4.2",
      "Payer approval code: SIM-F83020BD",
    ],
  },
  "case-9b2e44": {
    patient_message_body:
      "We're processing your prior authorization. We still need: clinical notes, x ray or mri. Please reply with a photo or PDF of each.",
    patient_message_buttons: [{ id: "upload_docs", title: "Upload now" }],
    doctor_card_body:
      "Patient: A. Fernandes\nProcedure: Crown - porcelain/ceramic (D2740)\nMissing documents: clinical_notes, xray_or_mri.",
    doctor_card_buttons: [
      { id: "approve_slot", title: "Approve Treatment Slot" },
      { id: "request_notes", title: "Request Extra Notes" },
    ],
    audit_headline: "Incomplete info for A. Fernandes",
    audit_detail_lines: [
      "Case ID: case-9b2e44",
      "Payer: PAYER-ACME  |  CPT: D2740",
      "Outcome: INCOMPLETE_INFO",
      "Rule rationale: Rule ACME-D2740-v1: Requires pre-treatment X-ray per ACME dental policy section 7.1",
    ],
  },
  "case-1a77de": {
    patient_message_body: "Good news - your upcoming procedure does not require prior authorization. Your appointment is confirmed.",
    patient_message_buttons: [{ id: "ack", title: "Got it" }],
    doctor_card_body: "Patient: K. Iyer\nProcedure: Comprehensive oral evaluation (D0150)\nNo prior authorization required.",
    doctor_card_buttons: [
      { id: "approve_slot", title: "Approve Treatment Slot" },
      { id: "request_notes", title: "Request Extra Notes" },
    ],
    audit_headline: "No prior auth needed for K. Iyer",
    audit_detail_lines: [
      "Case ID: case-1a77de",
      "Payer: PAYER-ACME  |  CPT: D0150",
      "Outcome: NOT_REQUIRED",
      "Rule rationale: Rule ACME-D0150-v1: Routine dental exam, no prior-auth required under ACME policy",
    ],
  },
  "case-c40f12": {
    patient_message_body:
      "We're still verifying your insurance coverage for this procedure. We'll message you as soon as it's confirmed.",
    patient_message_buttons: [{ id: "ack", title: "Got it" }],
    doctor_card_body:
      "Patient: M. Desai\nProcedure: Knee arthroscopy, meniscectomy (29881)\nPrior authorization verified with payer.",
    doctor_card_buttons: [
      { id: "approve_slot", title: "Approve Treatment Slot" },
      { id: "request_notes", title: "Request Extra Notes" },
    ],
    audit_headline: "Payer declined eligibility for M. Desai",
    audit_detail_lines: [
      "Case ID: case-c40f12",
      "Payer: PAYER-GLOBALHEALTH  |  CPT: 29881",
      "Outcome: PRIOR_AUTH_REQUIRED",
      "Rule rationale: Rule GH-29881-v1: Requires 6 weeks documented conservative treatment per GlobalHealth policy",
    ],
  },
  "case-3e88a0": {
    patient_message_body: "Good news - your upcoming procedure does not require prior authorization. Your appointment is confirmed.",
    patient_message_buttons: [{ id: "ack", title: "Got it" }],
    doctor_card_body: "Patient: S. Nair\nProcedure: Screening mammography, bilateral (77067)\nNo prior authorization required.",
    doctor_card_buttons: [
      { id: "approve_slot", title: "Approve Treatment Slot" },
      { id: "request_notes", title: "Request Extra Notes" },
    ],
    audit_headline: "No prior auth needed for S. Nair",
    audit_detail_lines: [
      "Case ID: case-3e88a0",
      "Payer: PAYER-GLOBALHEALTH  |  CPT: 77067",
      "Outcome: NOT_REQUIRED",
      "Rule rationale: Rule GH-77067-v1: Preventive screening, no prior-auth required under GlobalHealth policy",
    ],
  },
};

const mockFacts: Record<string, string[]> = {
  "case-7f3a1c": ["Symptom summary: Patient reports persistent knee pain and swelling after a fall two weeks ago."],
  "case-9b2e44": ["Symptom summary: Patient needs a crown replacement following a cracked molar."],
  "case-1a77de": ["Symptom summary: Routine six-month dental check-up, no acute symptoms reported."],
  "case-c40f12": ["Symptom summary: Chronic knee instability, patient requesting surgical evaluation."],
  "case-3e88a0": ["Symptom summary: Annual preventive screening, no symptoms reported."],
};

function buildAgentTrace(c: CaseSummary, messages: CaseDetail["messages"], facts: string[]): CaseDetail["agent_trace"] {
  const cardLines = Object.entries(c.extracted_card)
    .filter(([k, v]) => k !== "confidence" && v)
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`);
  if (c.extracted_card.confidence != null) {
    cardLines.push(`extraction confidence: ${c.extracted_card.confidence}`);
  }

  const trace: CaseDetail["agent_trace"] = [
    { agent: "Intake", tool: "extract_insurance_card + transcribe_voice_note", detail: [...cardLines, ...facts] },
    {
      agent: "Verification",
      tool: "check_prior_auth",
      detail: [
        `outcome = ${c.verification.outcome}`,
        `matched_rule_id = ${c.verification.matched_rule_id}`,
        `rationale: ${c.verification.rationale}`,
        ...(c.verification.missing_documents.length
          ? [`missing_documents: ${c.verification.missing_documents.join(", ")}`]
          : []),
      ],
    },
  ];

  if (c.verification.payer_simulated) {
    trace.push({
      agent: "Verification",
      tool: "call_payer_ivr (SIMULATED)",
      detail: [
        `eligible = ${c.verification.payer_eligible}`,
        `approval_code = ${c.verification.approval_code ?? "n/a"}`,
      ],
    });
  }

  trace.push({
    agent: "Notification",
    tool: "draft_patient_message + draft_doctor_approval_card + draft_audit_summary",
    detail: [`patient message: ${messages.patient_message_body}`, `doctor card: ${messages.doctor_card_body}`],
  });

  return trace;
}

function buildActivityLog(c: CaseSummary): CaseDetail["activity_log"] {
  const created = new Date(c.created_at);
  const at = (mins: number) => new Date(created.getTime() + mins * 60_000).toISOString();
  const log: CaseDetail["activity_log"] = [
    { timestamp: at(0), event: "CREATED", actor: "system", detail: `Inbound ${c.channel} intake received.` },
    { timestamp: at(1), event: "AGENT_PROCESSED", actor: "agent", detail: "Insurance card read and documents captured." },
    {
      timestamp: at(2),
      event: "PAYER_CHECK",
      actor: "agent",
      detail: `Coverage checked - matched rule ${c.verification.matched_rule_id ?? "n/a"}.`,
    },
  ];
  if (c.verification.outcome === "PRIOR_AUTH_REQUIRED") {
    log.push({
      timestamp: at(3),
      event: "NOTIFIED",
      actor: "system",
      detail: "Prior-authorization request emailed to the payer.",
    });
  }
  log.push({ timestamp: at(4), event: "NOTIFIED", actor: "system", detail: "Patient and doctor notified." });
  return log;
}

export function mockCaseDetail(caseId: string): CaseDetail | undefined {
  const summary = mockCases.find((c) => c.case_id === caseId);
  if (!summary) return undefined;
  const messages = mockMessages[caseId] ?? {
    patient_message_body: "",
    patient_message_buttons: [],
    doctor_card_body: "",
    doctor_card_buttons: [],
    audit_headline: "",
    audit_detail_lines: [],
  };
  const facts = mockFacts[caseId] ?? [];
  return {
    ...summary,
    messages,
    perceived_facts: facts,
    narration: null,
    photo_url: null,
    audio_url: null,
    agent_trace: buildAgentTrace(summary, messages, facts),
    activity_log: buildActivityLog(summary),
    transcript: buildMockTranscript(summary, messages),
    payer_emails: buildMockPayerEmails(summary),
    // Mirrors the backend rule: a case only has a reply-able WhatsApp
    // thread if it came in via WhatsApp (channel_dispatcher only stores
    // patient_phone for that channel - see handler.py's _persist_case).
    can_message_patient: summary.channel === "whatsapp",
  };
}

/**
 * Builds a representative WhatsApp conversation for mock/demo mode so the
 * realtime thread view has content to render. In live mode this comes from
 * the backend `transcript` field instead.
 */
function buildMockTranscript(
  summary: CaseSummary,
  messages: DraftedMessages
): TranscriptMessage[] {
  if (summary.channel !== "whatsapp") return [];
  const base = new Date(summary.created_at).getTime();
  const t = (offsetMin: number) => new Date(base + offsetMin * 60_000).toISOString();
  const first = (summary.patient_name.split(" ")[0] || "there").replace(/\*+/g, "");

  const thread: TranscriptMessage[] = [
    {
      direction: "outbound",
      kind: "text",
      body: `Hello ${first || "there"}, this is ${summary.hospital_name || "your clinic"}. Your doctor has recommended a follow-up for ${summary.procedure_name}. To process your insurance, please reply with a clear photo of your insurance card and a short voice note describing your symptoms.`,
      actor: "staff",
      timestamp: t(0),
    },
    { direction: "inbound", kind: "image", body: "Insurance card photo", actor: "patient", timestamp: t(3) },
    { direction: "inbound", kind: "audio", body: "Voice note", actor: "patient", timestamp: t(4) },
  ];
  if (messages.patient_message_body) {
    thread.push({
      direction: "outbound",
      kind: "text",
      body: messages.patient_message_body,
      actor: "agent",
      timestamp: t(5),
    });
  }
  return thread;
}

/**
 * Builds the hospital <-> payer prior-authorization email correspondence
 * for mock/demo mode. Only populated when the case actually required prior
 * authorization (mirrors the backend, which only emails the payer then).
 */
function buildMockPayerEmails(summary: CaseSummary): PayerEmail[] {
  if (summary.verification.outcome !== "PRIOR_AUTH_REQUIRED") return [];
  const base = new Date(summary.created_at).getTime();
  const t = (offsetMin: number) => new Date(base + offsetMin * 60_000).toISOString();
  const clinic = summary.hospital_name || "CareRelay Clinic";
  const payer = summary.extracted_card.payer_name || summary.payer_id || "the payer";
  const subject = `Prior Authorization Request - ${summary.procedure_name} (CPT ${summary.cpt_code})`;
  return [
    {
      direction: "outbound",
      subject,
      from_addr: "priorauth@carerelay.health",
      to_addr: "intake@payer.example.com",
      from_label: clinic,
      to_label: payer,
      body:
        `Formal prior-authorization request sent to ${payer} for ${summary.procedure_name} ` +
        `(CPT ${summary.cpt_code}, member ${summary.extracted_card.member_id || "n/a"}). ` +
        `Clinical justification and the matched coverage rule ` +
        `(${summary.verification.matched_rule_id || "n/a"}) were included.`,
      message_id: "ses-0a1b2c3d",
      timestamp: t(6),
    },
    {
      direction: "inbound",
      subject: `RE: ${subject}`,
      from_addr: "intake@payer.example.com",
      to_addr: "priorauth@carerelay.health",
      from_label: payer,
      to_label: clinic,
      body:
        summary.verification.payer_eligible === false
          ? "Prior authorization could not be confirmed at this time. Additional clinical documentation may be required before a determination is issued."
          : "Prior authorization APPROVED for the requested procedure." +
            (summary.verification.approval_code
              ? ` Authorization reference: ${summary.verification.approval_code}.`
              : "") +
            " Please proceed and retain this reference for claims submission.",
      message_id: null,
      timestamp: t(42),
    },
  ];
}

export const mockPayerRules: PayerRule[] = [
  {
    payer_id: "PAYER-ACME",
    cpt_code: "29881",
    procedure_name: "Knee arthroscopy, meniscectomy",
    requires_prior_auth: true,
    required_documents: ["clinical_notes", "xray_or_mri"],
    rule_id: "ACME-29881-v1",
    notes: "Requires imaging within 90 days per ACME policy section 4.2",
  },
  {
    payer_id: "PAYER-ACME",
    cpt_code: "D0150",
    procedure_name: "Comprehensive oral evaluation",
    requires_prior_auth: false,
    required_documents: [],
    rule_id: "ACME-D0150-v1",
    notes: "Routine dental exam, no prior-auth required under ACME policy",
  },
  {
    payer_id: "PAYER-ACME",
    cpt_code: "D2740",
    procedure_name: "Crown - porcelain/ceramic",
    requires_prior_auth: true,
    required_documents: ["clinical_notes", "xray_or_mri"],
    rule_id: "ACME-D2740-v1",
    notes: "Requires pre-treatment X-ray per ACME dental policy section 7.1",
  },
  {
    payer_id: "PAYER-GLOBALHEALTH",
    cpt_code: "29881",
    procedure_name: "Knee arthroscopy, meniscectomy",
    requires_prior_auth: true,
    required_documents: ["clinical_notes", "xray_or_mri", "conservative_treatment_history"],
    rule_id: "GH-29881-v1",
    notes: "Requires 6 weeks documented conservative treatment per GlobalHealth policy",
  },
  {
    payer_id: "PAYER-GLOBALHEALTH",
    cpt_code: "77067",
    procedure_name: "Screening mammography, bilateral",
    requires_prior_auth: false,
    required_documents: [],
    rule_id: "GH-77067-v1",
    notes: "Preventive screening, no prior-auth required under GlobalHealth policy",
  },
];

export const mockStats: Stats = {
  total_cases: mockCases.length,
  by_outcome: mockCases.reduce<Record<string, number>>((acc, c) => {
    acc[c.verification.outcome] = (acc[c.verification.outcome] ?? 0) + 1;
    return acc;
  }, {}),
  by_status: mockCases.reduce<Record<string, number>>((acc, c) => {
    acc[c.status] = (acc[c.status] ?? 0) + 1;
    return acc;
  }, {}),
  by_channel: mockCases.reduce<Record<string, number>>((acc, c) => {
    acc[c.channel] = (acc[c.channel] ?? 0) + 1;
    return acc;
  }, {}),
  missing_documents: { clinical_notes: 1, xray_or_mri: 1 },
  payer_simulated_calls: mockCases.filter((c) => c.verification.payer_simulated).length,
  payer_eligible_calls: mockCases.filter((c) => c.verification.payer_eligible).length,
  avg_card_extraction_confidence:
    Math.round(
      (mockCases.reduce((s, c) => s + (c.extracted_card.confidence ?? 0), 0) / mockCases.length) * 10
    ) / 10,
};

// --------------------------------------------------------------------------- #
// Mock staff directory - mirrors the dummy accounts seeded into the real
// StaffUsersTable by scripts/seed_staff_users.py, so mock mode and live mode
// log in with the SAME credentials. See user_creds.json at the repo root.
// --------------------------------------------------------------------------- #
export const mockStaffDirectory: {
  username: string;
  password: string;
  display_name: string;
  role: string;
  hospital_id: string;
  hospital_name: string;
  hospital_address: string;
  hospital_email: string;
  hospital_phone: string;
}[] = [
  {
    username: "pnair",
    password: "CareRelay#2026",
    display_name: "Dr. Priya Nair",
    role: "Clinic Physician",
    hospital_id: "sunrisegeneralhospital",
    hospital_name: "Sunrise General Hospital",
    hospital_address: "221 Marine Drive, Mumbai, MH 400002",
    hospital_email: "contact@sunrisegeneral.example.com",
    hospital_phone: "+912266550100",
  },
  {
    username: "jfernandes",
    password: "CareRelay#2026",
    display_name: "Jo Fernandes",
    role: "Billing Coordinator",
    hospital_id: "sunrisegeneralhospital",
    hospital_name: "Sunrise General Hospital",
    hospital_address: "221 Marine Drive, Mumbai, MH 400002",
    hospital_email: "contact@sunrisegeneral.example.com",
    hospital_phone: "+912266550100",
  },
  {
    username: "admin",
    password: "CareRelay#2026",
    display_name: "Clinic Administrator",
    role: "Admin",
    hospital_id: "sunrisegeneralhospital",
    hospital_name: "Sunrise General Hospital",
    hospital_address: "221 Marine Drive, Mumbai, MH 400002",
    hospital_email: "contact@sunrisegeneral.example.com",
    hospital_phone: "+912266550100",
  },
  {
    username: "admin",
    password: "CareRelay#2026",
    display_name: "Lakeside Clinic Administrator",
    role: "Admin",
    hospital_id: "lakesidemedicalcenter",
    hospital_name: "Lakeside Medical Center",
    hospital_address: "14 Lakeview Road, Pune, MH 411001",
    hospital_email: "contact@lakesidemedical.example.com",
    hospital_phone: "+912066550200",
  },
];
