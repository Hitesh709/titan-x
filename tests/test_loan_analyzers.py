from titan_x.services.loan_analyzers import (
    analyze_bank_statement,
    analyze_gst,
    analyze_invoice,
    cross_document_match,
)


def test_bank_csv_analysis() -> None:
    content = b"Date,Description,Credit,Debit,Party\n2026-08-01,ABC Traders,100000,,ABC Traders\n2026-08-05,EMI,,20000,Bank\n"
    result = analyze_bank_statement("statement.csv", content)
    assert result["transaction_count"] == 2
    assert result["total_credits"] == 100000
    assert result["bounce_count"] == 0
    assert result["emi_transaction_count"] == 1


def test_gst_and_invoice_matching() -> None:
    gst = analyze_gst(
        "gst.csv",
        b"GSTIN,Type,Turnover\n24ABCDE1234F1Z5,B2B,120000\n",
    )
    invoice = analyze_invoice(
        "invoice.txt",
        b"Buyer: ABC Traders\nGSTIN: 24ABCDE1234F1Z5\nInvoice No: INV-1\nGrand Total: 100000",
    )
    bank = {
        "monthly_credit_average": 20000,
        "top_credit_parties": [["ABCTRADERS", 100000]],
    }
    cross = cross_document_match(bank, gst, [invoice])
    assert gst["gstin_count"] == 1
    assert invoice["invoice_number"] == "INV-1"
    assert cross["party_matches"] == 1
