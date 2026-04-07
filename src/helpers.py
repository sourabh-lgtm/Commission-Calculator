import json
import math
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Quarter helpers
# ---------------------------------------------------------------------------

def month_to_quarter(month: pd.Timestamp) -> str:
    """Return 'Q1 FY26' style label for a given month timestamp."""
    q = (month.month - 1) // 3 + 1
    yr = str(month.year)[-2:]
    return f"Q{q} FY{yr}"


def quarter_end_month(month: pd.Timestamp) -> pd.Timestamp:
    """Return the last month of the quarter containing `month`."""
    q = (month.month - 1) // 3
    end_month = (q + 1) * 3  # 3, 6, 9, or 12
    return pd.Timestamp(year=month.year, month=end_month, day=1)


def quarter_months(year: int, quarter: int) -> list[pd.Timestamp]:
    """Return list of 3 month timestamps for a given year/quarter (1-indexed)."""
    start = (quarter - 1) * 3 + 1
    return [pd.Timestamp(year=year, month=start + i, day=1) for i in range(3)]


# ---------------------------------------------------------------------------
# FX lookup
# ---------------------------------------------------------------------------

def get_fx_rate(fx_df: pd.DataFrame, month: pd.Timestamp, currency: str) -> float:
    """Return EUR → `currency` rate for the given month.
    Falls back to nearest available month if exact match missing.
    """
    if currency == "EUR":
        return 1.0
    col = f"EUR_{currency}"
    if col not in fx_df.columns:
        return 1.0
    row = fx_df[fx_df["month"] == month]
    if row.empty:
        # Use closest prior month
        prior = fx_df[fx_df["month"] <= month]
        if prior.empty:
            return 1.0
        row = prior.iloc[[-1]]
    val = row[col].iloc[0]
    return float(val) if not math.isnan(val) else 1.0


# ---------------------------------------------------------------------------
# JSON serialiser
# ---------------------------------------------------------------------------

def clean_value(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 2)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return round(v, 2)
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def clean_json(obj):
    """Recursively clean an object for JSON serialisation."""
    if isinstance(obj, dict):
        return {k: clean_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_json(i) for i in obj]
    return clean_value(obj)


def df_to_records(df: pd.DataFrame) -> list[dict]:
    return clean_json(df.to_dict(orient="records"))


# ---------------------------------------------------------------------------
# Currency formatting helpers
# ---------------------------------------------------------------------------

CURRENCY_SYMBOLS = {"SEK": "kr", "GBP": "£", "EUR": "€", "USD": "$"}


def fmt_currency(amount: float, currency: str) -> str:
    sym = CURRENCY_SYMBOLS.get(currency, currency)
    if currency in ("SEK",):
        return f"{amount:,.0f} {sym}"
    return f"{sym}{amount:,.0f}"


# ---------------------------------------------------------------------------
# Scaffold builder
# ---------------------------------------------------------------------------

def build_scaffold(entities: pd.Series, months: list[pd.Timestamp]) -> pd.DataFrame:
    """Cross-join a list of entity IDs with a list of months."""
    df_e = pd.DataFrame({"employee_id": entities})
    df_m = pd.DataFrame({"month": months})
    df_e["_key"] = 1
    df_m["_key"] = 1
    scaffold = df_e.merge(df_m, on="_key").drop(columns="_key")
    return scaffold
