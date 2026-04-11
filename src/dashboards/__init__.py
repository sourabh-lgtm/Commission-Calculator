"""Role-specific dashboard HTML modules."""
from src.dashboards.sdr import build_html as _sdr
from src.dashboards.cs  import build_html as _cs
from src.dashboards.ae  import build_html as _ae
from src.dashboards.am  import build_html as _am
from src.dashboards.se  import build_html as _se

_BUILDERS = {
    "sdr": _sdr,
    "cs":  _cs,
    "ae":  _ae,
    "am":  _am,
    "se":  _se,
}
DEFAULT_ROLE = "sdr"

ROLE_LABELS = {
    "sdr": "SDR",
    "cs":  "Climate Strategy Advisor",
    "ae":  "Account Executive",
    "am":  "Account Manager",
    "se":  "Solutions Engineer",
}


def build_dashboard_html(role: str) -> str:
    builder = _BUILDERS.get(role, _BUILDERS[DEFAULT_ROLE])
    return builder(role)
