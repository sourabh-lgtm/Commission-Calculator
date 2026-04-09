"""Climate Strategy Advisor dashboard: tabs, nav links, and JS."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('cs-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('cs-monthly')">Monthly Summary</div>
    <div class="tab" onclick="showTab('cs-quarterly')">Quarterly Performance</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('cs-individual')">Advisor Detail</div>
    <div class="tab" onclick="showTab('workings')">Bonus Workings</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ CS TEAM OVERVIEW -->
<div id="tab-cs-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">Climate Strategy Advisor bonus &amp; referrals for the selected month</p>
  <div class="controls">
    <button class="btn" onclick="exportCSV('cs-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="cs-to-kpis"></div>
  <div class="two-col">
    <div class="panel"><h3>Total Payout by Advisor</h3><canvas id="cs-chart-bonus" height="220"></canvas></div>
    <div class="panel"><h3>NRR % by Advisor</h3><canvas id="cs-chart-nrr" height="220"></canvas></div>
  </div>
  <div class="panel">
    <h3>Advisor Breakdown</h3>
    <div class="tbl-wrap"><table id="cs-to-table"></table></div>
  </div>
</div>

<!-- ============================================================ CS MONTHLY SUMMARY -->
<div id="tab-cs-monthly" class="tab-content">
  <div class="page-title">Monthly Summary</div>
  <p class="page-sub">All advisors side-by-side — bonus only appears in quarter-end months (Mar / Jun / Sep / Dec)</p>
  <div class="panel">
    <div class="tbl-wrap"><table id="cs-ms-table"></table></div>
  </div>
</div>

<!-- ============================================================ CS QUARTERLY PERFORMANCE -->
<div id="tab-cs-quarterly" class="tab-content">
  <div class="page-title">Quarterly Performance</div>
  <p class="page-sub">NRR · CSAT · Service Credits scorecard</p>
  <div class="controls">
    <label>Year</label>
    <select id="cs-qs-year" onchange="loadCSQuarterly()"></select>
    <label>Quarter</label>
    <select id="cs-qs-quarter" onchange="loadCSQuarterly()">
      <option value="1">Q1</option><option value="2">Q2</option>
      <option value="3">Q3</option><option value="4" selected>Q4</option>
    </select>
  </div>
  <div class="kpi-grid" id="cs-qs-kpis"></div>
  <div class="panel">
    <h3>Scorecard</h3>
    <div class="tbl-wrap"><table id="cs-qs-table"></table></div>
  </div>
  <div class="panel">
    <h3>Measure Attainment</h3>
    <div id="cs-qs-bars"></div>
  </div>
</div>

<!-- ============================================================ CS INDIVIDUAL DETAIL -->
<div id="tab-cs-individual" class="tab-content">
  <div class="page-title">Advisor Detail</div>
  <p class="page-sub">Quarter-by-quarter performance for an individual advisor</p>
  <div class="controls">
    <label>Team Lead</label>
    <select id="cs-team-lead" onchange="onCSTeamLeadChange()">
      <option value="">All Advisors</option>
      <option value="UK22">Johnny McCreesh</option>
      <option value="161">Delphine Froment</option>
      <option value="UK46">Riad Samir Wakim</option>
    </select>
    <label>Advisor</label>
    <select id="sd-emp" onchange="loadCSIndividual()"></select>
  </div>
  <div class="kpi-grid" id="cs-ind-kpis"></div>
  <div class="panel"><h3>Quarterly Payout Trend</h3><canvas id="cs-ind-chart" height="60"></canvas></div>
  <div class="panel">
    <h3>Quarterly Breakdown</h3>
    <div class="tbl-wrap"><table id="cs-ind-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// CS — role init + tab dispatch
// ============================================================

// Team Lead filter — repopulates sd-emp dropdown based on selected lead
function onCSTeamLeadChange() {
  const leadId = document.getElementById('cs-team-lead').value;
  const el = document.getElementById('sd-emp');
  if (!el) return;
  const prev = el.value;
  el.innerHTML = '';
  const csEmps = employees.filter(e => e.role === 'cs');
  const filtered = leadId ? csEmps.filter(e => (e.manager_id || '') === leadId) : csEmps;
  filtered.forEach(e => {
    const opt = document.createElement('option');
    opt.value = e.employee_id; opt.text = e.name;
    el.appendChild(opt);
  });
  if (filtered.some(e => e.employee_id === prev)) el.value = prev;
  if (el.options.length > 0) loadCSIndividual();
}

async function onRoleInit() {
  rebuildEmpDropdowns();

  const curYr = new Date().getFullYear();
  ['cs-qs-year','ps-year','ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  showTab('cs-overview');
}

function loadTab(name) {
  if (name === 'cs-overview')      loadCSOverview();
  else if (name === 'cs-monthly')       loadCSMonthlySummary();
  else if (name === 'cs-quarterly')     loadCSQuarterly();
  else if (name === 'cs-individual')    loadCSIndividual();
  else if (name === 'workings')         loadWorkings();
  else if (name === 'approve-send')     loadApprovalStatus();
  else if (name === 'payroll-summary')  loadPayrollSummary();
  else if (name === 'accrual-summary')  loadAccrualSummary();
  else if (name === 'data-view')        loadDataView();
}

// ============================================================
// CS Team Overview
// ============================================================
async function loadCSOverview() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/cs_overview?month=' + month);
  const data  = await res.json();
  const {employees: emps, kpis} = data;

  document.getElementById('cs-to-kpis').innerHTML =
    kpiCard('Total Payout', fmtAmt(kpis.total_bonus_eur, 'EUR'), 'In EUR') +
    kpiCard('Avg NRR', kpis.avg_nrr_pct + '%', 'Team average') +
    kpiCard('Avg CSAT', kpis.avg_csat_pct + '%', 'Team average') +
    kpiCard('Active Advisors', kpis.num_active, fmtMonth(month));

  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('cs-chart-bonus', labels, emps.map(e => e.total_commission_eur), 'Total Payout (EUR)');
  renderBar('cs-chart-nrr',   labels, emps.map(e => e.nrr_pct), 'NRR %', '#7c3aed');

  const heads = ['Name','Region','Cur','Q Bonus Target','NRR %','NRR Bonus','CSAT %','CSAT Bonus','Credits %','Credits Bonus','Referrals','Ref Comm','Accel','Total (EUR)'];
  const rows = emps.map(e => [
    e.name, e.region, e.currency,
    fmtAmt(e.quarterly_bonus_target, e.currency),
    e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.nrr_bonus, e.currency),
    e.csat_score_pct ? e.csat_score_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.csat_bonus, e.currency),
    e.credits_used_pct ? e.credits_used_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.credits_bonus, e.currency),
    e.referral_sao_count || 0,
    fmtAmt(e.referral_sao_comm + e.referral_cw_comm, e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>',
  ]);
  renderTable('cs-to-table', heads, rows);
}

// ============================================================
// CS Monthly Summary
// ============================================================
async function loadCSMonthlySummary() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/cs_overview?month=' + month);
  const data  = await res.json();
  const emps  = data.employees || [];

  const isQEnd = ['03','06','09','12'].includes(month.slice(5,7));
  const heads = isQEnd
    ? ['Name','Region','Currency','NRR %','NRR Bonus','CSAT %','CSAT Bonus','Credits %','Credits Bonus','NRR Accel','Referral Comm','Total']
    : ['Name','Region','Currency','Referral SAOs','Referral Comm','Total'];

  const rows = emps.map(e => {
    const refComm = fmtAmt((e.referral_sao_comm||0) + (e.referral_cw_comm||0), e.currency);
    if (isQEnd) return [
      e.name, e.region, e.currency,
      e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.nrr_bonus, e.currency),
      e.csat_score_pct ? e.csat_score_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.csat_bonus, e.currency),
      e.credits_used_pct ? e.credits_used_pct.toFixed(1) + '%' : '\u2014',
      fmtAmt(e.credits_bonus, e.currency),
      fmtAmt(e.accelerator_topup, e.currency),
      refComm,
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
    ];
    return [e.name, e.region, e.currency, e.referral_sao_count || 0, refComm,
      '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>'];
  });
  renderTable('cs-ms-table', heads, rows);
}

// ============================================================
// CS Quarterly Performance
// ============================================================
async function loadCSQuarterly() {
  const yr = document.getElementById('cs-qs-year').value;
  const qt = document.getElementById('cs-qs-quarter').value;
  const res  = await fetch('/api/cs_quarterly?year=' + yr + '&quarter=' + qt);
  const data = await res.json();
  const emps = data.employees || [];

  const totalBonus = emps.reduce((s,e) => s + e.total_commission, 0);
  const avgNrr     = emps.length ? emps.reduce((s,e) => s + e.nrr_pct, 0) / emps.length : 0;
  const avgCsat    = emps.length ? emps.reduce((s,e) => s + e.csat_score_pct, 0) / emps.length : 0;

  document.getElementById('cs-qs-kpis').innerHTML =
    kpiCard('Total Q Bonus', fmtAmt(totalBonus,'mixed'), 'All currencies') +
    kpiCard('Avg NRR', avgNrr.toFixed(1) + '%', 'Team average') +
    kpiCard('Avg CSAT', avgCsat.toFixed(1) + '%', 'Team average') +
    kpiCard('Advisors', emps.length, 'Q' + qt + ' ' + yr);

  const heads = ['Name','Q Target','NRR %','NRR Bonus','CSAT %','CSAT Bonus','Credits %','Credits Bonus','NRR Accel','Ref SAOs','Ref Comm','Total'];
  const rows = emps.map(e => [
    e.name,
    fmtAmt(e.quarterly_bonus_target, e.currency),
    e.nrr_pct ? e.nrr_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.nrr_bonus, e.currency),
    e.csat_score_pct ? e.csat_score_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.csat_bonus, e.currency),
    e.credits_used_pct ? e.credits_used_pct.toFixed(1) + '%' : '\u2014',
    fmtAmt(e.credits_bonus, e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    e.referral_sao_count || 0,
    fmtAmt((e.referral_sao_comm||0) + (e.referral_cw_comm||0), e.currency),
    '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
  ]);
  renderTable('cs-qs-table', heads, rows);

  // Progress bars per measure per person
  const barsEl = document.getElementById('cs-qs-bars');
  barsEl.innerHTML = emps.map(e => {
    const measures = [
      { label: 'NRR (50%)',           pct: e.nrr_pct,          target: 100, color: 'var(--accent)' },
      { label: 'CSAT (35%)',          pct: e.csat_score_pct,   target: 90,  color: '#7c3aed' },
      { label: 'Service Credits (15%)', pct: e.credits_used_pct, target: 100, color: '#0891b2' },
    ];
    const bars = measures.map(m => {
      const w   = Math.min(100, (m.pct / m.target) * 100);
      const col = m.pct >= m.target ? 'var(--green)' : m.color;
      return '<div style="margin-bottom:6px"><div style="display:flex;justify-content:space-between;font-size:11px;color:var(--dim);margin-bottom:2px"><span>' + m.label + '</span><span>' + m.pct.toFixed(1) + '%</span></div><div class="progress-wrap"><div class="progress-bar" style="width:' + w + '%;background:' + col + '"></div></div></div>';
    }).join('');
    return '<div style="margin-bottom:18px"><div style="font-size:13px;font-weight:600;margin-bottom:6px">' + e.name + '</div>' + bars + '</div>';
  }).join('');
}

// ============================================================
// CS Individual Detail
// ============================================================
async function loadCSIndividual() {
  const empId = document.getElementById('sd-emp').value;
  if (!empId) return;

  // Fetch all months for this employee via sdr_detail endpoint (works for CS too)
  const res  = await fetch('/api/sdr_detail?employee_id=' + empId);
  const data = await res.json();
  const {employee: emp, rows, ytd_commission} = data;
  const cur = emp.currency || 'EUR';

  document.getElementById('cs-ind-kpis').innerHTML =
    kpiCard('YTD Total', fmtAmt(ytd_commission, cur), emp.region || '') +
    kpiCard('Role', emp.title || '', emp.country || '');

  // Chart — total by month
  renderLine('cs-ind-chart', rows.map(r => r.month), rows.map(r => r.total_commission), 'Total Payout');

  // Table — show CS-relevant fields
  const heads = ['Month','Q','NRR Bonus','CSAT Bonus','Credits Bonus','NRR Accel','Ref Comm','Total'];
  const rowData = rows.map(r => [
    r.month, r.quarter,
    fmtAmt(r.nrr_bonus || 0, cur),
    fmtAmt(r.csat_bonus || 0, cur),
    fmtAmt(r.credits_bonus || 0, cur),
    fmtAmt(r.accelerator_topup || 0, cur),
    fmtAmt((r.referral_sao_comm||0) + (r.referral_cw_comm||0), cur),
    '<strong>' + fmtAmt(r.total_commission, cur) + '</strong>',
  ]);
  renderTable('cs-ind-table', heads, rowData);
}
"""


def build_html(role: str = "cs") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator — Normative (CS)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
