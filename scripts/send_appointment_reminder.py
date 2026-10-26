#!/usr/bin/env python3
"""Create (or reuse) an appointment record and send the 24h-prior onboarding
reminder (quick-reply buttons: Start Verification / Reschedule) to the
patient over WhatsApp.

This is the STAFF-TRIGGERED manual path - see
channels.build_whatsapp_appointment_reminder for why this uses the
free-form interactive message builder rather than a Meta-approved Template
Message (required for the eventual fully-automated 24h-prior scheduler,
not yet built - this script is for testing/demo purposes where the
customer service window is open or Meta template approval isn't needed).

Usage:
    python scripts/send_appointment_reminder.py --phone 919500799295 \\
        --name "R. Sharma" --procedure "Knee arthroscopy" \\
        --when "tomorrow at 10 AM"
"""
import argparse
import os
import re
import sys
import time
import uuid

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, os.path.join(_REPO_ROOT, "lambdas"))


def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            match = re.match(r"^\s*([^#=\s]+)\s*=\s*(.*?)\s*$", line)
            if not match:
                continue
            key, value = match.group(1), match.group(2)
            os.environ.setdefault(key, value)


_load_dotenv(os.path.join(_REPO_ROOT, ".env"))

from common import aws_clients, config, channels, patient_directory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone", required=True, help="Patient's phone number (bare digits, e.g. 919500799295).")
    parser.add_argument("--name", required=True, help="Patient display name.")
    parser.add_argument("--procedure", required=True, help="Procedure/visit name.")
    parser.add_argument("--when", required=True, help="Human-readable appointment time, e.g. 'tomorrow at 10 AM'.")
    parser.add_argument("--hospital-id", required=True, help="Owning hospital's ID (e.g. metroorthopedicsimagingcenter).")
    parser.add_argument("--hospital-name", required=True, help="Owning hospital's display name.")
    args = parser.parse_args()

    if not config.WHATSAPP_PHONE_NUMBER_ID:
        print("ERROR: WHATSAPP_PHONE_NUMBER_ID is not set in .env.", file=sys.stderr)
        sys.exit(1)

    table = aws_clients.dynamodb_resource().Table(config.APPOINTMENTS_TABLE)
    appointment_id = f"appt-{uuid.uuid4().hex[:8]}"
    table.put_item(Item={
        "appointment_id": appointment_id,
        "patient_phone": args.phone,
        "phone_number_id": config.WHATSAPP_PHONE_NUMBER_ID,
        "patient_name": args.name,
        "procedure_name": args.procedure,
        "appointment_time_display": args.when,
        "hospital_id": args.hospital_id,
        "hospital_name": args.hospital_name,
        "reminder_sent": True,
        "status": "SCHEDULED",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    print(f"[dynamodb] Created appointment {appointment_id} for {args.name}.")

    # Associate this patient with the hospital so a case created later from
    # their WhatsApp intake inherits the correct hospital (Option A - see
    # common/patient_directory.py).
    patient_directory.associate_patient(
        patient_phone=args.phone,
        hospital_id=args.hospital_id,
        hospital_name=args.hospital_name,
        patient_name=args.name,
    )
    print(f"[dynamodb] Associated patient {args.phone} with hospital '{args.hospital_name}'.")

    msg = channels.build_whatsapp_appointment_reminder(to=args.phone, appointment_time_display=args.when)
    message_id = channels.send_whatsapp(msg, config.WHATSAPP_PHONE_NUMBER_ID)
    print(f"[whatsapp] Reminder sent. Meta message id: {message_id}")


if __name__ == "__main__":
    main()
