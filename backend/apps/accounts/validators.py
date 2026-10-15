import re

from django.core.exceptions import ValidationError

PASSWORD_RULES = [
    (r"[A-Z]", "an uppercase letter"),
    (r"[a-z]", "a lowercase letter"),
    (r"[0-9]", "a number"),
    (r"[^A-Za-z0-9]", "a special character"),
]


class ComplexityValidator:
    """REQ-AUTH-004: ≥8 chars (MinimumLengthValidator) + upper, lower, digit, special."""

    def validate(self, password, user=None):
        missing = [label for pattern, label in PASSWORD_RULES if not re.search(pattern, password or "")]
        if missing:
            raise ValidationError("Password must contain " + ", ".join(missing) + ".", code="password_complexity")

    def get_help_text(self):
        return "At least 8 characters with uppercase, lowercase, a number and a special character."
