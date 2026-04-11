"""SDR-specific dashboard: tabs, nav links, and JS."""
from src.dashboards.base import assemble_html

_NAV_LINKS = """
    <div class="nav-section">Team</div>
    <div class="tab active" onclick="showTab('team-overview')">Team Overview</div>
    <div class="tab" onclick="showTab('monthly-summary')">Monthly Summary</div>
    <div class="tab" onclick="showTab('quarterly-summary')">Quarterly Summary</div>
    <div class="nav-section">Individual</div>
    <div class="tab" onclick="showTab('sdr-detail')">SDR Detail</div>
    <div class="tab" onclick="showTab('workings')">Commission Workings</div>
    <div class="tab" onclick="showTab('spif')">SPIFs</div>
    <div class="nav-section">Actions</div>
    <div class="tab" onclick="showTab('approve-send')">Approve &amp; Send</div>
    <div class="tab" onclick="showTab('payroll-summary')">Payroll Summary</div>
    <div class="tab" onclick="showTab('accrual-summary')">Finance Accruals</div>
    <div class="tab" onclick="showTab('accrual-vs-payroll')">Accruals vs Payroll</div>
    <div class="tab" onclick="showTab('data-view')">Data</div>
"""

_TABS_HTML = """
<!-- ============================================================ SDR TEAM OVERVIEW -->
<div id="tab-team-overview" class="tab-content active">
  <div class="page-title">Team Overview</div>
  <p class="page-sub">SDR commissions for the selected month</p>
  <div class="controls">
    <button class="btn" onclick="exportCSV('team-overview')">Export CSV</button>
  </div>
  <div class="kpi-grid" id="to-kpis"></div>
  <div class="two-col">
    <div class="panel"><h3>Commission by SDR</h3><canvas id="to-chart-comm" height="220"></canvas></div>
    <div class="panel"><h3>SAOs by SDR</h3><canvas id="to-chart-saos" height="220"></canvas></div>
  </div>
  <div class="panel">
    <h3>SDR Breakdown</h3>
    <div class="tbl-wrap"><table id="to-table"></table></div>
  </div>
</div>

<!-- ============================================================ SDR MONTHLY SUMMARY -->
<div id="tab-monthly-summary" class="tab-content">
  <div class="page-title">Monthly Summary</div>
  <p class="page-sub">All SDRs side-by-side for the selected month</p>
  <div class="panel">
    <div class="tbl-wrap"><table id="ms-table"></table></div>
  </div>
</div>

<!-- ============================================================ SDR QUARTERLY SUMMARY -->
<div id="tab-quarterly-summary" class="tab-content">
  <div class="page-title">Quarterly Summary</div>
  <p class="page-sub">SAO attainment and accelerator status by quarter</p>
  <div class="controls">
    <label>Year</label>
    <select id="qs-year" onchange="loadQuarterly()"></select>
    <label>Quarter</label>
    <select id="qs-quarter" onchange="loadQuarterly()">
      <option value="1">Q1</option><option value="2">Q2</option>
      <option value="3">Q3</option><option value="4" selected>Q4</option>
    </select>
  </div>
  <div class="kpi-grid" id="qs-kpis"></div>
  <div class="panel">
    <h3>SDR Progress to Target (9 SAOs / quarter)</h3>
    <div id="qs-progress"></div>
  </div>
  <div class="panel">
    <h3>Accelerator Detail</h3>
    <div class="tbl-wrap"><table id="qs-accel-table"></table></div>
  </div>
</div>

<!-- ============================================================ SDR DETAIL -->
<div id="tab-sdr-detail" class="tab-content">
  <div class="page-title">SDR Detail</div>
  <p class="page-sub">Month-by-month breakdown for an individual SDR</p>
  <div class="controls">
    <label>SDR</label>
    <select id="sd-emp" onchange="loadSDRDetail()"></select>
    <label>Month</label>
    <select id="sd-month" onchange="loadSDRDetail()">
      <option value="">All months</option>
    </select>
  </div>
  <div class="kpi-grid" id="sd-kpis"></div>
  <div class="panel"><h3>Monthly Commission Trend</h3><canvas id="sd-chart" height="60"></canvas></div>
  <div class="panel">
    <h3>Monthly Breakdown</h3>
    <div class="tbl-wrap"><table id="sd-table"></table></div>
  </div>
</div>
"""

_ROLE_JS = """
// ============================================================
// SDR — role init + tab dispatch
// ============================================================
async function onRoleInit() {
  // Populate individual month selector (with All option)
  const sdm = document.getElementById('sd-month');
  if (sdm) {
    months.slice().reverse().forEach(m => {
      const opt = document.createElement('option');
      opt.value = m; opt.text = fmtMonth(m);
      sdm.appendChild(opt);
    });
  }

  rebuildEmpDropdowns();

  // Year selectors
  const curYr = new Date().getFullYear();
  ['qs-year','ps-year','ac-year','avp-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  showTab('team-overview');
}

function loadTab(name) {
  if (name === 'team-overview')      loadTeamOverview();
  else if (name === 'monthly-summary')    loadMonthlySummary();
  else if (name === 'quarterly-summary')  loadQuarterly();
  else if (name === 'sdr-detail')         loadSDRDetail();
  else if (name === 'workings')           loadWorkings();
  else if (name === 'spif')               loadSPIFs();
  else if (name === 'approve-send')       loadApprovalStatus();
  else if (name === 'payroll-summary')    loadPayrollSummary();
  else if (name === 'accrual-summary')      loadAccrualSummary();
  else if (name === 'accrual-vs-payroll')   loadAccrualVsPayroll();
  else if (name === 'data-view')          loadDataView();
}

// ============================================================
// Team Overview
// ============================================================
async function loadTeamOverview() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/team_overview?month=' + month);
  const data  = await res.json();
  let {employees: emps, kpis} = data;
  emps = filterByRole(emps);

  const kpiEl = document.getElementById('to-kpis');
  kpiEl.innerHTML =
    kpiCard('Total Commission', fmtAmt(kpis.total_commission_eur,'EUR'), 'In EUR') +
    kpiCard('Total SAOs', kpis.total_saos, 'Outbound + Inbound') +
    kpiCard('Avg Attainment', kpis.avg_attainment + '%', 'vs monthly target (3 outbound SAOs)') +
    kpiCard('Active SDRs', kpis.num_sdrs, fmtMonth(month));

  const labels = emps.map(e => e.name.split(' ')[0]);
  renderBar('to-chart-comm', labels, emps.map(e => e.total_commission_eur), 'Commission (EUR)');
  renderBar('to-chart-saos', labels, emps.map(e => e.total_saos), 'SAOs', '#7c3aed');

  const heads = ['Name','Region','Out SAOs','In SAOs','Out CW','In CW','Accelerator','Total','Total (EUR)'];
  const rows  = emps.map(e => [
    e.name, e.region, e.outbound_saos, e.inbound_saos,
    fmtAmt(e.outbound_cw_comm, e.currency), fmtAmt(e.inbound_cw_comm, e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
    '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>'
  ]);
  renderTable('to-table', heads, rows);
}

// ============================================================
// Monthly Summary
// ============================================================
async function loadMonthlySummary() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch('/api/monthly_summary?month=' + month);
  let emps  = await res.json();
  emps = filterByRole(emps);
  const heads = ['Name','Region','Currency','Out SAOs','In SAOs','Attainment','Total Commission','Total (EUR)'];
  const rows  = emps.map(e => [
    e.name, e.region, e.currency, e.outbound_saos, e.inbound_saos,
    attainCell(e.attainment_pct),
    '<strong>' + fmtAmt(e.total_commission, e.currency) + '</strong>',
    '<strong>' + fmtAmt(e.total_commission_eur, 'EUR') + '</strong>'
  ]);
  renderTable('ms-table', heads, rows);
}

// ============================================================
// Quarterly Summary
// ============================================================
async function loadQuarterly() {
  const yr = document.getElementById('qs-year').value;
  const qt = document.getElementById('qs-quarter').value;
  const res  = await fetch('/api/quarterly_summary?year=' + yr + '&quarter=' + qt);
  const data = await res.json();
  let {employees: emps, accelerators: accels} = data;
  emps = filterByRole(emps);

  const kpiEl = document.getElementById('qs-kpis');
  const totalQ  = emps.reduce((s,e) => s + e.total_commission_eur, 0);
  const accelQ  = emps.reduce((s,e) => s + e.accelerator_topup, 0);
  const metCount = emps.filter(e => e.target_met).length;
  kpiEl.innerHTML =
    kpiCard('Q Commission', fmtAmt(totalQ,'EUR'), 'In EUR') +
    kpiCard('Accelerator Earned', fmtAmt(accelQ,'mixed'), 'Total top-ups') +
    kpiCard('Target Met', metCount + ' / ' + emps.length, '\u2265 9 SAOs in quarter');

  const prog = document.getElementById('qs-progress');
  prog.innerHTML = emps.map(e => {
    const pct = Math.min(100, (e.total_saos / 9) * 100);
    const exc = e.total_saos > 9;
    return '<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;margin-bottom:4px"><span style="font-size:13px;font-weight:600">' + e.name + '</span><span style="font-size:12px;color:var(--dim)">' + e.total_saos + ' / 9 SAOs' + (exc ? ' <span style="color:var(--green);font-weight:700">\u2713 Accelerator</span>' : '') + '</span></div><div class="progress-wrap"><div class="progress-bar' + (exc?' exceeded':'') + '" style="width:' + pct + '%"></div></div></div>';
  }).join('');

  if (accels && accels.length) {
    const heads = ['SDR','Total SAOs','Threshold','Excess Outbound','Top-up / SAO','Accelerator'];
    const rows  = accels.map(a => [
      a.employee_id, a.total_saos, a.threshold, a.excess_outbound,
      fmtAmt(a.topup_per_sao, a.currency),
      '<strong class="pos">' + fmtAmt(a.accelerator_topup, a.currency) + '</strong>'
    ]);
    renderTable('qs-accel-table', heads, rows);
  } else {
    document.getElementById('qs-accel-table').innerHTML = '<tr><td colspan="6" style="color:var(--dim);padding:12px">No accelerators triggered this quarter</td></tr>';
  }
}

// ============================================================
// SDR Detail
// ============================================================
async function loadSDRDetail() {
  const empId = document.getElementById('sd-emp').value;
  const month = document.getElementById('sd-month').value;
  const url   = '/api/sdr_detail?employee_id=' + empId + (month ? '&month=' + month : '');
  const res   = await fetch(url);
  const data  = await res.json();
  const {employee: emp, rows, ytd_commission, ytd_saos} = data;

  const cur = emp.currency || 'EUR';
  document.getElementById('sd-kpis').innerHTML =
    kpiCard('YTD Commission', fmtAmt(ytd_commission, cur), emp.region || '') +
    kpiCard('YTD SAOs', ytd_saos, 'Outbound + Inbound') +
    kpiCard('Role', emp.title || '', emp.country || '');

  renderLine('sd-chart', rows.map(r => r.month), rows.map(r => r.total_commission), 'Commission');

  const heads = ['Month','Q','Out SAOs','In SAOs','Out SAO $','In SAO $','CW Invoiced $','CW Forecast $','Accel','SPIF','Total'];
  const rowData = rows.map(r => {
    const cwInvoiced = (r.outbound_cw_comm||0) + (r.inbound_cw_comm||0);
    const cwForecast = (r.outbound_cw_forecast_comm||0) + (r.inbound_cw_forecast_comm||0);
    const spif = r.spif_amount || 0;
    return [
      r.month, r.quarter, r.outbound_saos, r.inbound_saos,
      fmtAmt(r.outbound_sao_comm, cur), fmtAmt(r.inbound_sao_comm, cur),
      cwInvoiced ? fmtAmt(cwInvoiced, cur) : '\u2014',
      cwForecast ? '<span style="color:var(--dim)">' + fmtAmt(cwForecast, cur) + '</span>' : '\u2014',
      fmtAmt(r.accelerator_topup, cur),
      spif ? '<span style="color:var(--purple);font-weight:700">' + fmtAmt(spif, cur) + '</span>' : '\u2014',
      '<strong>' + fmtAmt(r.total_commission, cur) + '</strong>'
    ];
  });
  renderTable('sd-table', heads, rowData);
}
"""


def build_html(role: str = "sdr") -> str:
    return assemble_html(
        role=role,
        title="Commission Calculator — Normative (SDR)",
        nav_links=_NAV_LINKS,
        role_tabs_html=_TABS_HTML,
        role_js=_ROLE_JS,
    )
