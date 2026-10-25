"""Document extraction tools: the Bedrock vision model (insurance card)
and Amazon Transcribe (symptom voice note).

These tools only EXTRACT structured data. They never decide coverage - the
Intake Agent calls them to populate fields, which are then handed to the
Verification Agent's `check_prior_auth` tool (backed by rules_engine.py).

NOTE ON THE VISION SWAP: card extraction used to run on Amazon Textract
(deterministic OCR + label matching, no LLM). It now runs on the Bedrock
vision model (BEDROCK_VISION_MODEL_ID, e.g. Claude Sonnet 4.6) via Bedrock
Converse with a forced-JSON tool call. This trades Textract's per-field OCR confidence
score for a vision-LLM read, so `extract_insurance_card`'s `confidence`
field is now a coarse self-reported signal (100/60/0 based on `legible` and
`uncertain_fields`), not a true OCR confidence score. The downstream
contract (field names, types, nullability) is unchanged, so nothing else in
the agent/rules pipeline needed to change - see schemas.CardVisionExtraction
for the strict output contract enforced on the model.
"""
import json
import time
from typing import Any, Dict

from strands import tool

from lambdas.common import aws_clients, config
from lambdas.common.logging_utils import get_logger, log_event

from ..schemas import CardVisionExtraction

logger = get_logger("agent_tools.documents")

_CARD_EXTRACTION_SYSTEM_PROMPT = """You read photographed health insurance \
cards for a clinic intake system. Extract ONLY what is printed on the card \
image - never guess, infer, or fill in a plausible-looking value for a \
field you cannot actually read.

For each field, return the exact text as printed, or null if that field is \
not visible on the card. Set legible=false if the photo is too blurry, \
dark, glare-affected, or cropped to read reliably - in that case most \
fields should be null. List in uncertain_fields any field name where you \
are not confident in the value you returned (e.g. partially obscured text) \
even though you still returned a best-guess value for it.

Call the submit_card_extraction tool exactly once with your result."""

_CARD_EXTRACTION_TOOL = {
    "toolSpec": {
        "name": "submit_card_extraction",
        "description": "Submit the fields read from the insurance card photo.",
        "inputSchema": {"json": CardVisionExtraction.model_json_schema()},
    }
}


@tool
def extract_insurance_card(s3_bucket: str, s3_key: str) -> Dict[str, Any]:
    """Extract structured fields from a photographed insurance card using the Bedrock vision model.

    Downloads the card image from S3 and sends it to the Bedrock vision
    model (BEDROCK_VISION_MODEL_ID) with a forced structured-output tool
    call, so the response is validated JSON rather than parsed prose. The
    model is instructed to return null for anything it cannot actually read
    on the card rather than guessing.

    Args:
        s3_bucket: S3 bucket holding the card photo.
        s3_key: S3 object key of the card photo (jpeg/png/gif/webp).

    Returns:
        A dict with keys: payer_name, member_id, group_number, payer_id
        (each a string or None), legible (bool), uncertain_fields (list of
        field names the model flagged as low-confidence), and confidence
        (a coarse 0-100 signal derived from legible/uncertain_fields - see
        module docstring; this is a self-reported LLM signal, not a true
        OCR confidence score).
    """
    image_bytes = aws_clients.s3().get_object(Bucket=s3_bucket, Key=s3_key)["Body"].read()
    image_format = _image_format(s3_key)

    client = aws_clients.bedrock_runtime()
    resp = client.converse(
        modelId=config.BEDROCK_VISION_MODEL_ID,
        system=[{"text": _CARD_EXTRACTION_SYSTEM_PROMPT}],
        messages=[
            {
                "role": "user",
                "content": [
                    {"text": "Extract the fields from this insurance card photo."},
                    {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
                ],
            }
        ],
        toolConfig={
            "tools": [_CARD_EXTRACTION_TOOL],
            "toolChoice": {"tool": {"name": "submit_card_extraction"}},
        },
        inferenceConfig={"maxTokens": 512, "temperature": 0.0},
    )

    extraction = _parse_tool_response(resp)
    if extraction is None:
        log_event(logger, "warning", "card_vision.no_tool_use", s3_key=s3_key)
        return {
            "payer_name": None, "member_id": None, "group_number": None, "payer_id": None,
            "legible": False, "uncertain_fields": [], "confidence": 0.0,
        }

    fields_found = sum(
        1 for f in ("payer_name", "member_id", "group_number", "payer_id") if extraction.get(f)
    )
    log_event(
        logger, "info", "card_vision.extract.done", s3_key=s3_key,
        legible=extraction.get("legible"), fields_found=fields_found,
    )

    confidence = _confidence_score(extraction)
    return {
        "payer_name": extraction.get("payer_name"),
        "member_id": extraction.get("member_id"),
        "group_number": extraction.get("group_number"),
        "payer_id": extraction.get("payer_id"),
        "legible": extraction.get("legible", False),
        "uncertain_fields": extraction.get("uncertain_fields", []),
        "confidence": confidence,
    }


def _parse_tool_response(converse_response: Dict[str, Any]):
    """Extract + validate the submit_card_extraction tool-use input against
    CardVisionExtraction. Returns a plain dict, or None if the model didn't
    call the tool or returned a schema-invalid payload."""
    content = converse_response.get("output", {}).get("message", {}).get("content", [])
    for block in content:
        tool_use = block.get("toolUse")
        if tool_use and tool_use.get("name") == "submit_card_extraction":
            try:
                validated = CardVisionExtraction.model_validate(tool_use.get("input", {}))
            except Exception as exc:  # noqa: BLE001 - treat schema violation as no extraction
                log_event(get_logger("agent_tools.documents"), "warning",
                          "card_vision.schema_invalid", error=str(exc))
                return None
            return validated.model_dump()
    return None


def _confidence_score(extraction: Dict[str, Any]) -> float:
    """Coarse self-reported confidence: 0 if illegible, otherwise 100 minus
    a penalty per field the model itself flagged as uncertain. This is
    deliberately simple - it is NOT a calibrated OCR confidence score, just
    a signal for the dashboard to visually flag shakier reads."""
    if not extraction.get("legible", False):
        return 0.0
    uncertain = len(extraction.get("uncertain_fields", []))
    return max(0.0, 100.0 - uncertain * 20.0)


def _image_format(key: str) -> str:
    k = key.lower()
    if k.endswith(".png"):
        return "png"
    if k.endswith(".webp"):
        return "webp"
    if k.endswith(".gif"):
        return "gif"
    return "jpeg"


@tool
def transcribe_voice_note(s3_bucket: str, s3_key: str, media_format: str = "ogg") -> Dict[str, Any]:
    """Transcribe a patient's symptom voice note using Amazon Transcribe.

    Starts a transcription job, polls for completion (bounded to ~2 minutes),
    and returns the plain transcript text. This tool only transcribes speech
    to text; summarizing or acting on the symptoms described is the Intake
    Agent's job, not this tool's.

    Args:
        s3_bucket: S3 bucket holding the voice note.
        s3_key: S3 object key of the voice note audio file.
        media_format: audio codec/container (e.g. "ogg", "mp3", "mp4", "wav", "amr").

    Returns:
        A dict with keys: transcript (string, empty if transcription failed
        or timed out) and status ("COMPLETED", "FAILED", or "TIMEOUT").
    """
    media_uri = f"s3://{s3_bucket}/{s3_key}"
    job_name = f"carerelay-{int(time.time() * 1000)}-{abs(hash(s3_key)) % 100000}"
    client = aws_clients.transcribe()
    client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        MediaFormat=media_format,
        IdentifyLanguage=True,
    )
    for _ in range(40):  # ~2 minutes max
        job = client.get_transcription_job(TranscriptionJobName=job_name)
        status = job["TranscriptionJob"]["TranscriptionJobStatus"]
        if status == "COMPLETED":
            uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
            transcript = _download_transcript(uri)
            log_event(logger, "info", "transcribe.done", job=job_name)
            return {"transcript": transcript or "", "status": "COMPLETED"}
        if status == "FAILED":
            log_event(logger, "warning", "transcribe.failed", job=job_name)
            return {"transcript": "", "status": "FAILED"}
        time.sleep(3)
    log_event(logger, "warning", "transcribe.timeout", job=job_name)
    return {"transcript": "", "status": "TIMEOUT"}


def _download_transcript(uri: str) -> str:
    import json
    import urllib.request

    with urllib.request.urlopen(uri, timeout=15) as resp:  # noqa: S310
        data = json.loads(resp.read().decode("utf-8"))
    return data["results"]["transcripts"][0]["transcript"]
