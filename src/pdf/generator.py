"""PDF commission statement generator — public entry point."""
import os
from datetime import date

from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, PageBreak

from src.pdf._constants import MARGIN
from src.pdf._cover import _cover_page
from src.pdf._sdr import _summary_page, _workings_page
from src.pdf._cs import _cs_summary_page, _cs_workings_page
from src.pdf._ae import _ae_summary_page, _ae_workings_page
from src.pdf._am import _am_summary_page, _am_workings_page
from src.pdf._se import _se_summary_page, _se_workings_page


def generate_statement(
    employee: dict,
    month_str: str,          # "2026-02-01"
    summary: dict,           # from commission_detail row
    workings_rows: list[dict],
    accelerator: dict | None,
    output_path: str,
    logo_path: str | None = None,
) -> str:
    """Generate a PDF commission statement and save to output_path. Returns output_path."""

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    month_ts = date.fromisoformat(month_str)
    period_label = month_ts.strftime("%B %Y")   # "February 2026"
    currency = employee.get("currency", "EUR")
    role = employee.get("role", "sdr")

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )

    story = []

    # ------------------------------------------------------------------
    # PAGE 1 — Cover (shared)
    # ------------------------------------------------------------------
    story.extend(_cover_page(employee, period_label, logo_path))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 2 — Summary  (role-specific)
    # ------------------------------------------------------------------
    if role in ("cs", "cs_lead", "cs_director"):
        story.extend(_cs_summary_page(employee, period_label, summary, currency))
    elif role in ("am", "am_lead"):
        story.extend(_am_summary_page(employee, period_label, summary, currency))
    elif role == "ae":
        story.extend(_ae_summary_page(employee, period_label, summary, accelerator, currency))
    elif role == "se":
        story.extend(_se_summary_page(employee, period_label, summary, currency))
    else:
        story.extend(_summary_page(employee, period_label, summary, accelerator, currency))
    story.append(PageBreak())

    # ------------------------------------------------------------------
    # PAGE 3+ — Full Workings  (role-specific)
    # ------------------------------------------------------------------
    if role in ("cs", "cs_lead", "cs_director"):
        story.extend(_cs_workings_page(employee, period_label, workings_rows, summary, currency))
    elif role in ("am", "am_lead"):
        story.extend(_am_workings_page(employee, period_label, workings_rows, summary, currency))
    elif role == "ae":
        story.extend(_ae_workings_page(employee, period_label, workings_rows, accelerator, currency))
    elif role == "se":
        story.extend(_se_workings_page(employee, period_label, workings_rows, summary, currency))
    else:
        story.extend(_workings_page(employee, period_label, workings_rows, currency))

    doc.build(story)
    return output_path
