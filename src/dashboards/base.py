"""Shared HTML/CSS/JS building blocks for all role dashboards."""
from src.dashboards._styles import CSS
from src.dashboards._shared_html import SHARED_TABS_HTML, SHARED_MODALS
from src.dashboards._shared_js import SHARED_JS


def _role_options_html(selected_role: str) -> str:
    roles = [
        ("sdr", "SDR"),
        ("cs",  "Climate Strategy Advisor"),
        ("ae",  "Account Executive"),
        ("am",  "Account Manager"),
    ]
    return "".join(
        f'<option value="{v}"{" selected" if v == selected_role else ""}>{label}</option>'
        for v, label in roles
    )


def assemble_html(
    role: str,
    title: str,
    nav_links: str,
    role_tabs_html: str,
    role_js: str,
) -> str:
    role_opts = _role_options_html(role)
    return (
        f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>{CSS}</style>
</head>
<body>

<nav>
  <div class="logo">
    <small>Normative</small>
    <h1>Commissions</h1>
  </div>
  <div class="global-filter">
    <label>Month</label>
    <select id="global-month" onchange="onGlobalMonthChange()"></select>
  </div>
  <div class="global-filter" style="margin-top:8px">
    <label>Role</label>
    <select id="global-role" onchange="onGlobalRoleChange()">
      {role_opts}
    </select>
  </div>
  <div class="tabs">
    {nav_links}
  </div>
</nav>

<main>
{role_tabs_html}
{SHARED_TABS_HTML}
</main>

{SHARED_MODALS}

<script>
{role_js}
{SHARED_JS}
</script>
</body>
</html>"""
    )
