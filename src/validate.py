"""
Validation for a single field submission record.

validate_record() never raises; it returns {"valid": bool, "errors": [str, ...]}
so callers can handle invalid records as data rather than exceptions.
"""

import re
from datetime import datetime

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

PDP_STATUSES = ["Active", "Expiring", "Missing"]


def validate_record(record):
    """
    Validate one record against the PDP submission schema.

    Business rule: expiry_year is required when pdp_status is "Active" or
    "Expiring", and must be null when pdp_status is "Missing" (a plan with
    unknown status has no expiry date to report).
    """
    errors = []

    if not isinstance(record, dict):
        return {"valid": False, "errors": ["record must be an object/dict"]}

    uuid_value = record.get("submission_uuid")
    if not isinstance(uuid_value, str) or not UUID_PATTERN.match(uuid_value):
        errors.append("submission_uuid must be a valid UUID")

    council = record.get("urban_council")
    if not isinstance(council, str) or council.strip() == "":
        errors.append("urban_council is required")

    status = record.get("pdp_status")
    if status not in PDP_STATUSES:
        errors.append(f"pdp_status must be one of: {', '.join(PDP_STATUSES)}")
    else:
        expiry_year = record.get("expiry_year")
        if status == "Missing":
            if expiry_year is not None:
                errors.append('expiry_year must be null when pdp_status is "Missing"')
        else:
            is_whole_number = isinstance(expiry_year, int) and not isinstance(expiry_year, bool)
            if not is_whole_number or expiry_year < 2000 or expiry_year > 2100:
                errors.append(
                    'expiry_year must be a whole number between 2000 and 2100 '
                    'when pdp_status is "Active" or "Expiring"'
                )

    timestamp = record.get("field_officer_timestamp")
    if not isinstance(timestamp, str) or not _is_valid_timestamp(timestamp):
        errors.append("field_officer_timestamp must be an ISO-8601 timestamp")

    return {"valid": len(errors) == 0, "errors": errors}


def _is_valid_timestamp(text):
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return True
    except (ValueError, AttributeError):
        return False
