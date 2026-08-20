from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def _money(value: Any) -> float:
    try:
        return float(Decimal(str(value).replace(",", "").replace("₹", "").strip()))
    except (InvalidOperation, ValueError, TypeError):
        return 0.0


def _norm(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(content)).pages)
    except Exception:
        return ""


def _rows_from_upload(filename: str, content: bytes) -> list[dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="ignore")
        return list(csv.DictReader(io.StringIO(text)))
    if lower.endswith((".xlsx", ".xls")):
        try:
            import pandas as pd

            frame = pd.read_excel(io.BytesIO(content))
            return frame.fillna("").to_dict(orient="records")
        except Exception:
            return []
    return []


def analyze_bank_statement(filename: str, content: bytes) -> dict[str, Any]:
    rows = _rows_from_upload(filename, content)
    text = _extract_pdf_text(content) if filename.lower().endswith(".pdf") else ""
    if not rows and text:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        amounts = [_money(x.replace("₹", "")) for x in re.findall(r"(?:₹|INR)?\s*([\d,]+(?:\.\d{1,2})?)", text)]
        credits = sum(amounts)
        return {
            "source": filename,
            "parser": "pdf_text_heuristic",
            "transaction_count_estimate": len(amounts),
            "total_credits_estimate": round(credits, 2),
            "monthly_credit_average": round(credits / 6, 2),
            "emi_count_estimate": len(re.findall(r"\bEMI\b", text, re.I)),
            "bounce_count_estimate": len(re.findall(r"bounce|return|dishonou", text, re.I)),
            "cash_activity_estimate": len(re.findall(r"cash", text, re.I)),
            "raw_lines": len(lines),
            "confidence": 0.45,
            "requires_review": True,
        }

    credits = debits = cash = 0.0
    bounces = emis = 0
    parties: defaultdict[str, float] = defaultdict(float)
    for row in rows:
        normalized = {str(k).strip().lower(): v for k, v in row.items()}
        amount = _money(normalized.get("amount") or normalized.get("transaction amount") or normalized.get("credit") or 0)
        credit = _money(normalized.get("credit") or normalized.get("credit amount") or 0)
        debit = _money(normalized.get("debit") or normalized.get("debit amount") or 0)
        if credit == 0 and debit == 0 and amount:
            direction = str(normalized.get("type") or normalized.get("transaction type") or "").lower()
            if "credit" in direction or "cr" in direction:
                credit = amount
            else:
                debit = amount
        credits += credit
        debits += debit
        desc = str(normalized.get("description") or normalized.get("narration") or normalized.get("remarks") or "")
        if "cash" in desc.lower():
            cash += abs(credit or debit)
        if re.search(r"bounce|return|dishonour|ecs return", desc, re.I):
            bounces += 1
        if re.search(r"\bemi\b|loan repayment|nach", desc, re.I):
            emis += 1
        party = str(normalized.get("party") or normalized.get("beneficiary") or "").strip()
        if party and credit:
            parties[_norm(party)] += credit

    months = max(1, min(6, len(rows) // 20 or 1))
    return {
        "source": filename,
        "parser": "tabular",
        "transaction_count": len(rows),
        "total_credits": round(credits, 2),
        "total_debits": round(debits, 2),
        "monthly_credit_average": round(credits / months, 2),
        "cash_activity": round(cash, 2),
        "bounce_count": bounces,
        "emi_transaction_count": emis,
        "top_credit_parties": sorted(parties.items(), key=lambda item: item[1], reverse=True)[:20],
        "confidence": 0.9,
        "requires_review": False,
    }


def analyze_bureau(filename: str, content: bytes) -> dict[str, Any]:
    text = _extract_pdf_text(content) if filename.lower().endswith(".pdf") else content.decode("utf-8", errors="ignore")
    score_match = re.search(r"(?:CIBIL|CREDIT)\s*SCORE[^\d]{0,20}(\d{3})", text, re.I)
    dpd_90 = len(re.findall(r"(?:90\+|90\s*DPD|written off|write[- ]?off|settled|suit filed)", text, re.I))
    enquiries = len(re.findall(r"enquir", text, re.I))
    active_loans = len(re.findall(r"active|open", text, re.I))
    return {
        "source": filename,
        "score": int(score_match.group(1)) if score_match else None,
        "active_loan_indicator_count": active_loans,
        "enquiry_indicator_count": enquiries,
        "severe_credit_event_count": dpd_90,
        "raw_text_available": bool(text),
        "confidence": 0.75 if score_match else 0.4,
        "requires_review": not bool(score_match),
    }


def analyze_gst(filename: str, content: bytes) -> dict[str, Any]:
    rows = _rows_from_upload(filename, content)
    text = _extract_pdf_text(content) if filename.lower().endswith(".pdf") else ""
    turnover = 0.0
    gstin_count = 0
    b2b = b2c = 0
    for row in rows:
        normalized = {str(k).strip().lower(): v for k, v in row.items()}
        turnover += _money(normalized.get("turnover") or normalized.get("taxable value") or normalized.get("invoice value") or normalized.get("total") or 0)
        if re.fullmatch(r"[0-9A-Z]{15}", str(normalized.get("gstin", "")).upper().strip()):
            gstin_count += 1
        typ = str(normalized.get("type") or normalized.get("customer type") or "").lower()
        b2b += int("b2b" in typ)
        b2c += int("b2c" in typ)
    if not rows and text:
        turnover = sum(_money(v) for v in re.findall(r"(?:turnover|taxable value|invoice value)[^\d]{0,20}([\d,]+(?:\.\d+)?)", text, re.I))
        gstin_count = len(set(re.findall(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z0-9]\b", text.upper())))
        b2b = len(re.findall(r"\bB2B\b", text, re.I))
        b2c = len(re.findall(r"\bB2C\b", text, re.I))
    return {
        "source": filename,
        "turnover": round(turnover, 2),
        "gstin_count": gstin_count,
        "b2b_records": b2b,
        "b2c_records": b2c,
        "filing_indicators": len(re.findall(r"GSTR[- ]?(?:1|3B)", text, re.I)) if text else 0,
        "confidence": 0.85 if rows else 0.55,
        "requires_review": not bool(rows or text),
    }


def analyze_invoice(filename: str, content: bytes) -> dict[str, Any]:
    text = _extract_pdf_text(content) if filename.lower().endswith(".pdf") else content.decode("utf-8", errors="ignore")
    gstins = sorted(set(re.findall(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z0-9]\b", text.upper())))
    invoice = re.search(r"(?:invoice|inv)\s*(?:no|number|#)?\s*[:\-]?\s*([A-Z0-9\-/]+)", text, re.I)
    amount_values = [_money(v) for v in re.findall(r"(?:total|grand total|invoice value)[^\d]{0,20}([\d,]+(?:\.\d{1,2})?)", text, re.I)]
    party = re.search(r"(?:buyer|customer|party|bill to)\s*[:\-]?\s*([^\n]{2,100})", text, re.I)
    return {
        "source": filename,
        "invoice_number": invoice.group(1) if invoice else None,
        "gstins": gstins,
        "party_name": party.group(1).strip() if party else None,
        "invoice_amount": round(amount_values[0], 2) if amount_values else None,
        "confidence": 0.8 if text else 0.2,
        "requires_review": not bool(text),
    }


def cross_document_match(bank: dict[str, Any], gst: dict[str, Any], invoices: list[dict[str, Any]]) -> dict[str, Any]:
    bank_turnover = _money(bank.get("monthly_credit_average"))
    gst_turnover = _money(gst.get("turnover"))
    ratio = None
    if bank_turnover and gst_turnover:
        ratio = min(bank_turnover, gst_turnover) / max(bank_turnover, gst_turnover)
    bank_parties = {key for key, _ in bank.get("top_credit_parties", [])}
    invoice_parties = {_norm(item.get("party_name")) for item in invoices if item.get("party_name")}
    party_matches = len(bank_parties & invoice_parties) if bank_parties and invoice_parties else 0
    return {
        "bank_gst_turnover_consistency": round(ratio, 4) if ratio is not None else None,
        "party_matches": party_matches,
        "invoice_count": len(invoices),
        "invoice_bank_party_match_rate": round(party_matches / max(1, len(invoice_parties)), 4) if invoice_parties else None,
        "status": "MATCH" if ratio is not None and ratio >= 0.7 else "REVIEW",
    }
