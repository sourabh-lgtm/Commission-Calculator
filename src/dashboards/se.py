"""Solutions Engineer dashboard."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('se-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('se-monthly')">Monthly Summary</div>
    <div class="tab" onclick="showTab('se-quarterly')">Quarterly Performance</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('se-individual')">SE Detail</div>
    <div class="tab" onclick="showTab('workings')">Bonus Workings</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ SE TEAM OVERVIEW -->
<div id="tab-se-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">Solutions Engineer bonus for the selected month</p>
  <div class="controls">
    <button class="btn" onclick="exportCSV('se-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="se-to-kpis"></div>
  <div class="two-col">
    <div class="panel"><h3>Total Payout by SE</h3><canvas id="se-chart-bonus" height="220"></canvas></div>
    <div class="panel"><h3>New Business Achievement %</h3><canvas id="se-chart-nb" height="220"></canvas></div>
  </div>
  <div class="panel">
    <h3>SE Breakdown</h3>
    <div class="tbl-wrap"><table id="se-to-table"></table></div>
  </div>
</div>

<!-- ============================================================ SE MONTHLY SUMMARY -->
<div id="tab-se-monthly" class="tab-content">
  <div class="page-title">Monthly Summary</div>
  <p class="page-sub">All SEs side-by-side \u2014 bonus only appears in quarter-end months (Mar / Jun / Sep / Dec)</p>
  <div class="panel">
    <div class="tbl-wrap"><table id="se-ms-table"></table></div>
  </div>
</div>

<!-- ============================================================ SE QUARTERLY PERFORMANCE -->
<div id="tab-se-quarterly" class="tab-content">
  <div class="page-title">Quarterly Performance</div>
  <p class="page-sub">New Business &amp; ARR scorecard for the quarter</p>
  <div class="controls">
    <label>Year</label>
    <select id="se-qs-year" onchange="loadSEQuarterly()"></select>
    <label>Quarter</label>
    <select id="se-qs-quarter" onchange="loadSEQuarterly()">
      <option value="1">Q1</option><option value="2">Q2</option>
      <option value="3">Q3</option><option value="4" selected>Q4</option>
    </select>
  </div>
  <div class="kpi-grid" id="se-qs-kpis"></div>
  <div class="panel">
    <h3>Scorecard</h3>
    <div class="tbl-wrap"><table id="se-qs-table"></table></div>
  </div>
  <div class="panel">
    <h3>Achievement Progress</h3>
    <div id="se-qs-bars"></div>
  </div>
</div>

<!-- ============================================================ SE INDIVIDUAL DETAIL -->
<div id="tab-se-individual" class="tab-content">
  <div class="page-title">SE Detail</div>
  <p class="page-sub">Quarter-by-quarter performance for an individual Solutions Engineer</p>
  <div class="controls">
    <label>Solutions Engineer</label>
    <select id="se-ind-emp" onchange="loadSEIndividual()"></select>
  </div>
  <div class="kpi-grid" id="se-ind-kpis"></div>
  <div class="panel"><h3>Monthly Payout Trend</h3><canvas id="se-ind-chart" height="60"></canvas></div>
  <div class="panel">
    <h3>Monthly Breakdown</h3>
    <div class="tbl-wrap"><table id="se-ind-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// SE \u2014 role init + tab dispatch
// ============================================================

async function onRoleInit() {
  const seEmps = employees.filter(e => e.role === 'se');

  ['se-ind-emp', 'wk-emp'].forEach(selId => {
    const sel = document.getElementById(selId);
    if (!sel) return;
    sel.innerHTML = '';
    seEmps.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.employee_id; opt.text = e.name;
      sel.appendChild(opt);
    });
  });

  const curYr = new Date().getFullYear();
  ['se-qs-year','ps-year','ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  showTab('se-overview');
}

function loadTab(name) {
  if (name === 'se-overview')       loadSEOverview();
  else if (name === 'se-monthly')        loadSEMonthlySummary();
  else if (name === 'se-quarterly')      loadSEQuarterly();
  else if (name === 'se-individual')     loadSEIndividual();
  else if (name === 'workings')          loadWorkings();
  else if (name === 'approve-send')      loadApprovalStatus();
  else if (name === 'payroll-summary')   loadPayrollSummary();
  else if (name === 'accrual-summary')   loadAccrualSummary();
  else if (name === 'data-view')         loadDataView();
}

// ============================================================
// SE Team Overview
// ============================================================
async function loadSEOverview() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/se_overview?month=' + month);
  const data  = await res.json();
  const {employees: emps, kpis} = data;

  const isQEnd = ['03','06','09','12'].includes(month.slice(5,7));

  document.getElementById('se-to-kpis').innerHTML =
    kpiCard('Total Payout', fmtAmt(kpis.total_bonus_eur, 'EUR'), 'In EUR') +
    kpiCard('Active SEs', kpis.num_active, fmtMonth(month)) +
    (isQEnd ? kpiCard('Quarter-end', 'Bonus included', 'NB + ARR measures') : '');

  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('se-chart-bonus', labels, emps.map(e => e.total_commission_eur), 'Total Payout (EUR)');
  renderBar('se-chart-nb', labels, emps.map(e => e.nb_achievement_pct), 'New Business Achievement %', '#7c3aed');

  const heads = isQEnd
    ? ['Name','Region','Cur','Q Bonus Target','NB Achievement','NB Bonus','ARR Achievement','ARR Bonus','Total (EUR)']
    : ['Name','Region','Currency','Total'];
  const rows = emps.map(e => {
    if (isQEnd) return [
      e.name, e.region, e.currency,
      fmtAmt(e.quarterly_bonus_target, e.currency),
      e.nb_achievement_pct ? e.nb_achievement_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.nb_bonus, e.currency),
      e.arr_achievement_pct ? e.arr_achievement_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.arr_bonus, e.currency),
      '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>',
    ];
    return [e.name, e.region, e.currency,
      '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>'];
  });
  renderTable('se-to-table', heads, rows);
}

// ============================================================
// SE Monthly Summary
// ============================================================
async function loadSEMonthlySummary() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/se_overview?month=' + month);
  const data  = await res.json();
  const emps  = data.employees || [];

  const isQEnd = ['03','06','09','12'].includes(month.slice(5,7));
  const heads = isQEnd
    ? ['Name','Region','Currency','Q Bonus Target','NB %','NB Bonus','ARR %','ARR Bonus','Total']
    : ['Name','Region','Currency','Total'];

  const rows = emps.map(e => {
    if (isQEnd) return [
      e.name, e.region, e.currency,
      fmtAmt(e.quarterly_bonus_target, e.currency),
      e.nb_achievement_pct ? e.nb_achievement_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.nb_bonus, e.currency),
      e.arr_achievement_pct ? e.arr_achievement_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.arr_bonus, e.currency),
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
    ];
    return [e.name, e.region, e.currency,
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>'];
  });
  renderTable('se-ms-table', heads, rows);
}

// ============================================================
// SE Quarterly Performance
// ============================================================
async function loadSEQuarterly() {
  const yr = document.getElementById('se-qs-year').value;
  const qt = document.getElementById('se-qs-quarter').value;
  const res  = await fetch('/api/se_quarterly?year=' + yr + '&quarter=' + qt);
  const data = await res.json();
  const emps = data.employees || [];

  const totalBonus = emps.reduce((s,e) => s + e.total_commission, 0);

  document.getElementById('se-qs-kpis').innerHTML =
    kpiCard('Total Q Bonus', fmtAmt(totalBonus,'mixed'), 'All currencies') +
    kpiCard('SEs', emps.length, 'Q' + qt + ' ' + yr);

  const heads = ['Name','Q Target','NB %','NB Bonus','ARR %','ARR Bonus','Total'];
  const rows = emps.map(e => [
    e.name,
    fmtAmt(e.quarterly_bonus_target, e.currency),
    e.nb_achievement_pct ? e.nb_achievement_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.nb_bonus, e.currency),
    e.arr_achievement_pct ? e.arr_achievement_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.arr_bonus, e.currency),
    '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
  ]);
  renderTable('se-qs-table', heads, rows);

  // Achievement progress bars
  const barsEl = document.getElementById('se-qs-bars');
  barsEl.innerHTML = emps.map(e => {
    const nbW  = Math.min(125, e.nb_achievement_pct  || 0);
    const arrW = Math.min(125, e.arr_achievement_pct || 0);
    const nbCol  = (e.nb_achievement_pct  || 0) >= 100 ? 'var(--green)' : 'var(--accent)';
    const arrCol = (e.arr_achievement_pct || 0) >= 100 ? 'var(--green)' : 'var(--accent)';
    const mkBar = (label, val, w, col) =>
      '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--dim);margin-bottom:2px"><span>' + label + '</span><span>' +
      (val || 0).toFixed(1) + '%</span></div><div class="progress-wrap"><div class="progress-bar" style="width:' +
      Math.min(100,w) + '%;background:' + col + '"></div></div></div>';
    return '<div style="margin-bottom:18px"><div style="font-size:13px;font-weight:600;margin-bottom:6px">' +
      e.name + '</div>' +
      mkBar('New Business (80%)', e.nb_achievement_pct,  nbW,  nbCol) +
      mkBar('Company ARR (20%)', e.arr_achievement_pct, arrW, arrCol) +
      '</div>';
  }).join('');
}

// ============================================================
// SE Individual Detail
// ============================================================
async function loadSEIndividual() {
  const empId = document.getElementById('se-ind-emp').value;
  if (!empId) return;

  const res  = await fetch('/api/sdr_detail?employee_id=' + empId);
  const data = await res.json();
  const {employee: emp, rows, ytd_commission} = data;
  const cur = emp.currency || 'EUR';

  document.getElementById('se-ind-kpis').innerHTML =
    kpiCard('YTD Total', fmtAmt(ytd_commission, cur), emp.region || '') +
    kpiCard('Role', emp.title || '', emp.country || '');

  renderLine('se-ind-chart', rows.map(r => r.month), rows.map(r => r.total_commission), 'Total Payout');

  const heads = ['Month','Q','Q Bonus Target','NB %','NB Bonus','ARR %','ARR Bonus','Total'];
  const rowData = rows.map(r => [
    r.month, r.quarter,
    fmtAmt(r.quarterly_bonus_target || 0, cur),
    r.nb_achievement_pct ? r.nb_achievement_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(r.nb_bonus || 0, cur),
    r.arr_achievement_pct ? r.arr_achievement_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(r.arr_bonus || 0, cur),
    '<strong>' + fmtAmt(r.total_commission, cur) + '</strong>',
  ]);
  renderTable('se-ind-table', heads, rowData);
}
"""


def build_html(role: str = "se") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator \u2014 Normative (SE)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
