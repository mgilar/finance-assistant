"""Data layer: load the CSVs once, validate them, and build one enriched invoice table.

Every number the app shows (summary, tool results, evidence rows) is computed from
`Dataset.invoices`, so there is a single source of truth with a known lineage:
data/invoices_2025_clean.csv joined with data/vendor_master.csv.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
INVOICES_FILE = "invoices_2025_clean.csv"
VENDORS_FILE = "vendor_master.csv"

# Illustrative 2025 average rates (1 unit of currency -> EUR). NOT ECB rates.
# Policy §5.1 requires the ECB reference rate on the invoice date; that is a
# production item (docs/production_backlog.md). Every response that uses a
# converted figure must carry FX_NOTE.
FX_TO_EUR: dict[str, float] = {"EUR": 1.0, "GBP": 1.17, "USD": 0.89}
FX_NOTE = (
    "EUR figures use approximate fixed rates (1 GBP = 1.17 EUR, 1 USD = 0.89 EUR), "
    "not the ECB rate on the invoice date required by policy §5.1. "
    "Native-currency amounts are exact."
)

INVOICE_COLUMNS = [
    "invoice_number", "invoice_date", "vendor_id", "vendor_name", "description",
    "amount", "currency", "cost_center", "po_number", "approved_by",
]
VENDOR_COLUMNS = ["vendor_id", "vendor_name", "country", "category", "status"]


class DataValidationError(Exception):
    """Raised at startup when the source files don't match what the app assumes."""


@dataclass(frozen=True)
class Dataset:
    invoices: pd.DataFrame  # one row per invoice, enriched with vendor fields + amount_eur
    vendors: pd.DataFrame
    sources: tuple[str, ...]


def load_dataset(data_dir: Path = DATA_DIR) -> Dataset:
    # Read identifiers as strings; keep_default_na=False so empty cells stay "" and
    # we decide explicitly what "missing" means (below), instead of pandas guessing.
    invoices = pd.read_csv(
        data_dir / INVOICES_FILE, dtype=str, keep_default_na=False
    )
    vendors = pd.read_csv(data_dir / VENDORS_FILE, dtype=str, keep_default_na=False)

    _require_columns(invoices, INVOICE_COLUMNS, INVOICES_FILE)
    _require_columns(vendors, VENDOR_COLUMNS, VENDORS_FILE)

    invoices["amount"] = pd.to_numeric(invoices["amount"], errors="raise")
    invoices["invoice_date"] = pd.to_datetime(invoices["invoice_date"], format="%Y-%m-%d")

    # Fail fast on assumptions the rest of the app relies on.
    unknown_ccy = set(invoices["currency"]) - set(FX_TO_EUR)
    if unknown_ccy:
        raise DataValidationError(f"No FX rate for currencies: {sorted(unknown_ccy)}")
    orphans = set(invoices["vendor_id"]) - set(vendors["vendor_id"])
    if orphans:
        raise DataValidationError(f"Invoices reference unknown vendors: {sorted(orphans)}")
    if invoices["invoice_number"].duplicated().any():
        raise DataValidationError("Duplicate invoice numbers")

    # Missing PO / approver are meaningful policy facts (§2.2, §3.1): make them explicit None.
    for col in ("po_number", "approved_by"):
        invoices[col] = invoices[col].str.strip().replace("", None)

    # Join vendor master data. Category/country/status come ONLY from the master
    # (decision: category = vendor-master category, never the free-text description).
    # Status is today's snapshot, not the status on the invoice date.
    enriched = invoices.merge(
        vendors[["vendor_id", "country", "category", "status"]].rename(
            columns={"status": "vendor_status", "category": "vendor_category",
                     "country": "vendor_country"}
        ),
        on="vendor_id",
        how="left",
        validate="many_to_one",
    )

    enriched["amount_eur"] = (enriched["amount"] * enriched["currency"].map(FX_TO_EUR)).round(2)
    # Credit notes stay in totals (net spend); this flag lets answers say how many were included.
    enriched["is_credit_note"] = enriched["amount"] < 0

    return Dataset(
        invoices=enriched,
        vendors=vendors,
        sources=(f"data/{INVOICES_FILE}", f"data/{VENDORS_FILE}"),
    )


def _require_columns(df: pd.DataFrame, expected: list[str], filename: str) -> None:
    missing = set(expected) - set(df.columns)
    if missing:
        raise DataValidationError(f"{filename} is missing columns: {sorted(missing)}")
