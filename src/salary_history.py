"""Prorated salary calculations for bonus-based commission roles (AM, CS, etc.).

For roles where commission = % of salary:
  - If salary changes mid-period, each segment is weighted by calendar days.
  - If role changes mid-period, each role segment uses its own bonus % and salary.
"""

import pandas as pd


def get_prorated_monthly_salary(
    salary_history: pd.DataFrame,
    employee_id: str,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
) -> float:
    """Return the prorated monthly-equivalent salary for [period_start, period_end].

    Example: salary was 40,000 for 15 days, then 45,000 for 75 days in a 90-day quarter.
    Prorated monthly = (40000 * 15 + 45000 * 75) / 90 = 43,333.33

    Returns prorated monthly salary in the employee's local currency.
    """
    if salary_history.empty:
        return 0.0

    emp_hist = salary_history[salary_history["employee_id"] == employee_id].copy()
    if emp_hist.empty:
        return 0.0

    total_days   = (period_end - period_start).days + 1
    weighted_sum = 0.0

    for _, row in emp_hist.iterrows():
        seg_start = row["effective_date"]
        seg_end   = row["end_date"] if pd.notna(row["end_date"]) else period_end

        # Overlap of this salary segment with the period
        overlap_start = max(seg_start, period_start)
        overlap_end   = min(seg_end,   period_end)

        if overlap_end < overlap_start:
            continue

        overlap_days  = (overlap_end - overlap_start).days + 1
        weighted_sum += row["salary_monthly"] * overlap_days

    return round(weighted_sum / total_days, 2) if total_days > 0 else 0.0


def get_role_segments(
    salary_history: pd.DataFrame,
    employee_id: str,
    period_start: pd.Timestamp,
    period_end: pd.Timestamp,
) -> list[dict]:
    """Return salary segments that overlap with [period_start, period_end].

    Each segment dict contains:
        effective_date, end_date, salary_monthly, salary_currency,
        role_at_time, title_at_time, overlap_days, weight (fraction of period)
    """
    if salary_history.empty:
        return []

    emp_hist   = salary_history[salary_history["employee_id"] == employee_id].copy()
    total_days = (period_end - period_start).days + 1
    segments   = []

    for _, row in emp_hist.iterrows():
        seg_start = row["effective_date"]
        seg_end   = row["end_date"] if pd.notna(row["end_date"]) else period_end

        overlap_start = max(seg_start, period_start)
        overlap_end   = min(seg_end,   period_end)

        if overlap_end < overlap_start:
            continue

        overlap_days = (overlap_end - overlap_start).days + 1
        segments.append({
            "effective_date":  row["effective_date"],
            "end_date":        row["end_date"],
            "salary_monthly":  row["salary_monthly"],
            "salary_currency": row["salary_currency"],
            "role_at_time":    row["role_at_time"],
            "title_at_time":   row["title_at_time"],
            "overlap_start":   overlap_start,
            "overlap_end":     overlap_end,
            "overlap_days":    overlap_days,
            "weight":          round(overlap_days / total_days, 6),
        })

    return segments


def quarter_date_range(year: int, quarter: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (first_day, last_day) for a calendar quarter."""
    start_month = (quarter - 1) * 3 + 1
    end_month   = start_month + 2
    q_start = pd.Timestamp(year=year, month=start_month, day=1)
    # Last day of end_month
    q_end   = (pd.Timestamp(year=year, month=end_month, day=1)
               + pd.offsets.MonthEnd(0))
    return q_start, q_end


def month_date_range(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (first_day, last_day) for a calendar month."""
    m_start = pd.Timestamp(year=year, month=month, day=1)
    m_end   = m_start + pd.offsets.MonthEnd(0)
    return m_start, m_end
