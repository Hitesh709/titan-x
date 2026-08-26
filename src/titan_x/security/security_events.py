"""Security-event taxonomy used by audit/alerting integrations."""
from __future__ import annotations

from enum import StrEnum


class SecurityEvent(StrEnum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    MFA_CHALLENGE_FAILURE = "mfa_challenge_failure"
    TOKEN_REUSE = "token_reuse"
    TOKEN_REVOKED = "token_revoked"
    AUTHZ_DENIED = "authorization_denied"
    RATE_LIMITED = "rate_limited"
    SUSPICIOUS_REQUEST = "suspicious_request"
    TRADING_DENIED = "trading_denied"
    PASSWORD_RESET = "password_reset"
    ADMIN_ACTION = "admin_action"
