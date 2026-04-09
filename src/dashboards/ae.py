"""Account Executive dashboard — full implementation."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('ae-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('ae-annual')">Annual Summary</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('ae-detail')">AE Detail</div>
    <div class="tab" onclick="showTab('workings')">Commission Workings</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ AE TEAM OVERVIEW -->
<div id="tab-ae-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">Account Executive ACV pipeline &amp; year-end commission</p>
  <div class="controls">
    <label>Year</label>
    <select id="ae-year" onchange="loadAEOverview()"></select>
    <button class="btn" onclick="exportCSV('ae-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="ae-to-kpis"></div>
  <div class="panel">
    <h3>ACV by AE</h3>
    <canvas id="ae-chart-acv" height="120"></canvas>
  </div>
  <div class="panel">
    <h3>AE Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-to-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE ANNUAL SUMMARY -->
<div id="tab-ae-annual" class="tab-content">
  <div class="page-title">Annual Summary</div>
  <p class="page-sub">Full year ACV &amp; commission breakdown per AE</p>
  <div class="controls">
    <label>Year</label>
    <select id="ae-ann-year" onchange="loadAEAnnual()"></select>
  </div>
  <div class="panel">
    <h3>Annual Commission Summary</h3>
    <div class="tbl-wrap"><table id="ae-ann-table"></table></div>
  </div>
</div>

<!-- ============================================================ AE DETAIL -->
<div id="tab-ae-detail" class="tab-content">
  <div class="page-title">AE Detail</div>
  <p class="page-sub">Per-quarter performance &amp; gate status for an individual AE</p>
  <div class="controls">
    <label>AE</label>
    <select id="ae-emp" onchange="loadAEDetail()"></select>
    <label>Year</label>
    <select id="ae-det-year" onchange="loadAEDetail()"></select>
  </div>
  <div class="kpi-grid" id="ae-det-kpis"></div>
  <div class="panel">
    <h3>Annual ACV Progress</h3>
    <div id="ae-det-progress"></div>
  </div>
  <div class="panel">
    <h3>Quarterly Breakdown</h3>
    <div class="tbl-wrap"><table id="ae-det-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// AE — role init + tab dispatch
// ============================================================
async function onRoleInit() {
  const curYr = new Date().getFullYear();

  // Populate year selectors
  ['ae-year', 'ae-ann-year', 'ae-det-year', 'ps-year', 'ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr - 1, curYr, curYr + 1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  // Populate AE employee dropdown
  rebuildEmpDropdowns();

  showTab('ae-overview');
}

function rebuildEmpDropdowns() {
  const aeEmps = employees.filter(e => e.role === 'ae');
  ['ae-emp', 'wk-emp'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    const prev = el.value;
    el.innerHTML = '';
    aeEmps.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.employee_id; opt.text = e.name;
      el.appendChild(opt);
    });
    if (aeEmps.some(e => e.employee_id === prev)) el.value = prev;
  });
}

function loadTab(name) {
  if (name === 'ae-overview')       loadAEOverview();
  else if (name === 'ae-annual')    loadAEAnnual();
  else if (name === 'ae-detail')    loadAEDetail();
  else if (name === 'workings')     loadWorkings();
  else if (name === 'approve-send') loadApprovalStatus();
  else if (name === 'payroll-summary')  loadPayrollSummary();
  else if (name === 'accrual-summary')  loadAccrualSummary();
  else if (name === 'data-view')    loadDataView();
}

// ============================================================
// AE Team Overview
// ============================================================
async function loadAEOverview() {
  const yr  = document.getElementById('ae-year').value;
  const res = await fetch('/api/ae_overview?year=' + yr);
  const data = await res.json();
  const {employees: emps, kpis} = data;

  // KPI cards
  document.getElementById('ae-to-kpis').innerHTML =
    kpiCard('Total YTD ACV', '\u20ac' + fmtNum(kpis.total_acv_eur), 'EUR') +
    kpiCard('Team Avg Attainment', kpis.avg_attainment_pct + '%', 'Annual target') +
    kpiCard('Year-end Commission', '\u20ac' + fmtNum(kpis.total_year_end_comm_eur), 'EUR') +
    kpiCard('Active AEs', kpis.num_aes, 'FY' + yr);

  // Bar chart
  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('ae-chart-acv', labels, emps.map(e => e.ytd_acv_eur), 'YTD ACV (EUR)');

  // Table
  const heads = ['Name', 'Region', 'Cur',
    'Q1 ACV', 'Q1 Gate', 'Q2 ACV', 'Q2 Gate',
    'Q3 ACV', 'Q3 Gate', 'Q4 ACV', 'Q4 Gate',
    'Annual ACV', 'vs Target', 'Year-end Comm'];

  const rows = emps.map(e => {
    const attColor = e.annual_attainment_pct >= 100
      ? 'var(--green)' : e.annual_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(e.q1_acv), gateIcon(e.q1_gate),
      '\u20ac' + fmtNum(e.q2_acv), gateIcon(e.q2_gate),
      '\u20ac' + fmtNum(e.q3_acv), gateIcon(e.q3_gate),
      '\u20ac' + fmtNum(e.q4_acv), gateIcon(e.q4_gate),
      '<strong>\u20ac' + fmtNum(e.ytd_acv_eur) + '</strong>',
      '<span style="color:' + attColor + ';font-weight:600">' + e.annual_attainment_pct + '%</span>',
      e.year_end_commission > 0
        ? '<strong>' + fmtAmt(e.year_end_commission, e.currency) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
    ];
  });
  renderTable('ae-to-table', heads, rows);
}

// ============================================================
// AE Annual Summary
// ============================================================
async function loadAEAnnual() {
  const yr  = document.getElementById('ae-ann-year').value;
  const res = await fetch('/api/ae_overview?year=' + yr);
  const data = await res.json();
  const {employees: emps} = data;

  const heads = ['Name', 'Region', 'Cur', 'Annual Target EUR', 'YTD ACV EUR',
    'Attainment %', 'Qualifying ACV', 'Year-end Comm (local)', 'Year-end Comm (EUR)'];

  const rows = emps.map(e => {
    const attColor = e.annual_attainment_pct >= 100
      ? 'var(--green)' : e.annual_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    return [
      e.name, e.region, e.currency,
      '\u20ac' + fmtNum(e.annual_target_eur),
      '\u20ac' + fmtNum(e.ytd_acv_eur),
      '<span style="color:' + attColor + ';font-weight:600">' + e.annual_attainment_pct + '%</span>',
      '\u20ac' + fmtNum(e.qualifying_acv_eur),
      e.year_end_commission > 0
        ? '<strong>' + fmtAmt(e.year_end_commission, e.currency) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
      e.year_end_commission_eur > 0
        ? '<strong>\u20ac' + fmtNum(e.year_end_commission_eur) + '</strong>'
        : '<span style="color:var(--dim)">\u2014</span>',
    ];
  });
  renderTable('ae-ann-table', heads, rows);
}

// ============================================================
// AE Detail
// ============================================================
async function loadAEDetail() {
  const empId = document.getElementById('ae-emp').value;
  const yr    = document.getElementById('ae-det-year').value;
  if (!empId) return;

  const res  = await fetch('/api/ae_detail?employee_id=' + empId + '&year=' + yr);
  const data = await res.json();
  const {employee: emp, quarters, year_end} = data;
  const cur  = emp.currency || 'EUR';

  // KPI cards
  const commAmt = emp.year_end_commission || 0;
  const attColor = (emp.annual_attainment_pct || 0) >= 100
    ? 'var(--green)' : (emp.annual_attainment_pct || 0) >= 50
    ? 'var(--orange)' : 'var(--red)';

  document.getElementById('ae-det-kpis').innerHTML =
    kpiCard('Annual Target', '\u20ac' + fmtNum(emp.annual_target_eur || 0), 'EUR') +
    kpiCard('YTD ACV', '\u20ac' + fmtNum(emp.ytd_acv_eur || 0), 'EUR') +
    kpiCard('Attainment', '<span style="color:' + attColor + '">' + (emp.annual_attainment_pct || 0) + '%</span>', 'vs annual target') +
    kpiCard('Year-end Commission', fmtAmt(commAmt, cur), commAmt > 0 ? 'Paid in December' : 'Not yet paid');

  // Progress bar
  const target = emp.annual_target_eur || 1;
  const acv    = emp.ytd_acv_eur || 0;
  const pct50  = 50;
  const pct100 = 100;
  const pctACV = Math.min(150, (acv / target) * 100);
  const barColor = acv >= target ? 'var(--green)' : acv >= target * 0.5 ? 'var(--accent)' : 'var(--red)';

  document.getElementById('ae-det-progress').innerHTML =
    '<div style="position:relative;margin-bottom:8px">' +
      '<div style="background:var(--border);border-radius:10px;height:18px;position:relative">' +
        '<div style="background:' + barColor + ';width:' + pctACV + '%;height:18px;border-radius:10px;transition:width .4s"></div>' +
        '<div style="position:absolute;top:0;left:' + pct50 + '%;height:18px;width:2px;background:var(--dim);opacity:.6"></div>' +
        '<div style="position:absolute;top:0;left:' + Math.min(100, pct100) + '%;height:18px;width:2px;background:#000;opacity:.4"></div>' +
      '</div>' +
      '<div style="display:flex;justify-content:space-between;font-size:10px;color:var(--dim);margin-top:4px">' +
        '<span>0</span>' +
        '<span style="position:absolute;left:' + pct50 + '%">50% gate</span>' +
        '<span style="position:absolute;left:' + Math.min(99, pct100) + '%">100%</span>' +
        '<span>\u20ac' + fmtNum(target) + '</span>' +
      '</div>' +
    '</div>';

  // Quarterly table
  const heads = ['Quarter', 'Q ACV (EUR)', 'Q Target (EUR)', 'Attainment', 'Gate Met', 'Total Deals', 'Invoiced', 'Forecast'];
  const rows = (quarters || []).map(q => {
    const gateStr = q.gate_met
      ? '<span style="color:var(--green);font-weight:700">\u2713 Met</span>'
      : '<span style="color:var(--red);font-weight:700">\u2717 Not Met</span>';
    const attColor2 = q.q_attainment_pct >= 100
      ? 'var(--green)' : q.q_attainment_pct >= 50
      ? 'var(--orange)' : 'var(--red)';
    return [
      q.q_label,
      '\u20ac' + fmtNum(q.q_acv_eur),
      '\u20ac' + fmtNum(q.q_target_eur),
      '<span style="color:' + attColor2 + ';font-weight:600">' + q.q_attainment_pct + '%</span>',
      gateStr,
      q.deals_count,
      q.invoiced_count,
      q.forecast_count,
    ];
  });
  renderTable('ae-det-table', heads, rows);
}

// ============================================================
// Helpers
// ============================================================
function gateIcon(met) {
  return met
    ? '<span style="color:var(--green);font-weight:700">\u2713</span>'
    : '<span style="color:var(--red);font-weight:700">\u2717</span>';
}

function fmtNum(v) {
  const n = parseFloat(v);
  if (isNaN(n)) return '\u2014';
  return n.toLocaleString('en-GB', {minimumFractionDigits: 0, maximumFractionDigits: 0});
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
