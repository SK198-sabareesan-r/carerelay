"""CareRelay's Strands agents.

Three specialists, one supervisor:

    intake_agent         - extracts structured facts (Bedrock vision model
                            for the card photo, Transcribe for the voice note).
    verification_agent   - calls the deterministic rules engine + simulated
                            payer IVR; NEVER decides anything itself.
    notification_agent   - drafts patient/doctor/audit messages.
    supervisor           - orchestrates the three above via the
                            "agents as tools" pattern and returns one
                            structured case result.
"""
