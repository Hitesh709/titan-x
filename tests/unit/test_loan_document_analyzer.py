from titan_x.services.loan_document_analyzer import (
    analyze_bank_statement,
    analyze_bureau,
    analyze_gst,
    analyze_gst_bills,
    build_loan_analysis,
    match_bank_to_gst,
)


def test_bank_statement_metrics():
    result = analyze_bank_statement(
        [
            {"Date": "01-01-2026", "Description": "ABC TRADERS", "Credit": "100000", "Debit": "0"},
            {"Date": "10-01-2026", "Description": "EMI ABC", "Credit": "0", "Debit": "20000"},
            {"Date": "01-02-2026", "Description": "ABC TRADERS", "Credit": "120000", "Debit": "0"},
            {"Date": "10-02-2026", "Description": "EMI ABC", "Credit": "0", "Debit": "20000"},
        ]
    )
    assert result["status"] == "ok"
    assert result["total_credits"] == 220000
    assert result["estimated_monthly_emi"] == 20000
    assert result["bounce_count"] == 0


def test_bureau_detects_adverse_credit():
    result = analyze_bureau("CIBIL SCORE: 742\nDPD: 30\nOne account settled")
    assert result["score"] == 742
    assert result["max_dpd"] == 30
    assert "writeoff_or_settlement" in result["adverse_flags"]


def test_gst_and_bill_extraction():
    gst = analyze_gst("GSTIN 24ABCDE1234F1Z5\nTURNOVER: 12,50,000\nGSTR-3B B2B")
    bill = analyze_gst_bills("GSTIN 24ABCDE1234F1Z5\nINVOICE NO: INV-1001\nTOTAL: 1,18,000\nBUYER: ABC TRADERS")
    assert gst["gstins"] == ["24ABCDE1234F1Z5"]
    assert gst["estimated_detected_turnover"] == 1250000
    assert bill["invoice_numbers"] == ["INV-1001"]
    assert bill["invoice_amounts"] == [118000]


def test_bank_gst_party_and_amount_match():
    bank = analyze_bank_statement(
        [{"Date": "01-01-2026", "Description": "ABC TRADERS", "Credit": "118000", "Debit": "0"}]
    )
    bills = analyze_gst_bills("BUYER: ABC TRADERS\nTOTAL: 118000")
    result = match_bank_to_gst(bank, bills)
    assert result["match_count"] == 1
    assert result["confidence"] > 0.9


def test_loan_summary_produces_foir_and_decision():
    bank = analyze_bank_statement(
        [
            {"Date": "01-01-2026", "Description": "SALES", "Credit": "100000", "Debit": "0"},
            {"Date": "10-01-2026", "Description": "EMI", "Credit": "0", "Debit": "20000"},
        ]
    )
    result = build_loan_analysis(bank=bank, bureau={"max_dpd": 0}, gst={}, gst_bills={})
    assert result["foir"] == 0.2
    assert result["decision"] == "eligible"
