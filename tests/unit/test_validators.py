"""Unit tests for src/forms/validators.py."""

from __future__ import annotations

from src.forms.validators import address, email, phone_us, ssn_last4, ssn_or_dl, validate, zip_us


class TestEmail:
    def test_valid_email(self):
        ok, cleaned, err = email("Alex@Example.COM")
        assert ok is True
        assert cleaned == "alex@example.com"
        assert err == ""

    def test_invalid_no_at(self):
        ok, cleaned, err = email("notanemail")
        assert ok is False
        assert "valid email" in err.lower()

    def test_invalid_no_domain(self):
        ok, cleaned, err = email("user@")
        assert ok is False

    def test_empty(self):
        ok, _, _ = email("")
        assert ok is False


class TestPhoneUs:
    def test_10_digit(self):
        ok, cleaned, err = phone_us("2105551234")
        assert ok is True
        assert cleaned == "(210) 555-1234"

    def test_formatted_input(self):
        ok, cleaned, err = phone_us("(210) 555-1234")
        assert ok is True
        assert cleaned == "(210) 555-1234"

    def test_11_digit_with_country_code(self):
        ok, cleaned, err = phone_us("12105551234")
        assert ok is True
        assert cleaned == "(210) 555-1234"

    def test_too_short(self):
        ok, _, _ = phone_us("12345")
        assert ok is False


class TestZipUs:
    def test_5_digit(self):
        ok, cleaned, err = zip_us("78205")
        assert ok is True
        assert cleaned == "78205"

    def test_zip_plus_4(self):
        ok, cleaned, err = zip_us("78205-1234")
        assert ok is True

    def test_invalid(self):
        ok, _, _ = zip_us("1234")
        assert ok is False


class TestAddress:
    def test_valid_address(self):
        ok, cleaned, err = address("123 Main St")
        assert ok is True

    def test_no_number(self):
        ok, _, _ = address("Main St")
        assert ok is False

    def test_empty(self):
        ok, _, _ = address("")
        assert ok is False


class TestSsnOrDl:
    def test_9_digit_ssn(self):
        ok, cleaned, err = ssn_or_dl("123456789")
        assert ok is True
        assert "***" in cleaned  # masked

    def test_formatted_ssn(self):
        ok, cleaned, err = ssn_or_dl("123-45-6789")
        assert ok is True

    def test_driver_license(self):
        ok, cleaned, err = ssn_or_dl("TX12345678")
        assert ok is True
        assert "DL ending" in cleaned

    def test_empty(self):
        ok, _, _ = ssn_or_dl("")
        assert ok is False

    def test_too_short(self):
        ok, _, _ = ssn_or_dl("123")
        assert ok is False


class TestSsnLast4:
    def test_valid_4_digits(self):
        ok, cleaned, err = ssn_last4("6789")
        assert ok is True
        assert cleaned == "6789"

    def test_too_short(self):
        ok, _, _ = ssn_last4("123")
        assert ok is False

    def test_non_digits(self):
        ok, _, _ = ssn_last4("abcd")
        assert ok is False


class TestValidateDispatch:
    def test_unknown_name_passes_through(self):
        ok, cleaned, err = validate("nonexistent_validator", "any value")
        assert ok is True
        assert cleaned == "any value"

    def test_dispatches_email(self):
        ok, _, _ = validate("email", "bad")
        assert ok is False

    def test_dispatches_phone(self):
        ok, _, _ = validate("phone_us", "123")
        assert ok is False
