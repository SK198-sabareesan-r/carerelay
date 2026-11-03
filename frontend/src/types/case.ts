/**
 * Mirrors the shape returned by lambdas/dashboard_api/handler.py and the
 * Pydantic schemas in agent_app/schemas.py. Keep these two definitions in
 * sync when either side changes.
 */

export type CaseStatus =
  | "OPEN"
  | "APPROVED"
  | "DENIED"
  | "AWAITING_DOCUMENTS"
  // Follow-up flow lifecycle states.
  | "AWAITING_INSURANCE_DOCS"
  | "AWAITING_VOICE_NOTE"
  | "AWAITING_PAYER"
  | "PENDING_DOCTOR_APPROVAL"
  | "SCHEDULED";

export type PriorAuthOutcome =
  | "PRIOR_AUTH_REQUIRED"
  | "NOT_REQUIRED"
  | "INCOMPLETE_INFO"
  | "NO_MATCHING_RULE";

export type Channel = "whatsapp" | "rcs" | "sms";

export interface ExtractedCard {
  payer_name?: string | null;
  member_id?: string | null;
  group_number?: string | null;
  payer_id?: string | null;
  confidence?: number | null;
}

export interface VerificationResult {
  outcome: PriorAuthOutcome;
  requires_prior_auth: boolean;
  missing_documents: string[];
  matched_rule_id?: string | null;
  rationale: string;
  payer_simulated: boolean;
  payer_eligible?: boolean | null;
  approval_code?: string | null;
}

export interface DraftedMessages {
  patient_message_body: string;
  patient_message_buttons: { id: string; title: string }[];
  doctor_card_body: string;
  doctor_card_buttons: { id: string; title: string }[];
  audit_headline: string;
  audit_detail_lines: string[];
}

export interface AgentTraceStep {
  agent: "Intake" | "Verification" | "Notification";
  tool: string;
  detail: string[];
}

export interface ActivityLogEntry {
  timestamp: string;
  event: string;
  actor: string;
  detail: string;
}

export type TranscriptDirection = "inbound" | "outbound";
export type TranscriptKind = "text" | "image" | "audio" | "button" | "interactive";

export interface TranscriptMessage {
  direction: TranscriptDirection;
  kind: TranscriptKind;
  body: string;
  actor: string;
  timestamp: string;
}

/** One email in the hospital <-> payer prior-authorization correspondence. */
export interface PayerEmail {
  direction: "inbound" | "outbound"; // outbound = clinic->payer, inbound = payer->clinic
  subject: string;
  from_addr: string;
  to_addr: string;
  from_label: string;
  to_label: string;
  body: string;
  message_id?: string | null;
  timestamp: string;
}

export interface CaseSummary {
  case_id: string;
  created_at: string;
  status: CaseStatus;
  channel: Channel;
  flow?: string | null;
  has_insurance?: boolean | null;
  appointment_datetime?: string | null;
  appointment_released?: boolean | null;
  hospital_id?: string | null;
  hospital_name?: string | null;
  patient_name: string;
  patient_phone_masked: string;
  cpt_code: string;
  procedure_name: string;
  payer_id: string;
  verification: VerificationResult;
  extracted_card: ExtractedCard;
}

export interface CaseDetail extends CaseSummary {
  messages: DraftedMessages;
  perceived_facts: string[];
  narration?: string | null;
  photo_url?: string | null;
  audio_url?: string | null;
  agent_trace: AgentTraceStep[];
  activity_log: ActivityLogEntry[];
  transcript?: TranscriptMessage[];
  payer_emails?: PayerEmail[];
  can_message_patient: boolean;
}

// ---------------------------------------------------------------------------
// CareRelay Sentinel: evidence-reconciliation & readiness types.
// Mirror agent_app/models/* (case_evidence, policy_requirement, discrepancy,
// readiness_report). Keep in sync when the Python models change.
// ---------------------------------------------------------------------------

export type FieldConfidence = "high" | "medium" | "low";

export type DocumentKind =
  | "insurance_card"
  | "procedure_order"
  | "clinical_notes"
  | "xray_or_mri"
  | "conservative_treatment_history"
  | "referral"
  | "lab_result"
  | "payer_policy"
  | "unknown";

export interface SentinelExtractedField {
  name: string;
  value?: string | null;
  source_document_id: string;
  confidence: FieldConfidence;
  note?: string | null;
}

export interface EvidenceDocument {
  id: string;
  kind: DocumentKind;
  s3_key?: string | null;
  legible: boolean;
  classification_confidence: FieldConfidence;
  fields: SentinelExtractedField[];
  raw_text?: string | null;
}

export interface CaseEvidence {
  case_id: string;
  patient_name?: string | null;
  payer_id?: string | null;
  cpt_code?: string | null;
  procedure_name?: string | null;
  documents: EvidenceDocument[];
  symptom_summary?: string | null;
}

export type Severity = "critical" | "warning" | "info";

export type DiscrepancyKind =
  | "field_mismatch"
  | "missing_document"
  | "missing_field"
  | "low_confidence"
  | "illegible_document"
  | "unsupported_requirement"
  | "timing";

export interface Discrepancy {
  id: string;
  kind: DiscrepancyKind;
  severity: Severity;
  field_name?: string | null;
  summary: string;
  source_document_ids: string[];
  conflicting_values: string[];
  related_requirement_id?: string | null;
  explanation?: string | null;
  recommended_action?: string | null;
  resolved: boolean;
}

export type ReadinessStatus =
  | "ready_for_human_review"
  | "missing_evidence"
  | "conflict"
  | "blocked";

export interface RequirementCheck {
  requirement_id: string;
  description: string;
  satisfied: boolean;
  satisfied_by_document_id?: string | null;
  critical: boolean;
  note?: string | null;
}

export interface ReadinessReport {
  case_id: string;
  payer_id?: string | null;
  cpt_code?: string | null;
  matched_rule_id?: string | null;
  status: ReadinessStatus;
  requirement_checks: RequirementCheck[];
  discrepancies: Discrepancy[];
  summary?: string | null;
  safety_notes?: string | null;
  can_progress?: boolean;
}

export interface PayerRule {
  payer_id: string;
  cpt_code: string;
  procedure_name: string;
  requires_prior_auth: boolean;
  required_documents: string[];
  rule_id: string;
  notes: string;
}

export interface Stats {
  total_cases: number;
  by_outcome: Record<string, number>;
  by_status: Record<string, number>;
  by_channel: Record<string, number>;
  missing_documents: Record<string, number>;
  payer_simulated_calls: number;
  payer_eligible_calls: number;
  avg_card_extraction_confidence: number | null;
}
