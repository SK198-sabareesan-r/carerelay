"""Entrypoint for the CareRelay agent backend on Amazon Bedrock AgentCore Runtime.

Wraps the Strands supervisor (Intake -> Verification -> Notification) in a
BedrockAgentCoreApp so it can be containerized and deployed as a single
AgentCore Runtime. The channel_dispatcher Lambda invokes this runtime via
bedrock-agentcore's invoke_agent_runtime API once per patient case.

Local testing (no AWS deploy required):
    python agent_app/main.py
    curl -X POST http://localhost:8080/invocations \
      -H "Content-Type: application/json" \
      -d '{"payer_id": "PAYER-ACME", "cpt_code": "29881", ...}'

See docs/DEPLOYMENT.md for building the container and creating the runtime.
"""
import json
from typing import Any, Dict, Optional

from bedrock_agentcore.runtime import BedrockAgentCoreApp

from agent_app import rules_engine
from agent_app.agents.supervisor import build_supervisor
from agent_app.tools.verification import _load_rules_safely

app = BedrockAgentCoreApp()

# Built once per container instance and reused across invocations within
# the same microVM session (AgentCore gives each session its own isolated
# microVM, so this is safe - no cross-patient state leaks between sessions).
_supervisor = None


def _get_supervisor():
    global _supervisor
    if _supervisor is None:
        _supervisor = build_supervisor()
    return _supervisor


def _build_case_prompt(payload: Dict[str, Any]) -> str:
    """Turn the structured case payload into the instruction text the
    supervisor agent receives. Keeping this as plain string formatting (not
    an LLM call) keeps the hand-off from Lambda to agent fully deterministic
    and auditable."""
    lines = ["Process this patient intake case end to end."]

    if payload.get("card_s3_bucket") and payload.get("card_s3_key"):
        lines.append(
            f"Insurance card photo: s3://{payload['card_s3_bucket']}/{payload['card_s3_key']}"
        )
    if payload.get("voice_s3_bucket") and payload.get("voice_s3_key"):
        fmt = payload.get("voice_media_format", "ogg")
        lines.append(
            f"Symptom voice note: s3://{payload['voice_s3_bucket']}/{payload['voice_s3_key']} "
            f"(format={fmt})"
        )
    if payload.get("cpt_code"):
        lines.append(f"Planned procedure CPT code: {payload['cpt_code']}")
    if payload.get("procedure_name"):
        lines.append(f"Procedure name: {payload['procedure_name']}")
    if payload.get("payer_id"):
        lines.append(f"Known payer_id: {payload['payer_id']}")
    if payload.get("documents_on_file"):
        lines.append(f"Documents already on file: {payload['documents_on_file']}")
    if payload.get("patient_name"):
        lines.append(f"Patient display name: {payload['patient_name']}")
    if payload.get("case_id"):
        lines.append(f"Case ID: {payload['case_id']}")

    lines.append(
        "Return your final structured summary as described in your system prompt."
    )
    return "\n".join(lines)


def _verify_against_rules_engine(
    payload: Dict[str, Any], case_result: Dict[str, Any]
) -> Optional[str]:
    """Independently re-run the deterministic rules engine with the SAME
    inputs the supervisor was given, and reject the agent's structured
    output if its claimed verification fields disagree.

    This is the actual enforcement of "code decides, AI talks" - a system
    prompt instruction alone cannot stop a model from fabricating a
    plausible-looking rule citation if, for example, a tool-call result was
    lost mid-stream (this happened in testing: a Windows console encoding
    crash silently broke a tool response, and the supervisor fabricated a
    rule ID that does not exist anywhere in PayerRulesTable instead of
    surfacing the failure). Returns an error string if verification fails,
    or None if the claimed outcome matches reality.
    """
    verification = case_result.get("verification") or {}
    payer_id = payload.get("payer_id", "PAYER-UNKNOWN")
    cpt_code = payload.get("cpt_code", "")
    documents_on_file = payload.get("documents_on_file", []) or []

    rules = _load_rules_safely()
    expected = rules_engine.evaluate(
        payer_id=payer_id, cpt_code=cpt_code, documents_on_file=documents_on_file, rules=rules,
    )

    if verification.get("outcome") != expected.outcome:
        return (
            f"Supervisor claimed outcome={verification.get('outcome')!r} but the "
            f"deterministic rules engine says outcome={expected.outcome!r} for "
            f"payer_id={payer_id!r} cpt_code={cpt_code!r}."
        )
    if verification.get("matched_rule_id") != expected.matched_rule_id:
        return (
            f"Supervisor claimed matched_rule_id={verification.get('matched_rule_id')!r} "
            f"but the deterministic rules engine says matched_rule_id={expected.matched_rule_id!r} "
            f"- this rule_id does not exist or does not apply to this case."
        )
    return None


@app.entrypoint
def invoke(payload: Dict[str, Any]) -> Dict[str, Any]:
    """AgentCore Runtime entrypoint. `payload` is the JSON body the caller
    (channel_dispatcher Lambda) sends via invoke_agent_runtime.

    Returns the supervisor's structured CaseResult (validated against the
    schema in agent_app/schemas.py AND independently cross-checked against
    the deterministic rules engine - see _verify_against_rules_engine) as a
    plain dict, plus the free-text narration for logging/debugging.
    channel_dispatcher only reads the `case_result` fields - it never
    parses the narration text. If cross-checking fails, `case_result` is
    null and `verification_error` explains why, so the caller can retry or
    escalate rather than act on a fabricated outcome."""
    prompt = payload.get("prompt") or _build_case_prompt(payload)
    supervisor = _get_supervisor()
    result = supervisor(prompt)

    case_result = result.structured_output
    if case_result is None:
        return {"case_result": None, "narration": str(result), "verification_error": "no structured output"}

    case_result_dict = case_result.model_dump()
    verification_error = _verify_against_rules_engine(payload, case_result_dict)
    if verification_error:
        return {
            "case_result": None,
            "narration": str(result),
            "verification_error": verification_error,
        }

    return {
        "case_result": case_result_dict,
        "narration": str(result),
        "verification_error": None,
    }


if __name__ == "__main__":
    app.run()
