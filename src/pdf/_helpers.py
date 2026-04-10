"""Small formatting helpers shared across all PDF page builders."""
from reportlab.platypus import Paragraph
from reportlab.lib.styles import ParagraphStyle


def _para(text, style):
    return Paragraph(str(text), style)


def _style(name, **kwargs):
    return ParagraphStyle(name, **kwargs)


def _sym(currency):
    return {"SEK": "kr ", "GBP": "\u00a3", "EUR": "\u20ac", "USD": "$"}.get(currency, "")


def _num(v):
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return str(v)


def _rate_label(currency, kind):
    from src.commission_plans.sdr import FIXED_RATES
    rates = FIXED_RATES.get(currency, FIXED_RATES["EUR"])
    key = "outbound_sao" if kind == "outbound" else "inbound_sao"
    sym = _sym(currency)
    return f"{sym}{rates[key]:,} / SAO"


def _accel_desc(accelerator, currency):
    if not accelerator or not accelerator.get("accelerator_topup", 0):
        return "Not triggered (< 9 SAOs / quarter)"
    sym    = _sym(currency)
    excess = accelerator.get("excess_outbound", 0)
    topup  = accelerator.get("topup_per_sao", 0)
    return f"{excess} excess outbound \u00d7 {sym}{topup:,} top-up"
