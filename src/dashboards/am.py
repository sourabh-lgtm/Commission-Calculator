"""Account Manager dashboard."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('am-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('am-monthly')">Monthly Summary</div>
    <div class="tab" onclick="showTab('am-quarterly')">Quarterly Performance</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('am-individual')">Manager Detail</div>
    <div class="tab" onclick="showTab('workings')">Bonus Workings</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('accrual-vs-payroll')">Accruals vs Payroll</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ AM TEAM OVERVIEW -->
<div id="tab-am-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">Account Manager bonus &amp; referrals for the selected month</p>
  <div class="controls">
    <button class="btn" onclick="exportCSV('am-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="am-to-kpis"></div>
  <div class="two-col">
    <div class="panel"><h3>Total Payout by Manager</h3><canvas id="am-chart-bonus" height="220"></canvas></div>
    <div class="panel"><h3>NRR % by Manager</h3><canvas id="am-chart-nrr" height="220"></canvas></div>
  </div>
  <div class="panel">
    <h3>Manager Breakdown</h3>
    <div class="tbl-wrap"><table id="am-to-table"></table></div>
  </div>
</div>

<!-- ============================================================ AM MONTHLY SUMMARY -->
<div id="tab-am-monthly" class="tab-content">
  <div class="page-title">Monthly Summary</div>
  <p class="page-sub">All managers side-by-side — bonus only appears in quarter-end months (Mar / Jun / Sep / Dec)</p>
  <div class="panel">
    <div class="tbl-wrap"><table id="am-ms-table"></table></div>
  </div>
</div>

<!-- ============================================================ AM QUARTERLY PERFORMANCE -->
<div id="tab-am-quarterly" class="tab-content">
  <div class="page-title">Quarterly Performance</div>
  <p class="page-sub">NRR scorecard for the quarter</p>
  <div class="controls">
    <label>Year</label>
    <select id="am-qs-year" onchange="loadAMQuarterly()"></select>
    <label>Quarter</label>
    <select id="am-qs-quarter" onchange="loadAMQuarterly()">
      <option value="1">Q1</option><option value="2">Q2</option>
      <option value="3">Q3</option><option value="4" selected>Q4</option>
    </select>
  </div>
  <div class="kpi-grid" id="am-qs-kpis"></div>
  <div class="panel">
    <h3>Scorecard</h3>
    <div class="tbl-wrap"><table id="am-qs-table"></table></div>
  </div>
  <div class="panel">
    <h3>NRR Attainment</h3>
    <div id="am-qs-bars"></div>
  </div>
</div>

<!-- ============================================================ AM INDIVIDUAL DETAIL -->
<div id="tab-am-individual" class="tab-content">
  <div class="page-title">Manager Detail</div>
  <p class="page-sub">Quarter-by-quarter performance for an individual account manager</p>
  <div class="controls">
    <label>Manager</label>
    <select id="am-ind-emp" onchange="loadAMIndividual()"></select>
  </div>
  <div class="kpi-grid" id="am-ind-kpis"></div>
  <div class="panel"><h3>Monthly Payout Trend</h3><canvas id="am-ind-chart" height="60"></canvas></div>
  <div class="panel">
    <h3>Monthly Breakdown</h3>
    <div class="tbl-wrap"><table id="am-ind-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// AM — role init + tab dispatch
// ============================================================

async function onRoleInit() {
  // Populate AM individual and workings dropdowns from employees list
  const amEmps = employees.filter(e => e.role === 'am' || e.role === 'am_lead');

  ['am-ind-emp', 'wk-emp'].forEach(selId => {
    const sel = document.getElementById(selId);
    if (!sel) return;
    sel.innerHTML = '';
    amEmps.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.employee_id; opt.text = e.name;
      sel.appendChild(opt);
    });
  });

  const curYr = new Date().getFullYear();
  ['am-qs-year','ps-year','ac-year','avp-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  showTab('am-overview');
}

function loadTab(name) {
  if (name === 'am-overview')      loadAMOverview();
  else if (name === 'am-monthly')       loadAMMonthlySummary();
  else if (name === 'am-quarterly')     loadAMQuarterly();
  else if (name === 'am-individual')    loadAMIndividual();
  else if (name === 'workings')         loadWorkings();
  else if (name === 'approve-send')     loadApprovalStatus();
  else if (name === 'payroll-summary')  loadPayrollSummary();
  else if (name === 'accrual-summary')      loadAccrualSummary();
  else if (name === 'accrual-vs-payroll')   loadAccrualVsPayroll();
  else if (name === 'data-view')        loadDataView();
}

// ============================================================
// AM Team Overview
// ============================================================
async function loadAMOverview() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/am_overview?month=' + month);
  const data  = await res.json();
  const {employees: emps, kpis} = data;

  document.getElementById('am-to-kpis').innerHTML =
    kpiCard('Total Payout', fmtAmt(kpis.total_bonus_eur, 'EUR'), 'In EUR') +
    kpiCard('Avg NRR', kpis.avg_nrr_pct + '%', 'Team average') +
    kpiCard('Active Managers', kpis.num_active, fmtMonth(month));

  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('am-chart-bonus', labels, emps.map(e => e.total_commission_eur), 'Total Payout (EUR)');
  renderBar('am-chart-nrr',   labels, emps.map(e => e.nrr_pct), 'NRR %', '#7c3aed');

  const heads = ['Name','Region','Cur','Q Bonus Target','NRR %','NRR Bonus','Multi-yr ACV','Referrals','Ref Comm','Accel','Total (EUR)'];
  const rows = emps.map(e => [
    e.name, e.region, e.currency,
    fmtAmt(e.quarterly_bonus_target, e.currency),
    e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.nrr_bonus, e.currency),
    e.multi_year_comm ? fmtAmt(e.multi_year_comm, e.currency) : '\u2014',
    e.referral_sao_count || 0,
    fmtAmt((e.referral_sao_comm||0) + (e.referral_cw_comm||0), e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>',
  ]);
  renderTable('am-to-table', heads, rows);
}

// ============================================================
// AM Monthly Summary
// ============================================================
async function loadAMMonthlySummary() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/am_overview?month=' + month);
  const data  = await res.json();
  const emps  = data.employees || [];

  const isQEnd = ['03','06','09','12'].includes(month.slice(5,7));
  const heads = isQEnd
    ? ['Name','Region','Currency','NRR %','NRR Bonus','NRR Accel','Multi-yr ACV','Referral Comm','Total']
    : ['Name','Region','Currency','Multi-yr ACV','Referral Comm','Total'];

  const rows = emps.map(e => {
    const refComm = fmtAmt((e.referral_sao_comm||0) + (e.referral_cw_comm||0), e.currency);
    const myAcv   = e.multi_year_comm ? fmtAmt(e.multi_year_comm, e.currency) : '\u2014';
    if (isQEnd) return [
      e.name, e.region, e.currency,
      e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.nrr_bonus, e.currency),
      fmtAmt(e.accelerator_topup, e.currency),
      myAcv, refComm,
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
    ];
    return [e.name, e.region, e.currency, myAcv, refComm,
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>'];
  });
  renderTable('am-ms-table', heads, rows);
}

// ============================================================
// AM Quarterly Performance
// ============================================================
async function loadAMQuarterly() {
  const yr = document.getElementById('am-qs-year').value;
  const qt = document.getElementById('am-qs-quarter').value;
  const res  = await fetch('/api/am_quarterly?year=' + yr + '&quarter=' + qt);
  const data = await res.json();
  const emps = data.employees || [];

  const totalBonus = emps.reduce((s,e) => s + e.total_commission, 0);
  const avgNrr     = emps.length ? emps.reduce((s,e) => s + e.nrr_pct, 0) / emps.length : 0;

  document.getElementById('am-qs-kpis').innerHTML =
    kpiCard('Total Q Bonus', fmtAmt(totalBonus,'mixed'), 'All currencies') +
    kpiCard('Avg NRR', avgNrr.toFixed(1) + '%', 'Team average') +
    kpiCard('Managers', emps.length, 'Q' + qt + ' ' + yr);

  const heads = ['Name','Q Target','NRR %','NRR Bonus','NRR Accel','Multi-yr ACV','Ref SAOs','Ref Comm','Total'];
  const rows = emps.map(e => [
    e.name,
    fmtAmt(e.quarterly_bonus_target, e.currency),
    e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.nrr_bonus, e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    e.multi_year_comm ? fmtAmt(e.multi_year_comm, e.currency) : '\u2014',
    e.referral_sao_count || 0,
    fmtAmt((e.referral_sao_comm||0) + (e.referral_cw_comm||0), e.currency),
    '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
  ]);
  renderTable('am-qs-table', heads, rows);

  // NRR progress bars
  const barsEl = document.getElementById('am-qs-bars');
  barsEl.innerHTML = emps.map(e => {
    const w   = Math.min(100, e.nrr_pct);
    const col = e.nrr_pct >= 100 ? 'var(--green)' : 'var(--accent)';
    const bar = '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--dim);margin-bottom:2px"><span>NRR (100%)</span><span>' +
      e.nrr_pct.toFixed(1) + '%</span></div><div class="progress-wrap"><div class="progress-bar" style="width:' +
      w + '%;background:' + col + '"></div></div></div>';
    return '<div style="margin-bottom:18px"><div style="font-size:13px;font-weight:600;margin-bottom:6px">' +
      e.name + '</div>' + bar + '</div>';
  }).join('');
}

// ============================================================
// AM Individual Detail
// ============================================================
async function loadAMIndividual() {
  const empId = document.getElementById('am-ind-emp').value;
  if (!empId) return;

  const res  = await fetch('/api/sdr_detail?employee_id=' + empId);
  const data = await res.json();
  const {employee: emp, rows, ytd_commission} = data;
  const cur = emp.currency || 'EUR';

  document.getElementById('am-ind-kpis').innerHTML =
    kpiCard('YTD Total', fmtAmt(ytd_commission, cur), emp.region || '') +
    kpiCard('Role', emp.title || '', emp.country || '');

  renderLine('am-ind-chart', rows.map(r => r.month), rows.map(r => r.total_commission), 'Total Payout');

  const heads = ['Month','Q','NRR Bonus','NRR Accel','Multi-yr ACV','Ref Comm','Total'];
  const rowData = rows.map(r => [
    r.month, r.quarter,
    fmtAmt(r.nrr_bonus || 0, cur),
    fmtAmt(r.accelerator_topup || 0, cur),
    fmtAmt(r.multi_year_comm || 0, cur),
    fmtAmt((r.referral_sao_comm||0) + (r.referral_cw_comm||0), cur),
    '<strong>' + fmtAmt(r.total_commission, cur) + '</strong>',
  ]);
  renderTable('am-ind-table', heads, rowData);
}
"""


def build_html(role: str = "am") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator — Normative (AM)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
