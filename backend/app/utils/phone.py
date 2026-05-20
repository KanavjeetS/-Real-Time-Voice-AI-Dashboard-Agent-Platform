"""E.164 phone normalization for Twilio outbound calls."""
import re

# Indian mobile: 10 digits, starts 6–9
_IN_MOBILE = re.compile(r"^[6-9]\d{9}$")


def normalize_phone_e164(raw: str, default_region: str = "IN") -> str:
    """
    Normalize user input to E.164.

    Examples (default_region=IN):
      8076029575     -> +918076029575
      918076029575   -> +918076029575
      +918076029575  -> +918076029575
      08076029575    -> +918076029575
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("Phone number is required")

    if s.startswith("+"):
        digits = re.sub(r"\D", "", s)
        if len(digits) < 10:
            raise ValueError("Invalid phone number")
        # Strict validation for common regions to catch typo-length numbers early.
        if digits.startswith("91"):
            if len(digits) != 12 or not _IN_MOBILE.match(digits[2:]):
                raise ValueError("Invalid India number. Use +91 followed by a valid 10-digit mobile number")
        if digits.startswith("1"):
            if len(digits) != 11:
                raise ValueError("Invalid US number. Use +1 followed by a valid 10-digit number")
        return f"+{digits}"

    digits = re.sub(r"\D", "", s)

    if default_region.upper() == "IN":
        if len(digits) == 10 and _IN_MOBILE.match(digits):
            return f"+91{digits}"
        if len(digits) == 12 and digits.startswith("91") and _IN_MOBILE.match(digits[2:]):
            return f"+{digits}"
        if len(digits) == 11 and digits.startswith("0") and _IN_MOBILE.match(digits[1:]):
            return f"+91{digits[1:]}"

    if default_region.upper() == "US":
        if len(digits) == 10:
            return f"+1{digits}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+{digits}"

    # Fallback: require explicit +country code
    raise ValueError(
        "Use E.164 format with country code, e.g. +918076029575 for India or +14155551234 for US"
    )


def format_twilio_error(exc: Exception) -> str:
    """User-friendly Twilio API errors."""
    msg = str(exc)
    lower = msg.lower()
    if "unverified" in lower or "21219" in msg:
        return (
            "Twilio trial account: this number is not verified. "
            "Add and verify it at https://console.twilio.com/us1/develop/phone-numbers/manage/verified "
            "or upgrade your Twilio account."
        )
    if "21211" in msg or "invalid" in lower and "phone" in lower:
        return "Invalid phone number. Use E.164 format, e.g. +918076029575 for India."
    if "21608" in msg or "unverified caller id" in lower:
        return "Twilio: the From number is not verified for your account."
    return msg
