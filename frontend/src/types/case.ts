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
