"""Field validators used by the form workflow.

Each validator returns ``(ok, cleaned_value, error_message)``. An ``ok``
of ``True`` means the value passed and the cleaned form is what should
be stored. Validators are deliberately permissive about whitespace and
formatting so the assistant can be friendly about user input.
"""

from __future__ import annotations

import datetime as _dt
import re

ValidationResult = tuple[bool, str, str]


# helpers
def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


# atomic validators
def email(value: str) -> ValidationResult:
    value = (value or "").strip()
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return True, value.lower(), ""
    return False, value, "That doesn't look like a valid email address."


def phone_us(value: str) -> ValidationResult:
    digits = _digits_only(value or "")
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return False, value, "Please enter a 10-digit U.S. phone number."
    formatted = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return True, formatted, ""


def zip_us(value: str) -> ValidationResult:
    value = (value or "").strip()
    if re.fullmatch(r"\d{5}(-\d{4})?", value):
        return True, value, ""
    return False, value, "Please enter a 5-digit ZIP (or ZIP+4)."


def address(value: str) -> ValidationResult:
    value = (value or "").strip()
    # Very lightweight check: must start with a number and contain at least
    # one alphabetical token (street name)
    if re.match(r"^\d+\s+\S+", value) and re.search(r"[A-Za-z]", value):
        return True, value, ""
    return (
        False,
        value,
        (
            "Please enter a street address that begins with a house number, "
            "for example '123 Main St'."
        ),
    )


def ssn_or_dl(value: str) -> ValidationResult:
    """Accept a U.S. SSN (9 digits) or a state driver license (5-13 alphanumeric)."""
    value = (value or "").strip()
    if not value:
        return False, value, "This field is required."
    digits = _digits_only(value)
    if len(digits) == 9:
        return True, f"***-**-{digits[-4:]}", ""  # store masked form
    if 5 <= len(value) <= 13 and re.fullmatch(r"[A-Za-z0-9-]+", value):
        last4 = re.sub(r"[^A-Za-z0-9]", "", value)[-4:]
        return True, f"DL ending {last4}", ""
    return False, value, "Enter a 9-digit SSN or a state driver license number."


def ssn_last4(value: str) -> ValidationResult:
    digits = _digits_only(value or "")
    if len(digits) == 4:
        return True, digits, ""
    return False, value, "Enter the last 4 digits of your Social Security Number."


def cps_account(value: str) -> ValidationResult:
    """CPS Energy account numbers are typically 10-14 digits."""
    if not value:
        return True, "", ""  # optional field
    digits = _digits_only(value)
    if 9 <= len(digits) <= 16:
        return True, digits, ""
    return False, value, "CPS Energy account numbers are usually 10-14 digits."


# date validators
def _parse_date(value: str) -> _dt.date | None:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y"):
        try:
            return _dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def date_field(value: str) -> ValidationResult:
    d = _parse_date(value)
    if d is None:
        return False, value, "Please enter a date as YYYY-MM-DD or MM/DD/YYYY."
    return True, d.isoformat(), ""


def date_of_birth(value: str) -> ValidationResult:
    """Accept a date of birth as YYYY-MM-DD, MM/DD/YYYY, or a bare age (integer).

    A bare integer like '25' is treated as 'approximately 25 years old' and
    converted to an estimated birthdate (today minus that many years). The
    converted value is stored as an ISO date string for the form record.
    """
    value = (value or "").strip()
    if not value:
        return False, value, "Please enter your date of birth."
    # Accept bare integer as an age
    if value.isdigit():
        age = int(value)
        if age < 1 or age > 120:
            return (
                False,
                value,
                "Please enter a valid age (1–120) or a date as YYYY-MM-DD or MM/DD/YYYY.",
            )
        estimated = _dt.date.today().replace(year=_dt.date.today().year - age)
        return True, estimated.isoformat(), ""
    # Accept standard date formats
    d = _parse_date(value)
    if d is None:
        return (
            False,
            value,
            "Please enter your date of birth as YYYY-MM-DD, MM/DD/YYYY, or just your age.",
        )
    # Sanity check: must be in the past and not more than 120 years ago
    today = _dt.date.today()
    if d >= today:
        return False, value, "Date of birth must be in the past."
    if (today - d).days > 120 * 365:
        return False, value, "Please enter a valid date of birth."
    return True, d.isoformat(), ""


def _add_business_days(start: _dt.date, n: int) -> _dt.date:
    """Add ``n`` business days (skipping Sat/Sun) to ``start``."""
    d = start
    added = 0
    while added < n:
        d += _dt.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return d


def lead_time(value: str, days: int) -> ValidationResult:
    """Ensure a date is at least ``days`` business days from today and on a weekday."""
    ok, cleaned, err = date_field(value)
    if not ok:
        return ok, cleaned, err
    target = _dt.date.fromisoformat(cleaned)
    today = _dt.date.today()
    earliest = _add_business_days(today, days)
    if target.weekday() >= 5:
        return False, cleaned, "That date falls on a weekend; service cannot start then."
    if target < earliest:
        return (
            False,
            cleaned,
            f"Pick a date on or after {earliest.isoformat()} (at least {days} business days out).",
        )
    return True, cleaned, ""


def lead_time_2bd(value: str) -> ValidationResult:
    return lead_time(value, 2)


def lead_time_5bd(value: str) -> ValidationResult:
    return lead_time(value, 5)


# registry
VALIDATORS = {
    "email": email,
    "phone_us": phone_us,
    "zip_us": zip_us,
    "address": address,
    "ssn_or_dl": ssn_or_dl,
    "ssn_last4": ssn_last4,
    "cps_account": cps_account,
    "lead_time_2bd": lead_time_2bd,
    "lead_time_5bd": lead_time_5bd,
    "date": date_field,
    "date_of_birth": date_of_birth,
}


def validate(name: str, value: str) -> ValidationResult:
    """Look up a validator by name and apply it. Unknown names pass through."""
    fn = VALIDATORS.get(name)
    if fn is None:
        return True, (value or "").strip(), ""
    return fn(value)
