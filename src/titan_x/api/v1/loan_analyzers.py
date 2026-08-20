from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from titan_x.api.dependencies import get_current_active_user
from titan_x.models.user import User
from titan_x.services.loan_document_analyzer import (
    analyze_bank_statement,
    analyze_bureau,
    analyze_gst,
    analyze_gst_bills,
    build_loan_analysis,
    match_bank_to_gst,
    parse_csv,
    parse_pdf_text,
    parse_xlsx,
)

router = APIRouter(prefix="/loan-analyzers", tags=["loan-analyzers"])
MAX_UPLOAD_BYTES = 15 * 1024 * 1024


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 15 MB limit")
    return (file.filename or "upload.bin").lower(), content


def _parse_rows(filename: str, content: bytes) -> list[dict]:
    if filename.endswith(".csv"):
        return parse_csv(content)
    if filename.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(content)
    raise HTTPException(status_code=400, detail="Bank statement must be CSV or XLSX for structured analysis")


def _parse_text(filename: str, content: bytes) -> str:
    if filename.endswith(".pdf"):
        return parse_pdf_text(content)
    if filename.endswith((".txt", ".csv")):
        return content.decode("utf-8-sig", errors="replace")
    raise HTTPException(status_code=400, detail="Document must be PDF or TXT/CSV")


@router.post("/bank")
async def analyze_bank(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    filename, content = await _read_upload(file)
    return analyze_bank_statement(_parse_rows(filename, content))


@router.post("/bureau")
async def analyze_bureau_report(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    filename, content = await _read_upload(file)
    return analyze_bureau(_parse_text(filename, content))


@router.post("/gst")
async def analyze_gst_report(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    filename, content = await _read_upload(file)
    return analyze_gst(_parse_text(filename, content))


@router.post("/gst-bills")
async def analyze_gst_bill(
    file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    filename, content = await _read_upload(file)
    return analyze_gst_bills(_parse_text(filename, content))


@router.post("/cross-match")
async def cross_match_documents(
    bank_file: Annotated[UploadFile, File(...)],
    gst_bill_file: Annotated[UploadFile, File(...)],
    user: Annotated[User, Depends(get_current_active_user)],
):
    bank_name, bank_content = await _read_upload(bank_file)
    gst_name, gst_content = await _read_upload(gst_bill_file)
    bank = analyze_bank_statement(_parse_rows(bank_name, bank_content))
    bills = analyze_gst_bills(_parse_text(gst_name, gst_content))
    return match_bank_to_gst(bank, bills)


@router.post("/loan-summary")
async def loan_summary(
    bank_file: Annotated[UploadFile | None, File(None)] = None,
    bureau_file: Annotated[UploadFile | None, File(None)] = None,
    gst_file: Annotated[UploadFile | None, File(None)] = None,
    gst_bill_file: Annotated[UploadFile | None, File(None)] = None,
    user: Annotated[User, Depends(get_current_active_user)] = None,
):
    bank = bureau = gst = bills = None
    if bank_file:
        name, content = await _read_upload(bank_file)
        bank = analyze_bank_statement(_parse_rows(name, content))
    if bureau_file:
        name, content = await _read_upload(bureau_file)
        bureau = analyze_bureau(_parse_text(name, content))
    if gst_file:
        name, content = await _read_upload(gst_file)
        gst = analyze_gst(_parse_text(name, content))
    if gst_bill_file:
        name, content = await _read_upload(gst_bill_file)
        bills = analyze_gst_bills(_parse_text(name, content))
    return build_loan_analysis(bank, bureau, gst, bills)
