"""Account Executive dashboard — stub (commission plan not yet implemented)."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Coming Soon</div>
    <div class="tab active" onclick="showTab('ae-placeholder')">AE Dashboard</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<div id="tab-ae-placeholder" class="tab-content active">
  <div class="page-title">Account Executive Dashboard</div>
  <p class="page-sub">Commission plan coming soon</p>
  <div class="panel" style="color:var(--dim);font-size:13px;line-height:1.8">
    <p>The AE commission plan has not been implemented yet.</p>
    <p style="margin-top:8px">Once <code>src/commission_plans/ae.py</code> is built and registered, this dashboard will populate with:</p>
    <ul style="margin-top:8px;margin-left:20px">
      <li>Team overview: pipeline, closed-won, quota attainment</li>
      <li>Monthly &amp; quarterly summary</li>
      <li>Individual deal-level workings</li>
      <li>Approve &amp; Send statements</li>
    </ul>
  </div>
</div>
"""

_ROLE_JS = """
async function onRoleInit() {
  const curYr = new Date().getFullYear();
  ['ps-year','ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });
  showTab('ae-placeholder');
}

function loadTab(name) {
  if (name === 'payroll-summary')  loadPayrollSummary();
  else if (name === 'accrual-summary') loadAccrualSummary();
  else if (name === 'data-view')   loadDataView();
}
"""


def build_html(role: str = "ae") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator — Normative (AE)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
