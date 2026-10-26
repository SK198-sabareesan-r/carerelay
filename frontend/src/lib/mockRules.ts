import type { PayerRule, VerificationResult } from "../types/case";
import { mockPayerRules } from "./mockData";

/**
 * Mirrors agent_app/rules_engine.py:evaluate() so mock-mode "Add case"
 * produces the SAME kind of deterministic outcome the live API's
 * _evaluate_rules() wrapper does - never a hand-rolled placeholder. Kept
 * intentionally tiny (no model, no network) to match the real module's
 * "NO LLM CALLS IN THIS FILE" rule.
 */
export function evaluateMockRules(payerId: string, cptCode: string): VerificationResult {
  const rule: PayerRule | undefined = mockPayerRules.find(
    (r) => r.payer_id === payerId && r.cpt_code === cptCode
  );

  if (!rule) {
    return {
      outcome: "NO_MATCHING_RULE",
      requires_prior_auth: true,
      missing_documents: [],
      matched_rule_id: null,
      rationale: `No rule found for payer=${payerId} cpt=${cptCode}. Defaulting to manual review (fail-safe).`,
      payer_simulated: false,
      payer_eligible: null,
      approval_code: null,
    };
  }

  if (!rule.requires_prior_auth) {
    return {
      outcome: "NOT_REQUIRED",
      requires_prior_auth: false,
      missing_documents: [],
      matched_rule_id: rule.rule_id,
      rationale: `Rule ${rule.rule_id}: ${rule.notes || "no prior-auth required"}`,
      payer_simulated: false,
      payer_eligible: null,
      approval_code: null,
    };
  }

  // No documents on file yet for a freshly-logged case, same as the live API.
  const missing = [...rule.required_documents];
  return {
    outcome: missing.length ? "INCOMPLETE_INFO" : "PRIOR_AUTH_REQUIRED",
    requires_prior_auth: true,
    missing_documents: missing,
    matched_rule_id: rule.rule_id,
    rationale: `Rule ${rule.rule_id}: ${rule.notes || "prior authorization required"}`,
    payer_simulated: false,
    payer_eligible: null,
    approval_code: null,
  };
}
