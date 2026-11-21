"""GET /summary: a deterministic overview of the invoice data. No LLM involved."""

from app.data import FX_NOTE, FX_TO_EUR, Dataset
from app.schemas import CurrencyBreakdown, Lineage, StatusBreakdown, SummaryResponse

STATUS_NOTE = "Vendor status is the current vendor-master snapshot, not the status on the invoice date."


def build_summary(ds: Dataset, request_id: str) -> SummaryResponse:
    inv = ds.invoices
    credit_notes = int(inv["is_credit_note"].sum())

    by_currency = [
        CurrencyBreakdown(
            currency=ccy,
            invoice_count=len(g),
            total_native=round(float(g["amount"].sum()), 2),
            eur_approx=round(float(g["amount_eur"].sum()), 2),
        )
        for ccy, g in inv.groupby("currency")
    ]

    by_status = [
        StatusBreakdown(
            vendor_status=status,
            vendor_count=g["vendor_id"].nunique(),
            invoice_count=len(g),
            eur_approx=round(float(g["amount_eur"].sum()), 2),
        )
        for status, g in inv.groupby("vendor_status")
    ]

    return SummaryResponse(
        request_id=request_id,
        invoice_count=len(inv),
        period_start=inv["invoice_date"].min().date().isoformat(),
        period_end=inv["invoice_date"].max().date().isoformat(),
        total_eur_approx=round(float(inv["amount_eur"].sum()), 2),
        by_currency=by_currency,
        by_vendor_status=by_status,
        lineage=Lineage(
            sources=list(ds.sources),
            rows_used=len(inv),
            credit_notes_included=credit_notes,
            fx_rates_to_eur=FX_TO_EUR,
            notes=[
                f"Totals are net: {credit_notes} credit notes (negative amounts) are included.",
                FX_NOTE,
                STATUS_NOTE,
            ],
        ),
    )
