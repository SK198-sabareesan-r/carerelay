"""Patient -> hospital association, stored in PatientsTable.

This is the backbone of CareRelay's case-level multi-tenancy (Option A): a
patient's WhatsApp number carries no hospital information on its own, so we
record which hospital "owns" a patient the moment that hospital's staff
first interacts with them (creating an appointment / sending a reminder
from their logged-in console session). Later, when a patient messages the
shared WhatsApp number, channel_dispatcher looks the patient up here to tag
the resulting case with the correct hospital_id / hospital_name - so the
payer letter, audit email, and dashboard all reflect the real owning
hospital instead of a hardcoded CLINIC_NAME.

PatientsTable item shape (partition key patient_id = the bare-digit phone):
    {
      "patient_id": "919500799295",
      "hospital_id": "metroorthopedics",
      "hospital_name": "Metro Orthopedics & Imaging Center",
      "patient_name": "Sarah Jenkins",      # best-known display name
      "updated_at": "2026-...Z",
    }

If a patient has never been associated with a hospital (e.g. they message
the number cold, before any appointment was logged), lookups return None
and callers fall back to a neutral default - documented at each call site.
"""
import time
from typing import Any, Dict, Optional

from . import aws_clients, config
from .logging_utils import get_logger, log_event

logger = get_logger("patient_directory")


def _table():
    return aws_clients.dynamodb_resource().Table(config.PATIENTS_TABLE)


def associate_patient(
    patient_phone: str,
    hospital_id: str,
    hospital_name: str,
    patient_name: Optional[str] = None,
) -> None:
    """Record (or refresh) which hospital a patient belongs to. Called when
    a hospital's staff creates an appointment / sends a reminder. Last write
    wins - if a patient legitimately moves between hospitals, the most
    recent association is the one future cases inherit."""
    if not patient_phone or not hospital_id:
        return
    item = {
        "patient_id": patient_phone,
        "hospital_id": hospital_id,
        "hospital_name": hospital_name,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if patient_name:
        item["patient_name"] = patient_name
    try:
        _table().put_item(Item=item)
        log_event(logger, "info", "patient.associated", patient_id=patient_phone, hospital_id=hospital_id)
    except Exception as exc:  # noqa: BLE001 - association is best-effort, never block the caller
        log_event(logger, "warning", "patient.associate.failed", error=str(exc))


def lookup_patient(patient_phone: str) -> Optional[Dict[str, Any]]:
    """Return the patient's hospital association, or None if the patient has
    never been associated with a hospital."""
    if not patient_phone:
        return None
    try:
        resp = _table().get_item(Key={"patient_id": patient_phone})
        return resp.get("Item")
    except Exception as exc:  # noqa: BLE001
        log_event(logger, "warning", "patient.lookup.failed", error=str(exc))
        return None
