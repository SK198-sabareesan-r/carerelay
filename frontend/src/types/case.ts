/**
 * Mirrors the shape returned by lambdas/dashboard_api/handler.py and the
 * Pydantic schemas in agent_app/schemas.py. Keep these two definitions in
 * sync when either side changes.
 */

export type CaseStatus = "OPEN" | "APPROVED" | "DENIED" | "AWAITING_DOCUMENTS";

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

export interface CaseSummary {
  case_id: string;
  created_at: string;
  status: CaseStatus;
  channel: Channel;
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
