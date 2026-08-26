from titan_x.security.mfa import generate_totp_secret, generate_recovery_codes, verify_totp
import pyotp


def test_totp_round_trip():
    secret = generate_totp_secret()
    assert verify_totp(secret, pyotp.TOTP(secret).now())


def test_totp_rejects_invalid_code():
    secret = generate_totp_secret()
    assert not verify_totp(secret, "00000")
    assert not verify_totp(secret, "abcdef")


def test_recovery_codes_are_unique():
    codes = generate_recovery_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
