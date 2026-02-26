# utils/email_verification.py

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    """Token generator for email verification (distinct from password reset)."""

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{timestamp}{user.email_verified}"


email_verification_token = EmailVerificationTokenGenerator()


def build_email_verification_payload(user) -> dict[str, str]:
    """Return uid/token payload expected by /users/auth/verify-email/."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return {"uid": uid, "token": token}
