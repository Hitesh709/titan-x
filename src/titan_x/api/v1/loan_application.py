from __future__ import annotations

import json
import re
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from titan_x.models.loan_application import LoanApplication
from titan_x.services.loan_analyzers import (
    analyze_bank_statement,
    analyze_bureau,
    analyze_gst,
    analyze_invoice,
    cross_document_match,
)

router = APIRouter(prefix="/loan", tags=["Loan Application"])

STAGES = [
    "MOBILE_VERIFICATION", "PAN_VERIFICATION", "AADHAAR_KYC", "PROFILE_COMPLETION",
    "DOCUMENT_COLLECTION", "BANK_ANALYSIS", "BUREAU_ANALYSIS", "GST_ANALYSIS",
    "GST_BILL_ANALYSIS", "CROSS_DOCUMENT_VERIFICATION", "BANK_VERIFICATION",
    "CREDIT_ASSESSMENT", "CREDIT_DECISION", "LOAN_OFFER", "OFFER_ACCEPTED",
    "E_MANDATE", "E_SIGN", "FINAL_APPROVAL", "DISBURSEMENT", "LOAN_ACTIVE",
]


class ApplicationCreate(BaseModel):
    mobile: str = Field(min_length=10, max_length=15)
    user_id: int | None = None


class PanVerification(BaseModel):
    pan: str = Field(min_length=10, max_length=10)
    pan_name: str = Field(min_length=2, max_length=200)


class AadhaarProfile(BaseModel):
    aadhaar_verified: bool = False
    name: str | None = None
    dob: str | None = None
    address: str | None = None


class BankVerification(BaseModel):
    account_holder_name: str
    bank_name: str
    account_number_last4: str = Field(min_length=4, max_length=4)
    ifsc: str = Field(min_length=11, max_length=11)


class OfferAcceptance(BaseModel):
    accepted: bool


class StageUpdate(BaseModel):
    stage: str


def _dump(value: dict[str, Any]) -> str:
    return json.dumps(value, default=str)


def _load(value: str | None) -> dict[str, Any]:
    try:
        return json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}


def _application(session, application_id: int) -> LoanApplication:
    raise RuntimeError("Use async _get_application")


async def _get_application(request: Request, application_id: int) -> LoanApplication:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        return obj


@router.post("/auth/start")
async def start_mobile_login(payload: ApplicationCreate, request: Request) -> dict[str, Any]:
    """Create an application shell. SMS/OTP delivery is intentionally an adapter hook."""
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = LoanApplication(mobile=payload.mobile, user_id=payload.user_id, stage="MOBILE_VERIFICATION")
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
        return {"application_id": obj.id, "stage": obj.stage, "otp_status": "PENDING_PROVIDER"}


@router.post("/{application_id}/pan")
async def verify_pan(application_id: int, payload: PanVerification, request: Request) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        pan = payload.pan.upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", pan):
            raise HTTPException(422, "Invalid PAN format")
        name_match = re.sub(r"[^A-Z]", "", obj.customer_name or payload.pan_name).upper() == re.sub(r"[^A-Z]", "", payload.pan_name).upper()
        obj.pan, obj.pan_name = pan, payload.pan_name
        obj.customer_name = payload.pan_name
        obj.stage = "AADHAAR_KYC"
        verification = _load(obj.verification_json)
        verification["pan"] = {"format_valid": True, "name_match": name_match, "provider_status": "PENDING_EXTERNAL_VERIFICATION"}
        obj.verification_json = _dump(verification)
        await session.commit()
        return {"application_id": obj.id, "pan": pan, "name_match": name_match, "next_stage": obj.stage}


@router.post("/{application_id}/aadhaar")
async def update_aadhaar(application_id: int, payload: AadhaarProfile, request: Request) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        if payload.name:
            obj.customer_name = payload.name
        verification = _load(obj.verification_json)
        verification["aadhaar"] = payload.model_dump()
        obj.verification_json = _dump(verification)
        obj.stage = "PROFILE_COMPLETION"
        await session.commit()
        return {"application_id": obj.id, "kyc": verification["aadhaar"], "next_stage": obj.stage}


@router.post("/{application_id}/documents")
async def upload_document(
    application_id: int,
    request: Request,
    document_type: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(413, "Document exceeds 15 MB limit")
    allowed = {"itr", "gst", "gst_return", "gst_bill", "bank_statement", "bureau", "business", "aadhaar"}
    key = document_type.lower().strip()
    if key not in allowed:
        raise HTTPException(422, f"Unsupported document_type. Allowed: {sorted(allowed)}")

    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        documents = _load(obj.documents_json)
        documents.setdefault(key, []).append({"filename": file.filename, "content_type": file.content_type, "size": len(content)})
        obj.documents_json = _dump(documents)
        obj.stage = "DOCUMENT_COLLECTION"
        await session.commit()
    return {"application_id": application_id, "document_type": key, "stored": True, "next_stage": "DOCUMENT_COLLECTION", "note": "Binary storage should be connected to object storage in production."}


@router.post("/{application_id}/analyze")
async def run_analysis(application_id: int, request: Request) -> dict[str, Any]:
    """Run deterministic analyzers against JSON-registered document metadata.

    Actual file bytes are intentionally processed at upload time by clients/worker adapters;
    this endpoint also accepts pre-parsed analysis payloads for secure object-storage workers.
    """
    body = await request.json()
    bank = body.get("bank_statement")
    bureau = body.get("bureau")
    gst = body.get("gst")
    invoices = body.get("invoices") or []

    # Worker-friendly mode: each item can provide filename + base64 content.
    import base64

    def decode(item: dict[str, Any]) -> tuple[str, bytes]:
        return str(item.get("filename", "upload.bin")), base64.b64decode(item.get("content_base64", ""))

    bank_result = analyze_bank_statement(*decode(bank)) if bank and bank.get("content_base64") else (bank or {})
    bureau_result = analyze_bureau(*decode(bureau)) if bureau and bureau.get("content_base64") else (bureau or {})
    gst_result = analyze_gst(*decode(gst)) if gst and gst.get("content_base64") else (gst or {})
    invoice_results = [analyze_invoice(*decode(item)) if item.get("content_base64") else item for item in invoices]
    cross = cross_document_match(bank_result, gst_result, invoice_results)

    # Existing 110-point scorecard: only award points from evidence actually supplied.
    score = 0
    components: dict[str, int] = {}
    if bank_result.get("monthly_credit_average", 0) > 0:
        components["bank_cashflow"] = 10
    if bank_result.get("bounce_count", 0) == 0 and bank_result:
        components["bank_stability"] = 5
    bureau_score = bureau_result.get("score")
    if isinstance(bureau_score, int):
        components["bureau_score"] = 15 if bureau_score >= 750 else 10 if bureau_score >= 700 else 5 if bureau_score >= 650 else 0
    if bureau_result.get("severe_credit_event_count", 0) == 0 and bureau_result:
        components["credit_behaviour"] = 15
    if gst_result.get("turnover", 0) > 0:
        components["gst_turnover"] = 10
    if cross.get("status") == "MATCH":
        components["cross_document_match"] = 10
    if cross.get("party_matches", 0) > 0:
        components["party_verification"] = 5
    score = min(110, sum(components.values()))
    risk_grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"
    decision = "AUTO_APPROVE" if score >= 90 else "MANUAL_REVIEW" if score >= 60 else "DECLINE_REVIEW"

    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        analyses = {"bank": bank_result, "bureau": bureau_result, "gst": gst_result, "invoices": invoice_results, "cross_document": cross, "score_components": components, "decision": decision}
        obj.analyses_json = _dump(analyses)
        obj.score = score
        obj.risk_grade = risk_grade
        obj.stage = "LOAN_OFFER" if decision == "AUTO_APPROVE" else "CREDIT_DECISION"
        await session.commit()

    return {"application_id": application_id, "score": score, "max_score": 110, "risk_grade": risk_grade, "decision": decision, "analysis": analyses, "next_stage": obj.stage}


@router.post("/{application_id}/bank-verification")
async def verify_bank_details(application_id: int, payload: BankVerification, request: Request) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        verification = _load(obj.verification_json)
        verification["bank"] = {**payload.model_dump(), "provider_status": "PENDING_EXTERNAL_ACCOUNT_VERIFICATION"}
        obj.verification_json = _dump(verification)
        obj.stage = "CREDIT_ASSESSMENT"
        await session.commit()
    return {"application_id": application_id, "verification": verification["bank"], "next_stage": obj.stage}


@router.post("/{application_id}/offer")
async def create_offer(application_id: int, request: Request) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        if not obj.score or obj.score < 90:
            raise HTTPException(409, "Loan offer requires an approved credit decision")
        analysis = _load(obj.analyses_json)
        monthly_income = float(analysis.get("bank", {}).get("monthly_credit_average", 0) or 0)
        eligible = min(500000.0, round(monthly_income * 2.0, -3)) if monthly_income else 0.0
        offer = {"eligible_amount": eligible, "tenure_months": 24, "annual_interest_rate": 18.0, "processing_fee_percent": 2.0, "basis": "scorecard + analyzed cashflow", "status": "OFFERED"}
        obj.offer_json = _dump(offer)
        obj.stage = "LOAN_OFFER"
        await session.commit()
    return {"application_id": application_id, "offer": offer, "next_stage": "LOAN_OFFER"}


@router.post("/{application_id}/offer/accept")
async def accept_offer(application_id: int, payload: OfferAcceptance, request: Request) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        if not payload.accepted:
            obj.status = "OFFER_DECLINED"
            await session.commit()
            return {"application_id": application_id, "status": obj.status}
        offer = _load(obj.offer_json)
        offer["status"] = "ACCEPTED"
        obj.offer_json = _dump(offer)
        obj.stage = "E_MANDATE"
        await session.commit()
    return {"application_id": application_id, "offer": offer, "next_stage": "E_MANDATE"}


@router.post("/{application_id}/mandate")
async def create_mandate(application_id: int, request: Request) -> dict[str, Any]:
    return await _advance(application_id, "E_SIGN", request, "E_MANDATE", {"status": "PENDING_PROVIDER"})


@router.post("/{application_id}/esign")
async def create_esign(application_id: int, request: Request) -> dict[str, Any]:
    return await _advance(application_id, "FINAL_APPROVAL", request, "E_SIGN", {"status": "PENDING_PROVIDER"})


@router.post("/{application_id}/disburse")
async def disburse(application_id: int, request: Request) -> dict[str, Any]:
    return await _advance(application_id, "LOAN_ACTIVE", request, "FINAL_APPROVAL", {"status": "PENDING_BANK_TRANSFER"})


async def _advance(application_id: int, next_stage: str, request: Request, required_stage: str, event: dict[str, Any]) -> dict[str, Any]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        if obj.stage != required_stage:
            raise HTTPException(409, f"Application must be in {required_stage}; current stage is {obj.stage}")
        verification = _load(obj.verification_json)
        verification[required_stage.lower()] = event
        obj.verification_json = _dump(verification)
        obj.stage = next_stage
        if next_stage == "LOAN_ACTIVE":
            obj.status = "DISBURSEMENT_PENDING"
        await session.commit()
        return {"application_id": application_id, "stage": next_stage, "event": event}


@router.get("/{application_id}")
async def get_application(application_id: int, request: Request) -> dict[str, Any]:
    obj = await _get_application(request, application_id)
    return obj.to_dict()


@router.post("/{application_id}/stage")
async def update_stage(application_id: int, payload: StageUpdate, request: Request) -> dict[str, Any]:
    if payload.stage not in STAGES:
        raise HTTPException(422, "Unknown loan stage")
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        obj = await session.scalar(select(LoanApplication).where(LoanApplication.id == application_id))
        if obj is None:
            raise HTTPException(404, "Loan application not found")
        obj.stage = payload.stage
        await session.commit()
    return {"application_id": application_id, "stage": payload.stage}
