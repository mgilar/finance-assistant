"""Data-layer tests.

Expected values come from the independent profiling in docs/data_profile.md
(plain csv module, not this code), so they check the loader rather than echo it.
"""

import shutil

import pandas as pd
import pytest

from app.data import DATA_DIR, FX_TO_EUR, DataValidationError, load_dataset


@pytest.fixture(scope="module")
def ds():
    return load_dataset()


def test_row_counts(ds):
    assert len(ds.invoices) == 140
    assert len(ds.vendors) == 10


def test_native_sums_per_currency(ds):
    sums = ds.invoices.groupby("currency")["amount"].sum().round(2).to_dict()
    assert sums == {"EUR": 4493726.12, "GBP": 1182251.02, "USD": 1150445.53}


def test_eur_conversion_uses_fixed_rates(ds):
    expected = 4493726.12 + 1182251.02 * FX_TO_EUR["GBP"] + 1150445.53 * FX_TO_EUR["USD"]
    assert ds.invoices["amount_eur"].sum() == pytest.approx(expected, abs=1.0)


def test_credit_notes_are_kept_and_flagged(ds):
    credit = ds.invoices[ds.invoices["is_credit_note"]]
    assert sorted(credit["invoice_number"]) == ["INV-20029", "INV-20096"]


def test_missing_po_and_approver_are_none(ds):
    assert ds.invoices["po_number"].isna().sum() == 21
    assert ds.invoices["approved_by"].isna().sum() == 25


def test_vendor_join(ds):
    spain = ds.invoices[ds.invoices["vendor_country"] == "Spain"]
    assert set(spain["vendor_id"]) == {"V-1002", "V-1006", "V-1009"}
    assert ds.invoices["vendor_status"].value_counts().to_dict() == {
        "ACTIVE": 111, "INACTIVE": 17, "ON_HOLD": 12,
    }


def test_unknown_currency_fails_fast(tmp_path):
    for f in DATA_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    path = tmp_path / "invoices_2025_clean.csv"
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df.loc[0, "currency"] = "CHF"
    df.to_csv(path, index=False)
    with pytest.raises(DataValidationError, match="CHF"):
        load_dataset(tmp_path)
