import json
from urllib.parse import parse_qs
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from titan_x.api.dependencies import get_qr_auth_service
from titan_x.api.schemas import QRChallengeRequest, QRCreateResponse, QRLoginRequest, QRRegistrationCreateResponse, QRRegistrationEmailOTPRequest, QRRegistrationRequest, QRStatusResponse, RegisterResponse
from titan_x.core.audit import audit_event_later
from titan_x.core.config import Settings, get_settings
from titan_x.infrastructure.rate_limiter import RateLimiter
from titan_x.services.qr_auth_service import QRAuthService

router = APIRouter(tags=["qr-auth"])


def _rate_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _check_rate(request: Request, settings: Settings, suffix: str, limit: int) -> None:
    if not settings.rate_limit_enabled:
        return
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    allowed, _, _ = await RateLimiter(redis).check(f"qr:{suffix}:{_rate_key(request)}", limit, 60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many QR authentication requests")


async def _set_browser_cookie(response: Response, request: Request, browser_session: str, settings: Settings) -> None:
    response.set_cookie(QRAuthService.BROWSER_COOKIE, browser_session, max_age=QRAuthService.CHALLENGE_TTL_SECONDS + 30, httponly=True, secure=request.url.scheme == "https" or settings.environment == "production", samesite="lax", path="/api/v1/auth/qr")


@router.post("/auth/qr/create", response_model=QRCreateResponse)
async def create_qr(body: QRLoginRequest, request: Request, response: Response, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRCreateResponse:
    await _check_rate(request, settings, "create", 10)
    browser_session = service.create_browser_session()
    try:
        challenge, raw = await service.create_login_challenge(body.identifier, browser_session, request.client.host if request.client else None, request.headers.get("User-Agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _set_browser_cookie(response, request, browser_session, settings)
    audit_event_later(request, action="LOGIN_QR_CREATED", entity_type="auth_challenge", category="security", severity="info")
    return QRCreateResponse(challenge_id=challenge.challenge_id, qr_data_url=service._qr(raw, "LOGIN"), expires_at=challenge.expires_at, expires_in_seconds=service.CHALLENGE_TTL_SECONDS, sms_number=settings.qr_sms_number)


@router.post("/auth/qr/register/create", response_model=QRRegistrationCreateResponse)
async def create_registration_qr(body: QRRegistrationRequest, request: Request, response: Response, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRRegistrationCreateResponse:
    await _check_rate(request, settings, "register", 5)
    browser_session = service.create_browser_session()
    try:
        challenge, raw = await service.create_registration_challenge(body.username, body.password, body.confirm_password, body.email, body.phone, browser_session, request.client.host if request.client else None, request.headers.get("User-Agent"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _set_browser_cookie(response, request, browser_session, settings)
    audit_event_later(request, action="LOGIN_QR_CREATED", entity_type="registration_challenge", category="security", severity="info")
    return QRRegistrationCreateResponse(challenge_id=challenge.challenge_id, qr_data_url=service._qr(raw, "REGISTRATION"), expires_at=challenge.expires_at, expires_in_seconds=service.CHALLENGE_TTL_SECONDS, sms_number=None)


@router.post("/auth/qr/register/scan", response_model=dict)
async def scan_registration_qr(body: QRChallengeRequest, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)], settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    """Handle a QR scan for registration. No inbound SMS is required in the temporary flow."""
    await _check_rate(request, settings, "register-scan", 20)
    try:
        challenge = await service.scan_registration_qr(body.challenge_id)
    except ValueError as exc:
        audit_event_later(request, action="LOGIN_QR_FAILED", entity_type="registration_challenge", category="security", severity="warning")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_SCANNED", entity_type="registration_challenge", category="security", severity="info")
    return {"status": challenge.status, "email_otp_required": True, "message": "QR scanned. Email verification code sent."}


async def _read_sms_webhook(request: Request) -> tuple[str, str]:
    content_type = (request.headers.get("content-type") or "").lower()
    raw = await request.body()
    data: dict[str, object] = {}
    if "application/json" in content_type:
        try:
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                data = parsed
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail="Invalid SMS webhook JSON")
    else:
        parsed = parse_qs(raw.decode("utf-8", errors="replace"), keep_blank_values=True)
        data = {key: values[-1] for key, values in parsed.items() if values}
    from_number = data.get("from_number") or data.get("From") or data.get("from")
    message = data.get("body") or data.get("Body") or data.get("message")
    if not isinstance(from_number, str) or not isinstance(message, str) or not from_number.strip() or not message.strip():
        raise HTTPException(status_code=400, detail="SMS webhook must include sender and message body")
    return from_number.strip(), message.strip()


@router.post("/auth/qr/sms/webhook", response_model=dict)
async def sms_webhook(request: Request, settings: Annotated[Settings, Depends(get_settings)], service: Annotated[QRAuthService, Depends(get_qr_auth_service)], x_qr_sms_signature: str | None = Header(default=None)) -> dict:
    await _check_rate(request, settings, "sms-webhook", 60)
    from_number, message = await _read_sms_webhook(request)
    if not service.verify_webhook(from_number, message, x_qr_sms_signature):
        raise HTTPException(status_code=401, detail="Invalid SMS webhook signature")
    if not message.startswith(QRAuthService.SMS_PREFIX):
        raise HTTPException(status_code=400, detail="Unsupported SMS verification message")
    raw = message[len(QRAuthService.SMS_PREFIX):].strip()
    try:
        challenge = await service.sms_approve(raw, from_number)
    except ValueError as exc:
        audit_event_later(request, action="LOGIN_QR_FAILED", entity_type="auth_challenge", category="security", severity="warning")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="LOGIN_QR_APPROVED", entity_type="auth_challenge", category="security", severity="info", user_id=challenge.customer_id)
    return {"status": "approved", "email_otp_required": bool(challenge.operation == "REGISTRATION" and challenge.registration_email)}


@router.post("/auth/qr/register/email-otp/verify", response_model=dict)
async def verify_registration_email_otp(body: QRRegistrationEmailOTPRequest, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)], settings: Annotated[Settings, Depends(get_settings)]) -> dict:
    await _check_rate(request, settings, "email-otp", 10)
    try:
        await service.verify_registration_email_otp(body.challenge_id, body.otp)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_event_later(request, action="EMAIL_OTP_VERIFIED", entity_type="registration_challenge", category="security", severity="info")
    return {"status": "verified"}


@router.get("/auth/qr/status/{challenge_id}", response_model=QRStatusResponse)
async def qr_status(challenge_id: str, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> QRStatusResponse:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        state, user, tokens = await service.status_and_consume(challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if tokens and user:
        access, refresh = tokens
        return QRStatusResponse(status="USED", access_token=access, refresh_token=refresh, user=RegisterResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active, is_verified=user.is_verified))
    return QRStatusResponse(status=state)


@router.post("/auth/qr/cancel")
async def cancel_qr(body: QRChallengeRequest, request: Request, service: Annotated[QRAuthService, Depends(get_qr_auth_service)]) -> dict:
    browser_session = request.cookies.get(QRAuthService.BROWSER_COOKIE)
    if not browser_session:
        raise HTTPException(status_code=401, detail="QR browser session missing")
    try:
        await service.cancel(body.challenge_id, browser_session)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "QR authentication cancelled"}
