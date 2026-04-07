"""Commission Calculator — main entry point.

Runs a 5-stage data pipeline then serves a web dashboard on localhost.
Usage:
    python launch.py [--data-dir data] [--port 8050] [--no-browser]
"""

import argparse
import configparser
import json
import os
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import pandas as pd

from src.pipeline import run_pipeline, CommissionModel
from src.reports import (
    team_overview, sdr_detail, monthly_summary,
    quarterly_summary, commission_workings,
    employee_list, available_months,
    payroll_summary, accrual_summary,
)
from src.approval_state import ApprovalState
from src.helpers import clean_json
from src.pdf_generator import generate_statement
from src.email_sender import send_statement, build_cc_list, send_excel_report
from export_excel import export_payroll_workbook, export_accrual_workbook

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
MODEL: CommissionModel = None
APPROVAL: ApprovalState = None
SMTP_CONFIG: dict = {}
DATA_DIR: str = "data"
LOGO_PATH: str = "assets/normative_logo.png"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_config(config_file: str = "config.ini") -> dict:
    cfg = configparser.ConfigParser()
    if os.path.exists(config_file):
        cfg.read(config_file)
    smtp = {}
    if "smtp" in cfg:
        smtp = dict(cfg["smtp"])
    return smtp


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress request logging

    def _respond(self, data, status=200, content_type="application/json"):
        body = json.dumps(clean_json(data)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _respond_bytes(self, data: bytes, content_type: str, status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(data))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        def _p(key, default=None):
            vals = params.get(key, [])
            return vals[0] if vals else default

        if path == "/":
            html = _build_html()
            self._respond_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/months":
            self._respond(available_months(MODEL))
            return

        if path == "/api/employees":
            self._respond(employee_list(MODEL))
            return

        if path == "/api/team_overview":
            month = _parse_month(_p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else None))
            self._respond(team_overview(MODEL, month))
            return

        if path == "/api/sdr_detail":
            emp_id = _p("employee_id", "")
            month  = _parse_month(_p("month"))
            self._respond(sdr_detail(MODEL, emp_id, month))
            return

        if path == "/api/monthly_summary":
            month = _parse_month(_p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else None))
            self._respond(monthly_summary(MODEL, month))
            return

        if path == "/api/quarterly_summary":
            yr = int(_p("year", pd.Timestamp.now().year))
            qt = int(_p("quarter", 1))
            self._respond(quarterly_summary(MODEL, yr, qt))
            return

        if path == "/api/commission_workings":
            emp_id = _p("employee_id", "")
            month  = _parse_month(_p("month"))
            self._respond(commission_workings(MODEL, emp_id, month))
            return

        if path == "/api/spifs":
            if MODEL.spif_awards.empty:
                self._respond([])
            else:
                rows = []
                for _, r in MODEL.spif_awards.iterrows():
                    pm = r["payment_month"]
                    rows.append({
                        "employee_id":   r["employee_id"],
                        "name":          r["name"],
                        "spif_id":       r["spif_id"],
                        "description":   r["description"],
                        "amount":        float(r["amount"]),
                        "currency":      r["currency"],
                        "payment_month": pm.strftime("%Y-%m") if hasattr(pm, "strftime") else str(pm),
                        "sao_date":      r.get("sao_date") or "",
                        "close_date":    r.get("close_date") or "",
                        "days_to_close": int(r["days_to_close"]) if r.get("days_to_close") is not None and str(r.get("days_to_close")) not in ("None","nan","") else None,
                        "opportunity":   r.get("opportunity") or "",
                    })
                self._respond(rows)
            return

        if path == "/api/approval_status":
            month_str = _p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else "")
            states    = APPROVAL.get_all_for_month(month_str)
            # Enrich with employee names
            emp_map   = {r["employee_id"]: r["name"] for r in employee_list(MODEL)}
            sdrs      = employee_list(MODEL)
            result    = []
            for emp in sdrs:
                eid  = emp["employee_id"]
                st   = APPROVAL.get(eid, month_str)
                # Check stale
                det = MODEL.commission_detail[
                    (MODEL.commission_detail["employee_id"] == eid) &
                    (MODEL.commission_detail["month"] == _parse_month(month_str))
                ]
                total = float(det["total_commission"].iloc[0]) if not det.empty else 0
                APPROVAL.check_and_reset_stale(eid, month_str, total)
                st = APPROVAL.get(eid, month_str)
                result.append({**emp, **st, "total_commission": total})
            self._respond(result)
            return

        if path == "/api/preview_pdf":
            emp_id    = _p("employee_id", "")
            month_str = _p("month", "")
            pdf_path  = _make_pdf(emp_id, month_str)
            if pdf_path and os.path.exists(pdf_path):
                with open(pdf_path, "rb") as f:
                    self._respond_bytes(f.read(), "application/pdf")
            else:
                self._respond({"error": "Could not generate PDF"}, 500)
            return

        if path == "/api/payroll_summary":
            yr = int(_p("year", pd.Timestamp.now().year))
            self._respond(payroll_summary(MODEL, yr))
            return

        if path == "/api/accrual_summary":
            yr = int(_p("year", pd.Timestamp.now().year))
            self._respond(accrual_summary(MODEL, yr))
            return

        if path == "/api/export_payroll":
            yr = int(_p("year", pd.Timestamp.now().year))
            xls = export_payroll_workbook(MODEL, yr)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="Payroll_Summary_{yr}.xlsx"')
            self.send_header("Content-Length", len(xls))
            self.end_headers()
            self.wfile.write(xls)
            return

        if path == "/api/export_accrual":
            yr = int(_p("year", pd.Timestamp.now().year))
            xls = export_accrual_workbook(MODEL, yr)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", f'attachment; filename="Accrual_Summary_{yr}.xlsx"')
            self.send_header("Content-Length", len(xls))
            self.end_headers()
            self.wfile.write(xls)
            return

        self._respond({"error": "Not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        body   = self._read_body()

        if path == "/api/approve":
            emp_id    = body.get("employee_id", "")
            month_str = body.get("month", "")
            det = MODEL.commission_detail[
                (MODEL.commission_detail["employee_id"] == emp_id) &
                (MODEL.commission_detail["month"] == _parse_month(month_str))
            ]
            total = float(det["total_commission"].iloc[0]) if not det.empty else 0
            APPROVAL.approve(emp_id, month_str, total)
            self._respond({"ok": True, "status": "approved"})
            return

        if path == "/api/unapprove":
            emp_id    = body.get("employee_id", "")
            month_str = body.get("month", "")
            APPROVAL.unapprove(emp_id, month_str)
            self._respond({"ok": True, "status": "pending"})
            return

        if path == "/api/send_approved":
            month_str  = body.get("month", "")
            approved   = APPROVAL.get_approved_unsent(month_str)
            sent_count = 0
            errors     = []

            for emp_id in approved:
                pdf_path = _make_pdf(emp_id, month_str)
                if not pdf_path:
                    errors.append({"employee_id": emp_id, "error": "PDF generation failed"})
                    continue

                emp_row = MODEL.employees[MODEL.employees["employee_id"] == emp_id]
                if emp_row.empty:
                    continue
                emp     = emp_row.iloc[0].to_dict()
                det     = MODEL.commission_detail[
                    (MODEL.commission_detail["employee_id"] == emp_id) &
                    (MODEL.commission_detail["month"] == _parse_month(month_str))
                ]
                total    = float(det["total_commission"].iloc[0]) if not det.empty else 0
                currency = emp.get("currency", "EUR")
                ts       = _parse_month(month_str)
                m_label  = ts.strftime("%B %Y") if ts else month_str
                cc       = build_cc_list(MODEL.employees, emp_id)

                result = send_statement(SMTP_CONFIG, emp, m_label, total, currency, pdf_path, cc)
                if result["success"]:
                    APPROVAL.mark_sent(emp_id, month_str)
                    sent_count += 1
                else:
                    errors.append({"employee_id": emp_id, "error": result["error"]})

            self._respond({"sent": sent_count, "errors": errors})
            return

        if path == "/api/send_payroll":
            yr       = int(body.get("year", pd.Timestamp.now().year))
            to_email = body.get("email", "")
            if not to_email:
                self._respond({"error": "No recipient email provided"}, 400)
                return
            xls    = export_payroll_workbook(MODEL, yr)
            result = send_excel_report(
                SMTP_CONFIG, to_email,
                f"Commission & Bonus Payroll Summary — FY{yr}",
                f"Please find attached the commission & bonus payroll summary for FY{yr}.\n\nNormative — Commission & Incentive Team",
                xls, f"Payroll_Summary_{yr}.xlsx",
            )
            self._respond(result)
            return

        if path == "/api/send_accrual":
            yr       = int(body.get("year", pd.Timestamp.now().year))
            to_email = body.get("email", "")
            if not to_email:
                self._respond({"error": "No recipient email provided"}, 400)
                return
            xls    = export_accrual_workbook(MODEL, yr)
            result = send_excel_report(
                SMTP_CONFIG, to_email,
                f"Commission & Bonus Accrual Summary — FY{yr}",
                f"Please find attached the commission & bonus accrual summary for FY{yr}.\n\nNormative — Commission & Incentive Team",
                xls, f"Accrual_Summary_{yr}.xlsx",
            )
            self._respond(result)
            return

        self._respond({"error": "Not found"}, 404)


# ---------------------------------------------------------------------------
# PDF helper
# ---------------------------------------------------------------------------
def _make_pdf(emp_id: str, month_str: str) -> str | None:
    try:
        emp_row = MODEL.employees[MODEL.employees["employee_id"] == emp_id]
        if emp_row.empty:
            return None
        emp = emp_row.iloc[0].to_dict()

        month_ts = _parse_month(month_str)
        if month_ts is None:
            return None

        det = MODEL.commission_detail[
            (MODEL.commission_detail["employee_id"] == emp_id) &
            (MODEL.commission_detail["month"] == month_ts)
        ]
        summary = det.iloc[0].to_dict() if not det.empty else {}
        summary = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                   for k, v in summary.items()}

        wk = commission_workings(MODEL, emp_id, month_ts)
        rows = wk["rows"]

        acc = None
        if not MODEL.accelerators.empty:
            q    = (month_ts.month - 1) // 3 + 1
            a_df = MODEL.accelerators[
                (MODEL.accelerators["employee_id"] == emp_id) &
                (MODEL.accelerators["year"] == month_ts.year) &
                (MODEL.accelerators["quarter"] == q)
            ]
            acc = a_df.iloc[0].to_dict() if not a_df.empty else None

        out_dir = os.path.join("output", "statements")
        os.makedirs(out_dir, exist_ok=True)
        pdf_path = os.path.join(out_dir, f"{emp_id}_{month_str}.pdf")

        logo = LOGO_PATH if os.path.exists(LOGO_PATH) else None
        generate_statement(emp, month_str, summary, rows, acc, pdf_path, logo)
        return pdf_path
    except Exception as e:
        print(f"[PDF] Error generating for {emp_id} {month_str}: {e}")
        return None


def _parse_month(s: str | None) -> pd.Timestamp | None:
    if not s:
        return None
    try:
        return pd.Timestamp(s)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Embedded HTML dashboard
# ---------------------------------------------------------------------------
def _build_html() -> str:
    return r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Commission Calculator — Normative</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Space Grotesk',system-ui,sans-serif;display:flex;height:100vh;overflow:hidden;background:#fff;color:#000}
:root{--bg:#FFFFFF;--card:#F5F5F5;--border:#E0E0E0;--text:#000;--dim:#595959;--accent:#FF9178;--green:#16a34a;--red:#dc2626;--orange:#ea580c;--purple:#7c3aed;--cyan:#0891b2}

/* NAV */
nav{width:220px;min-width:220px;background:#FAFAFA;border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto}
nav .logo{padding:20px;border-bottom:1px solid var(--border)}
nav .logo small{font-size:8px;font-weight:700;letter-spacing:2px;color:var(--dim);text-transform:uppercase}
nav .logo h1{font-size:17px;font-weight:800;margin-top:2px}
nav .tabs{flex:1;padding:12px 0}
nav .tab{padding:9px 20px;cursor:pointer;font-size:13px;color:var(--dim);border-left:2px solid transparent;transition:all .12s}
nav .tab:hover{color:var(--text)}
nav .tab.active{color:#000;font-weight:700;background:linear-gradient(90deg,rgba(255,145,120,.18),transparent);border-left-color:var(--accent)}
nav .nav-section{font-size:9px;font-weight:700;letter-spacing:1.5px;color:var(--dim);text-transform:uppercase;padding:16px 20px 4px}
nav .global-filter{padding:12px 20px;border-bottom:1px solid var(--border)}
nav .global-filter label{display:block;font-size:9px;font-weight:700;letter-spacing:1.5px;color:var(--dim);text-transform:uppercase;margin-bottom:6px}
nav .global-filter select{width:100%;font-size:12px;padding:6px 10px}

/* MAIN */
main{flex:1;overflow-y:auto;padding:24px 32px}
.tab-content{display:none}.tab-content.active{display:block}
.page-title{font-size:22px;font-weight:800;margin-bottom:4px}
.page-sub{font-size:13px;color:var(--dim);margin-bottom:20px}

/* CONTROLS */
.controls{display:flex;gap:12px;align-items:center;margin-bottom:20px;flex-wrap:wrap}
.controls label{font-size:11px;color:var(--dim);font-weight:600;text-transform:uppercase;letter-spacing:.5px;margin-right:4px}
select,input[type=text]{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 14px;color:var(--text);font-size:13px;font-family:inherit;outline:none;cursor:pointer}
select:focus,input:focus{border-color:var(--accent)}

/* KPI CARDS */
.kpi-grid{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.kpi-card{background:var(--card);border-radius:12px;padding:20px 24px;border:1px solid var(--border);flex:1;min-width:170px}
.kpi-card .label{font-size:11px;color:var(--dim);font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:6px}
.kpi-card .value{font-size:28px;font-weight:800}
.kpi-card .sub{font-size:12px;color:var(--dim);margin-top:4px}

/* PANEL */
.panel{background:var(--card);border-radius:12px;padding:20px;border:1px solid var(--border);margin-bottom:20px}
.panel h3{font-size:14px;font-weight:700;margin-bottom:16px}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px}

/* TABLES */
.tbl-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:10px 12px;text-align:right;color:var(--dim);font-size:10px;font-weight:600;letter-spacing:.5px;text-transform:uppercase;border-bottom:2px solid var(--border);position:sticky;top:0;background:var(--bg)}
th:first-child{text-align:left}
td{padding:6px 12px;text-align:right;border-bottom:1px solid var(--border)}
td:first-child{text-align:left;font-weight:500}
td.neg{color:var(--red)}td.pos{color:var(--green)}
tr.total td{font-weight:700;background:#EEE;border-top:1px solid var(--border)}
tr.clickable{cursor:pointer;transition:background .1s}
tr.clickable:hover{background:rgba(255,145,120,.1)}

/* BUTTONS */
.btn{background:var(--card);border:1px solid var(--border);border-radius:6px;padding:6px 14px;color:var(--text);font-size:11px;font-family:inherit;cursor:pointer;transition:all .12s;font-weight:600}
.btn:hover{background:var(--accent);color:#000;border-color:var(--accent)}
.btn.primary{background:var(--accent);color:#000;border-color:var(--accent)}
.btn.primary:hover{background:#ff7a5a}
.btn.danger{color:var(--red);border-color:var(--red)}
.btn.danger:hover{background:var(--red);color:#fff}
.btn:disabled{opacity:.4;cursor:not-allowed}

/* BADGES */
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.5px}
.badge.pending{background:#eee;color:var(--dim)}
.badge.approved{background:#fff3e8;color:var(--orange);border:1px solid var(--orange)}
.badge.sent{background:#ecfdf5;color:var(--green);border:1px solid var(--green)}

/* PROGRESS BAR */
.progress-wrap{background:var(--border);border-radius:20px;height:8px;margin-top:6px}
.progress-bar{height:8px;border-radius:20px;background:var(--accent);transition:width .3s}
.progress-bar.exceeded{background:var(--green)}

/* TOAST */
#toast{position:fixed;bottom:24px;right:24px;background:#000;color:#fff;padding:12px 20px;border-radius:10px;font-size:13px;font-weight:600;opacity:0;transition:opacity .3s;z-index:9999;pointer-events:none}
#toast.show{opacity:1}

/* MODAL */
.modal-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.4);z-index:1000;align-items:center;justify-content:center}
.modal-overlay.open{display:flex}
.modal{background:#fff;border:1px solid var(--border);border-radius:14px;padding:28px;max-width:640px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 8px 40px rgba(0,0,0,.15)}
.modal h3{font-size:16px;font-weight:700;margin-bottom:4px;color:var(--accent)}
.modal .modal-sub{font-size:12px;color:var(--dim);margin-bottom:16px}
.modal .close-btn{margin-top:16px;background:var(--card);border:1px solid var(--border);color:var(--text);padding:8px 20px;border-radius:8px;cursor:pointer;font-family:inherit;font-size:13px}
.modal .close-btn:hover{background:var(--accent);color:#000;border-color:var(--accent)}

/* SEARCH */
.search{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:8px 14px;color:var(--text);font-size:13px;width:280px;outline:none;margin-bottom:12px;font-family:inherit}
.search:focus{border-color:var(--accent)}

/* ATTAINMENT CELL */
.attain-wrap{display:flex;align-items:center;gap:8px}
.attain-bar-bg{background:var(--border);border-radius:10px;height:6px;width:60px}
.attain-bar{height:6px;border-radius:10px;background:var(--accent)}
.attain-bar.ok{background:var(--green)}

@media(max-width:900px){.two-col{grid-template-columns:1fr}.kpi-grid{flex-direction:column}}
</style>
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
  <div class="tabs">
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
    <div class="tab" onclick="showTab('data-view')">Data</div>
  </div>
</nav>

<main>

<!-- ============================================================ TEAM OVERVIEW -->
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

<!-- ============================================================ MONTHLY SUMMARY -->
<div id="tab-monthly-summary" class="tab-content">
  <div class="page-title">Monthly Summary</div>
  <p class="page-sub">All SDRs side-by-side for the selected month</p>
  <div class="panel">
    <div class="tbl-wrap"><table id="ms-table"></table></div>
  </div>
</div>

<!-- ============================================================ QUARTERLY SUMMARY -->
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

<!-- ============================================================ WORKINGS -->
<div id="tab-workings" class="tab-content">
  <div class="page-title">Commission Workings</div>
  <p class="page-sub">Row-level audit trail for payroll verification</p>
  <div class="controls">
    <label>SDR</label>
    <select id="wk-emp" onchange="loadWorkings()"></select>
    <button class="btn" onclick="previewPDF()">Preview PDF</button>
  </div>
  <div class="kpi-grid" id="wk-kpis"></div>
  <div class="panel">
    <h3>Activity Detail</h3>
    <div class="tbl-wrap"><table id="wk-table"></table></div>
  </div>
</div>

<!-- ============================================================ SPIFs -->
<div id="tab-spif" class="tab-content">
  <div class="page-title">SPIFs</div>
  <p class="page-sub">Sales Performance Incentive Fund awards</p>
  <div id="spif-body"></div>
</div>

<!-- ============================================================ APPROVE & SEND -->
<div id="tab-approve-send" class="tab-content">
  <div class="page-title">Approve &amp; Send</div>
  <p class="page-sub">Review, approve and email commission statements</p>
  <div class="controls">
    <button class="btn primary" onclick="sendAllApproved()" id="as-send-btn">Send All Approved</button>
    <span id="as-counts" style="font-size:12px;color:var(--dim)"></span>
  </div>
  <div class="panel">
    <div class="tbl-wrap"><table id="as-table"></table></div>
  </div>
</div>

<!-- ============================================================ PAYROLL SUMMARY -->
<div id="tab-payroll-summary" class="tab-content">
  <div class="page-title">Payroll Summary</div>
  <p class="page-sub">Monthly commission per employee — send to payroll for processing</p>
  <div class="controls">
    <label>Year</label>
    <select id="ps-year" onchange="loadPayrollSummary()"></select>
    <button class="btn" onclick="exportPayroll()">Export Excel</button>
    <input type="email" class="search" id="ps-email" placeholder="payroll@company.com" style="width:220px;margin-bottom:0">
    <button class="btn primary" onclick="sendPayroll()">Send to Payroll</button>
  </div>
  <div id="ps-body"></div>
</div>

<!-- ============================================================ FINANCE ACCRUALS -->
<div id="tab-accrual-summary" class="tab-content">
  <div class="page-title">Finance Accruals</div>
  <p class="page-sub">Department-level commission accruals in EUR — send to finance</p>
  <div class="controls">
    <label>Year</label>
    <select id="ac-year" onchange="loadAccrualSummary()"></select>
    <button class="btn" onclick="exportAccrual()">Export Excel</button>
    <input type="email" class="search" id="ac-email" placeholder="finance@company.com" style="width:220px;margin-bottom:0">
    <button class="btn primary" onclick="sendAccrual()">Send to Finance</button>
  </div>
  <div id="ac-body"></div>
</div>

<!-- ============================================================ DATA VIEW -->
<div id="tab-data-view" class="tab-content">
  <div class="page-title">Data</div>
  <p class="page-sub">Raw data loaded from CSV files (read-only)</p>
  <div class="controls">
    <label>Table</label>
    <select id="dv-table" onchange="loadDataView()">
      <option value="activities">SDR Activities</option>
      <option value="closed_won">Closed Won</option>
      <option value="employees">Employees</option>
    </select>
    <input type="text" class="search" id="dv-search" placeholder="Search..." oninput="filterDataView()">
  </div>
  <div class="panel">
    <div class="tbl-wrap"><table id="dv-table-el"></table></div>
  </div>
</div>

</main>

<!-- MODAL for PDF preview -->
<div class="modal-overlay" id="pdf-modal">
  <div class="modal">
    <h3>PDF Preview</h3>
    <p class="modal-sub">Opens in a new browser tab.</p>
    <button class="close-btn" onclick="closeModal('pdf-modal')">Close</button>
  </div>
</div>

<div id="toast"></div>

<script>
// ============================================================
// State
// ============================================================
let months = [], employees = [], activeTab = 'team-overview';
let charts = {};
let dvData = [], dvHeaders = [];

// ============================================================
// Init
// ============================================================
async function init() {
  const [mRes, eRes] = await Promise.all([fetch('/api/months'), fetch('/api/employees')]);
  months = await mRes.json();
  employees = await eRes.json();

  // Populate global month selector
  const gmEl = document.getElementById('global-month');
  months.slice().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.text  = fmtMonth(m);
    gmEl.appendChild(opt);
  });

  // Populate SDR month for sd-month (with "All" option)
  const sdm = document.getElementById('sd-month');
  months.slice().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m; opt.text = fmtMonth(m);
    sdm.appendChild(opt);
  });

  // Populate employee selectors
  ['sd-emp','wk-emp'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    employees.forEach(e => {
      const opt = document.createElement('option');
      opt.value = e.employee_id; opt.text = e.name;
      el.appendChild(opt);
    });
  });

  // Year selectors (quarterly + payroll + accrual)
  const curYr = new Date().getFullYear();
  ['qs-year','ps-year','ac-year'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    [curYr-1, curYr, curYr+1].forEach(y => {
      const opt = document.createElement('option');
      opt.value = y; opt.text = y;
      if (y === curYr) opt.selected = true;
      el.appendChild(opt);
    });
  });

  await loadTeamOverview();
}

// ============================================================
// Global month change — reload the active month-based tab
// ============================================================
function onGlobalMonthChange() {
  if (activeTab === 'team-overview')   loadTeamOverview();
  else if (activeTab === 'monthly-summary') loadMonthlySummary();
  else if (activeTab === 'workings')   loadWorkings();
  else if (activeTab === 'approve-send') loadApprovalStatus();
}

// ============================================================
// Tab navigation
// ============================================================
function showTab(name) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  const tabs = document.querySelectorAll('.tab');
  tabs.forEach(t => { if (t.getAttribute('onclick') && t.getAttribute('onclick').includes("'" + name + "'")) t.classList.add('active'); });
  activeTab = name;

  if (name === 'team-overview')    loadTeamOverview();
  if (name === 'monthly-summary')  loadMonthlySummary();
  if (name === 'quarterly-summary') loadQuarterly();
  if (name === 'sdr-detail')       loadSDRDetail();
  if (name === 'workings')         loadWorkings();
  if (name === 'spif')             loadSPIFs();
  if (name === 'approve-send')     loadApprovalStatus();
  if (name === 'payroll-summary')  loadPayrollSummary();
  if (name === 'accrual-summary')  loadAccrualSummary();
  if (name === 'data-view')        loadDataView();
}

// ============================================================
// Team Overview
// ============================================================
async function loadTeamOverview() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch(`/api/team_overview?month=${month}`);
  const data  = await res.json();
  const {employees: emps, kpis} = data;

  // KPI cards
  const kpiEl = document.getElementById('to-kpis');
  kpiEl.innerHTML = `
    ${kpiCard('Total Commission', fmtAmt(kpis.total_commission_eur,'EUR'), 'In EUR')}
    ${kpiCard('Total SAOs', kpis.total_saos, 'Outbound + Inbound')}
    ${kpiCard('Avg Attainment', kpis.avg_attainment + '%', 'vs monthly target (3 outbound SAOs)')}
    ${kpiCard('Active SDRs', kpis.num_sdrs, fmtMonth(month))}
  `;

  // Charts
  const labels = emps.map(e => e.name.split(' ')[0]);
  const comms  = emps.map(e => e.total_commission_eur);
  const saos   = emps.map(e => e.total_saos);
  renderBar('to-chart-comm', labels, comms, 'Commission (EUR)');
  renderBar('to-chart-saos', labels, saos, 'SAOs', '#7c3aed');

  // Table
  const heads = ['Name','Region','Out SAOs','In SAOs','Out CW','In CW','Accelerator','Total','Total (EUR)'];
  const rows  = emps.map(e => [
    e.name, e.region,
    e.outbound_saos, e.inbound_saos,
    fmtAmt(e.outbound_cw_comm, e.currency), fmtAmt(e.inbound_cw_comm, e.currency),
    fmtAmt(e.accelerator_topup, e.currency),
    `<strong>${fmtAmt(e.total_commission, e.currency)}</strong>`,
    `<strong>${fmtAmt(e.total_commission_eur, 'EUR')}</strong>`
  ]);
  renderTable('to-table', heads, rows);
}

// ============================================================
// Monthly Summary
// ============================================================
async function loadMonthlySummary() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch(`/api/monthly_summary?month=${month}`);
  const emps  = await res.json();
  const heads = ['Name','Region','Currency','Out SAOs','In SAOs','Attainment','Total Commission','Total (EUR)'];
  const rows  = emps.map(e => [
    e.name, e.region, e.currency,
    e.outbound_saos, e.inbound_saos,
    attainCell(e.attainment_pct),
    `<strong>${fmtAmt(e.total_commission, e.currency)}</strong>`,
    `<strong>${fmtAmt(e.total_commission_eur, 'EUR')}</strong>`
  ]);
  renderTable('ms-table', heads, rows);
}

// ============================================================
// Quarterly Summary
// ============================================================
async function loadQuarterly() {
  const yr = document.getElementById('qs-year').value;
  const qt = document.getElementById('qs-quarter').value;
  const res  = await fetch(`/api/quarterly_summary?year=${yr}&quarter=${qt}`);
  const data = await res.json();
  const {employees: emps, accelerators: accels} = data;

  const kpiEl = document.getElementById('qs-kpis');
  const totalQ = emps.reduce((s,e) => s + e.total_commission_eur, 0);
  const accelQ = emps.reduce((s,e) => s + e.accelerator_topup, 0);
  const metCount = emps.filter(e => e.target_met).length;
  kpiEl.innerHTML = `
    ${kpiCard('Q Commission', fmtAmt(totalQ,'EUR'), 'In EUR')}
    ${kpiCard('Accelerator Earned', fmtAmt(accelQ,'mixed'), 'Total top-ups')}
    ${kpiCard('Target Met', metCount + ' / ' + emps.length, '≥ 9 SAOs in quarter')}
  `;

  const prog = document.getElementById('qs-progress');
  prog.innerHTML = emps.map(e => {
    const pct   = Math.min(100, (e.total_saos / 9) * 100);
    const exc   = e.total_saos > 9;
    return `<div style="margin-bottom:14px">
      <div style="display:flex;justify-content:space-between;margin-bottom:4px">
        <span style="font-size:13px;font-weight:600">${e.name}</span>
        <span style="font-size:12px;color:var(--dim)">${e.total_saos} / 9 SAOs${exc?' <span style="color:var(--green);font-weight:700">✓ Accelerator</span>':''}</span>
      </div>
      <div class="progress-wrap"><div class="progress-bar${exc?' exceeded':''}" style="width:${pct}%"></div></div>
    </div>`;
  }).join('');

  // Accelerator table
  if (accels && accels.length) {
    const heads = ['SDR','Total SAOs','Threshold','Excess Outbound','Top-up / SAO','Accelerator'];
    const rows  = accels.map(a => [
      a.employee_id, a.total_saos, a.threshold,
      a.excess_outbound, fmtAmt(a.topup_per_sao, a.currency),
      `<strong class="pos">${fmtAmt(a.accelerator_topup, a.currency)}</strong>`
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
  const url   = `/api/sdr_detail?employee_id=${empId}${month ? '&month='+month : ''}`;
  const res   = await fetch(url);
  const data  = await res.json();
  const {employee: emp, rows, ytd_commission, ytd_saos} = data;

  const cur = emp.currency || 'EUR';
  const kpiEl = document.getElementById('sd-kpis');
  kpiEl.innerHTML = `
    ${kpiCard('YTD Commission', fmtAmt(ytd_commission, cur), emp.region || '')}
    ${kpiCard('YTD SAOs', ytd_saos, 'Outbound + Inbound')}
    ${kpiCard('Role', emp.title || '', emp.country || '')}
  `;

  // Chart
  const mLabels = rows.map(r => r.month);
  const mComms  = rows.map(r => r.total_commission);
  renderLine('sd-chart', mLabels, mComms, 'Commission');

  // Table
  const heads = ['Month','Q','Out SAOs','In SAOs','Out SAO $','In SAO $','CW Invoiced $','CW Forecast $','Accel','SPIF','Total'];
  const rowData = rows.map(r => {
    const cwInvoiced = (r.outbound_cw_comm||0) + (r.inbound_cw_comm||0);
    const cwForecast = (r.outbound_cw_forecast_comm||0) + (r.inbound_cw_forecast_comm||0);
    const spif = r.spif_amount || 0;
    return [
      r.month, r.quarter,
      r.outbound_saos, r.inbound_saos,
      fmtAmt(r.outbound_sao_comm, cur), fmtAmt(r.inbound_sao_comm, cur),
      cwInvoiced ? fmtAmt(cwInvoiced, cur) : '—',
      cwForecast ? `<span style="color:var(--dim)">${fmtAmt(cwForecast, cur)}</span>` : '—',
      fmtAmt(r.accelerator_topup, cur),
      spif ? `<span style="color:var(--purple);font-weight:700">${fmtAmt(spif, cur)}</span>` : '—',
      `<strong>${fmtAmt(r.total_commission, cur)}</strong>`
    ];
  });
  renderTable('sd-table', heads, rowData);
}

// ============================================================
// Workings
// ============================================================
async function loadWorkings() {
  const empId = document.getElementById('wk-emp').value;
  const month = document.getElementById('global-month').value;
  if (!empId || !month) return;
  const res  = await fetch(`/api/commission_workings?employee_id=${empId}&month=${month}`);
  const data = await res.json();
  const {rows, summary} = data;
  const cur = summary.currency || 'EUR';

  const kpiEl = document.getElementById('wk-kpis');
  const fcastComm = (summary.outbound_cw_forecast_comm||0) + (summary.inbound_cw_forecast_comm||0);
  const spifAmt   = rows.filter(r => r.type === 'SPIF').reduce((s,r) => s + r.commission, 0);
  kpiEl.innerHTML = `
    ${kpiCard('Confirmed Commission', fmtAmt(summary.total_commission, cur), fmtMonth(month))}
    ${kpiCard('Outbound SAOs', summary.outbound_sao_count || 0, fmtAmt(summary.outbound_sao_comm||0,cur))}
    ${kpiCard('Inbound SAOs', summary.inbound_sao_count || 0, fmtAmt(summary.inbound_sao_comm||0,cur))}
    ${kpiCard('Accelerator', fmtAmt(summary.accelerator_topup||0,cur), 'Quarterly top-up')}
    ${spifAmt   > 0 ? kpiCard('SPIF', fmtAmt(spifAmt, cur), 'Included in total') : ''}
    ${fcastComm > 0 ? kpiCard('Forecast CW', fmtAmt(fcastComm, cur), 'Pending invoice') : ''}
  `;

  const heads = ['Date','Opportunity / Invoice','Direction','Category','Rate / Formula','Commission'];
  const rowData = rows.map(r => {
    const isSpif     = r.type === 'SPIF';
    const isForecast = r.is_forecast;
    const commStr = r.commission < 0
      ? `<span style="color:var(--red)">${fmtAmt(r.commission, cur)}</span>`
      : isSpif
        ? `<span style="color:var(--purple);font-weight:700">${fmtAmt(r.commission, cur)}</span>`
        : isForecast
          ? `<span style="color:var(--dim)">${fmtAmt(r.commission, cur)} <em style="font-size:10px">(forecast)</em></span>`
          : `<span style="color:var(--green)">${fmtAmt(r.commission, cur)}</span>`;
    // For invoice/CW rows show opp name; for SAO rows show opportunity_id; SPIF shows description
    const displayName = isSpif
      ? `<span style="color:var(--purple)">${r.opportunity_name || r.opportunity_id}</span>`
      : (r.type === 'SAO') ? r.opportunity_id : (r.opportunity_name || r.opportunity_id);
    const oppLabel = r.document_number
      ? `${displayName}<br><span style="font-size:10px;color:var(--dim)">${r.document_number}</span>`
      : displayName;
    const typeLabel = isSpif
      ? `<span style="background:var(--purple);color:#fff;font-size:10px;padding:2px 6px;border-radius:4px;font-weight:700">SPIF</span>`
      : r.type;
    return [
      r.date, oppLabel,
      r.sao_type ? r.sao_type.charAt(0).toUpperCase()+r.sao_type.slice(1) : '',
      typeLabel, isSpif ? '' : r.rate_desc, commStr
    ];
  });
  renderTable('wk-table', heads, rowData);
}

// ============================================================
// SPIFs
// ============================================================
async function loadSPIFs() {
  const res  = await fetch('/api/spifs');
  const data = await res.json();
  const el   = document.getElementById('spif-body');

  if (!data.length) {
    el.innerHTML = '<div class="panel" style="color:var(--dim);font-size:13px">' +
      'No SPIF awards calculated yet.<br><br>' +
      '<strong>AE SPIF:</strong> Fill in <code>data/spif_targets.csv</code> with each AE\'s Q1 target (q1_target_eur) to activate.<br>' +
      '<strong>SDR SPIF:</strong> Awarded automatically for Q1 deals closing within 8 weeks of SAO.' +
      '</div>';
    return;
  }

  // Group by spif_id
  const bySpif = {};
  data.forEach(r => {
    if (!bySpif[r.spif_id]) bySpif[r.spif_id] = [];
    bySpif[r.spif_id].push(r);
  });

  let html = '';

  const spifLabels = {
    'sdr_q1_2026_8week':          'SDR Q1 2026 — Closed Won within 8 weeks of SAO',
    'ae_q1_2026_first_to_target': 'AE Q1 2026 — First to Target',
  };

  for (const [spifId, rows] of Object.entries(bySpif)) {
    const label = spifLabels[spifId] || spifId;
    const totalByCur = {};
    rows.forEach(r => { totalByCur[r.currency] = (totalByCur[r.currency]||0) + r.amount; });
    const totalStr = Object.entries(totalByCur).map(([c,a]) => fmtAmt(a,c)).join(' + ');

    html += `<div class="panel" style="margin-bottom:16px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
        <h3>${label}</h3>
        <span style="font-size:13px;color:var(--dim)">Total payout: <strong>${totalStr}</strong></span>
      </div>`;

    if (spifId === 'sdr_q1_2026_8week') {
      const heads = ['SDR','Opportunity','SAO Date','Close Date','Days','Payment Month','Award'];
      const rowData = rows.map(r => [
        r.name,
        `<span style="font-size:12px">${r.opportunity}</span>`,
        r.sao_date, r.close_date,
        `<span style="color:${r.days_to_close<=28?'var(--green)':r.days_to_close<=42?'var(--orange)':'var(--dim)'}">${r.days_to_close}d</span>`,
        r.payment_month,
        `<strong style="color:var(--green)">${fmtAmt(r.amount, r.currency)}</strong>`,
      ]);
      html += tableHtml(heads, rowData);
    } else {
      // AE winner
      const r = rows[0];
      html += `<div class="kpi-grid">
        ${kpiCard('Winner 🏆', r.name, r.currency)}
        ${kpiCard('Award', fmtAmt(r.amount, r.currency), 'Paid ' + r.payment_month)}
        ${kpiCard('Achievement', r.opportunity, 'Closed by ' + r.close_date)}
      </div>`;
    }

    html += '</div>';
  }

  el.innerHTML = html;
}

function tableHtml(heads, rows) {
  let h = '<div style="overflow-x:auto"><table class="data-table"><thead><tr>';
  heads.forEach(hd => h += `<th>${hd}</th>`);
  h += '</tr></thead><tbody>';
  rows.forEach(row => {
    h += '<tr>';
    row.forEach(cell => h += `<td>${cell ?? ''}</td>`);
    h += '</tr>';
  });
  h += '</tbody></table></div>';
  return h;
}

// ============================================================
// Approve & Send
// ============================================================
let approvalData = [];

async function loadApprovalStatus() {
  const month = document.getElementById('global-month').value;
  const res   = await fetch(`/api/approval_status?month=${month}`);
  approvalData = await res.json();

  const pending  = approvalData.filter(e => e.status === 'pending').length;
  const approved = approvalData.filter(e => e.status === 'approved').length;
  const sent     = approvalData.filter(e => e.status === 'sent').length;
  document.getElementById('as-counts').textContent =
    `${approved} approved · ${sent} sent · ${pending} pending`;

  const heads = ['Name','Region','Currency','Total Commission','Status','Actions'];
  const tbl   = document.getElementById('as-table');
  tbl.innerHTML = '';

  const thead = tbl.createTHead();
  const hr    = thead.insertRow();
  heads.forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    hr.appendChild(th);
  });

  const tbody = tbl.createTBody();
  approvalData.forEach(e => {
    const tr = tbody.insertRow();
    tr.innerHTML = `
      <td>${e.name}</td>
      <td>${e.region}</td>
      <td>${e.currency}</td>
      <td style="text-align:right"><strong>${fmtAmt(e.total_commission, e.currency)}</strong></td>
      <td style="text-align:center"><span class="badge ${e.status}" id="badge-${e.employee_id}">${e.status}</span></td>
      <td style="text-align:right">
        ${e.status === 'pending'   ? `<button class="btn" onclick="approveEmp('${e.employee_id}')">Approve</button>` : ''}
        ${e.status === 'approved'  ? `<button class="btn danger" onclick="unapproveEmp('${e.employee_id}')">Undo</button>` : ''}
        ${e.status !== 'pending'   ? `<button class="btn" style="margin-left:6px" onclick="previewPDFFor('${e.employee_id}')">Preview PDF</button>` : ''}
      </td>
    `;
  });
}

async function approveEmp(empId) {
  const month = document.getElementById('global-month').value;
  await fetch('/api/approve', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:empId,month})});
  toast('Approved ✓');
  loadApprovalStatus();
}

async function unapproveEmp(empId) {
  const month = document.getElementById('global-month').value;
  await fetch('/api/unapprove', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({employee_id:empId,month})});
  toast('Reverted to pending');
  loadApprovalStatus();
}

async function sendAllApproved() {
  const month = document.getElementById('global-month').value;
  const btn   = document.getElementById('as-send-btn');
  btn.disabled = true;
  btn.textContent = 'Sending…';
  const res  = await fetch('/api/send_approved', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({month})});
  const data = await res.json();
  btn.disabled = false;
  btn.textContent = 'Send All Approved';
  if (data.errors && data.errors.length) {
    toast(`Sent ${data.sent}, ${data.errors.length} error(s) — check config.ini`);
  } else {
    toast(`✓ Sent ${data.sent} statement${data.sent !== 1 ? 's' : ''}`);
  }
  loadApprovalStatus();
}

function previewPDFFor(empId) {
  const month = document.getElementById('global-month').value;
  window.open(`/api/preview_pdf?employee_id=${empId}&month=${month}`, '_blank');
}
function previewPDF() {
  const empId = document.getElementById('wk-emp').value;
  const month = document.getElementById('global-month').value;
  window.open(`/api/preview_pdf?employee_id=${empId}&month=${month}`, '_blank');
}

// ============================================================
// Payroll Summary
// ============================================================
async function loadPayrollSummary() {
  const yr  = document.getElementById('ps-year').value;
  const res = await fetch(`/api/payroll_summary?year=${yr}`);
  const data = await res.json();
  const {months, month_labels, regions} = data;
  const el = document.getElementById('ps-body');

  if (!regions || !regions.length) {
    el.innerHTML = '<div class="panel" style="color:var(--dim)">No data for selected year.</div>';
    return;
  }

  let html = '';
  for (const rd of regions) {
    const emps = rd.employees;
    const qCols = ['Q1','Q2','Q3','Q4'];
    const heads = ['Employee','Title','Currency', ...month_labels, ...qCols, 'Total'];
    // Build totals
    const totMonthly = Object.fromEntries(months.map(m => [m, 0]));
    const totQ = {q1:0,q2:0,q3:0,q4:0}; let totTotal = 0;
    const rowData = emps.map(e => {
      months.forEach(m => totMonthly[m] += e.monthly[m]||0);
      totQ.q1+=e.q1; totQ.q2+=e.q2; totQ.q3+=e.q3; totQ.q4+=e.q4; totTotal+=e.total;
      return [
        e.name, e.title, e.currency,
        ...months.map(m => fmtAmt(e.monthly[m]||0, e.currency)),
        fmtAmt(e.q1,e.currency), fmtAmt(e.q2,e.currency),
        fmtAmt(e.q3,e.currency), fmtAmt(e.q4,e.currency),
        `<strong>${fmtAmt(e.total,e.currency)}</strong>`
      ];
    });
    // Totals row — mixed since regions can have one currency
    const cur = emps.length ? emps[0].currency : 'EUR';
    rowData.push([
      '<strong>TOTAL</strong>', '', cur,
      ...months.map(m => `<strong>${fmtAmt(totMonthly[m],cur)}</strong>`),
      `<strong>${fmtAmt(totQ.q1,cur)}</strong>`, `<strong>${fmtAmt(totQ.q2,cur)}</strong>`,
      `<strong>${fmtAmt(totQ.q3,cur)}</strong>`, `<strong>${fmtAmt(totQ.q4,cur)}</strong>`,
      `<strong>${fmtAmt(totTotal,cur)}</strong>`
    ]);

    html += `<div class="panel" style="margin-bottom:20px">
      <h3>${rd.region} — ${yr}</h3>
      <div class="tbl-wrap">${tableHtml(heads, rowData)}</div>
    </div>`;
  }
  el.innerHTML = html;
}

function exportPayroll() {
  const yr = document.getElementById('ps-year').value;
  window.location.href = `/api/export_payroll?year=${yr}`;
}

async function sendPayroll() {
  const yr    = document.getElementById('ps-year').value;
  const email = document.getElementById('ps-email').value.trim();
  if (!email) { toast('Enter a recipient email first'); return; }
  const res  = await fetch('/api/send_payroll', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year:parseInt(yr),email})});
  const data = await res.json();
  if (data.success) toast(`✓ Payroll summary sent to ${email}`);
  else toast(`✗ Error: ${data.error}`);
}

// ============================================================
// Finance Accruals
// ============================================================
async function loadAccrualSummary() {
  const yr  = document.getElementById('ac-year').value;
  const res = await fetch(`/api/accrual_summary?year=${yr}`);
  const data = await res.json();
  const {months, month_labels, regions} = data;
  const el = document.getElementById('ac-body');

  if (!regions || !regions.length) {
    el.innerHTML = '<div class="panel" style="color:var(--dim)">No data for selected year.</div>';
    return;
  }

  let html = '';
  for (const rd of regions) {
    const rows = rd.rows;
    const qCols = ['Q1','Q2','Q3','Q4'];
    const heads = ['Department','Type', ...month_labels, ...qCols, 'Total (EUR)'];
    const totMonthly = Object.fromEntries(months.map(m => [m, 0]));
    const totQ = {q1:0,q2:0,q3:0,q4:0}; let totTotal = 0;
    const rowData = rows.map(r => {
      const isNI = r.type.includes('NI');
      if (!isNI) {
        months.forEach(m => totMonthly[m] += r.monthly[m]||0);
        totQ.q1+=r.q1; totQ.q2+=r.q2; totQ.q3+=r.q3; totQ.q4+=r.q4; totTotal+=r.total;
      }
      const style = isNI ? 'color:var(--dim);font-style:italic' : '';
      const fmt = v => isNI
        ? `<span style="${style}">${fmtAmt(v,'EUR')}</span>`
        : fmtAmt(v,'EUR');
      return [
        `<span style="${style}">${r.department}</span>`,
        `<span style="${style}">${r.type}</span>`,
        ...months.map(m => fmt(r.monthly[m]||0)),
        fmt(r.q1), fmt(r.q2), fmt(r.q3), fmt(r.q4),
        isNI ? fmt(r.total) : `<strong>${fmtAmt(r.total,'EUR')}</strong>`
      ];
    });
    rowData.push([
      '<strong>TOTAL (Commission)</strong>', '',
      ...months.map(m => `<strong>${fmtAmt(totMonthly[m],'EUR')}</strong>`),
      `<strong>${fmtAmt(totQ.q1,'EUR')}</strong>`, `<strong>${fmtAmt(totQ.q2,'EUR')}</strong>`,
      `<strong>${fmtAmt(totQ.q3,'EUR')}</strong>`, `<strong>${fmtAmt(totQ.q4,'EUR')}</strong>`,
      `<strong>${fmtAmt(totTotal,'EUR')}</strong>`
    ]);

    html += `<div class="panel" style="margin-bottom:20px">
      <h3>${rd.region} — FY${yr} (EUR)</h3>
      <div class="tbl-wrap">${tableHtml(heads, rowData)}</div>
    </div>`;
  }
  el.innerHTML = html;
}

function exportAccrual() {
  const yr = document.getElementById('ac-year').value;
  window.location.href = `/api/export_accrual?year=${yr}`;
}

async function sendAccrual() {
  const yr    = document.getElementById('ac-year').value;
  const email = document.getElementById('ac-email').value.trim();
  if (!email) { toast('Enter a recipient email first'); return; }
  const res  = await fetch('/api/send_accrual', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({year:parseInt(yr),email})});
  const data = await res.json();
  if (data.success) toast(`✓ Accrual summary sent to ${email}`);
  else toast(`✗ Error: ${data.error}`);
}

// ============================================================
// Data view
// ============================================================
async function loadDataView() {
  const tbl = document.getElementById('dv-table').value;
  let url;
  if (tbl === 'activities') url = '/api/commission_workings?employee_id=&month=';
  // Simplified: reload approval status as proxy for data view
  const month = months[months.length-1] || '';
  const res = tbl === 'employees'
    ? await fetch('/api/employees')
    : await fetch(`/api/team_overview?month=${month}`);

  if (tbl === 'employees') {
    dvData = await res.json();
  } else {
    const d = await res.json();
    dvData = d.employees || [];
  }
  dvHeaders = dvData.length ? Object.keys(dvData[0]) : [];
  renderDVTable(dvData);
}

function filterDataView() {
  const q = document.getElementById('dv-search').value.toLowerCase();
  const filtered = dvData.filter(r => Object.values(r).some(v => String(v).toLowerCase().includes(q)));
  renderDVTable(filtered);
}

function renderDVTable(data) {
  const tbl = document.getElementById('dv-table-el');
  if (!data.length) { tbl.innerHTML = '<tr><td>No data</td></tr>'; return; }
  const heads = Object.keys(data[0]);
  const rows  = data.map(r => heads.map(h => r[h] ?? ''));
  renderTable('dv-table-el', heads, rows);
}

// ============================================================
// Chart helpers
// ============================================================
const PALETTE = ['#FF9178','#16a34a','#7c3aed','#ea580c','#0891b2','#db2777'];

function renderBar(id, labels, data, label, color='#FF9178') {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'bar',
    data:{labels,datasets:[{label,data,backgroundColor:color+'CC',borderRadius:6}]},
    options:{responsive:true,plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#595959',font:{size:10,family:'Space Grotesk'}}},
              y:{ticks:{color:'#595959',font:{size:10}},grid:{color:'#E0E0E0'}}}}
  });
}

function renderLine(id, labels, data, label) {
  if (charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type:'line',
    data:{labels,datasets:[{label,data,borderColor:'#FF9178',backgroundColor:'rgba(255,145,120,.12)',tension:.3,fill:true,pointRadius:4,pointBackgroundColor:'#FF9178'}]},
    options:{responsive:true,plugins:{legend:{display:false}},
      scales:{x:{ticks:{color:'#595959',font:{size:10,family:'Space Grotesk'}}},
              y:{ticks:{color:'#595959',font:{size:10}},grid:{color:'#E0E0E0'}}}}
  });
}

// ============================================================
// Table helpers
// ============================================================
function renderTable(id, heads, rows) {
  const tbl = document.getElementById(id);
  const numCols = new Set(rows.flatMap((r,i) => r.map((v,j) => typeof v==='number'?j:-1)).filter(x=>x>=0));
  let html = '<thead><tr>' + heads.map(h => `<th>${h}</th>`).join('') + '</tr></thead><tbody>';
  rows.forEach(r => {
    html += '<tr>' + r.map((v,j) => `<td${j>0?' style="text-align:right"':''}>${v??''}</td>`).join('') + '</tr>';
  });
  html += '</tbody>';
  tbl.innerHTML = html;
}

// ============================================================
// Formatting helpers
// ============================================================
function fmtMonth(s) {
  if (!s) return '';
  const d = new Date(s);
  return d.toLocaleDateString('en-GB',{month:'short',year:'2-digit'}).replace(' ','·');
}

function fmtAmt(v, currency) {
  if (v === null || v === undefined) return '—';
  const n = parseFloat(v);
  if (isNaN(n)) return '—';
  if (currency === 'mixed') return n.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
  const syms = {SEK:'kr',GBP:'£',EUR:'€',USD:'$'};
  const sym  = syms[currency] || '';
  if (currency === 'SEK') return n.toLocaleString('sv-SE',{minimumFractionDigits:0,maximumFractionDigits:0}) + ' kr';
  return sym + n.toLocaleString('en-GB',{minimumFractionDigits:0,maximumFractionDigits:0});
}

function kpiCard(label, value, sub='') {
  return `<div class="kpi-card">
    <div class="label">${label}</div>
    <div class="value">${value}</div>
    ${sub ? `<div class="sub">${sub}</div>` : ''}
  </div>`;
}

function attainCell(pct) {
  const w = Math.min(100, pct);
  const cls = pct >= 100 ? 'ok' : '';
  return `<div class="attain-wrap">
    <span style="font-size:12px;font-weight:600${pct>=100?';color:var(--green)':''}">${pct}%</span>
    <div class="attain-bar-bg"><div class="attain-bar ${cls}" style="width:${w}%"></div></div>
  </div>`;
}

// ============================================================
// Toast
// ============================================================
function toast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3000);
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

// ============================================================
// CSV export
// ============================================================
function exportCSV(tab) {
  const tbl = document.querySelector(`#tab-${tab} table`);
  if (!tbl) return;
  const rows = [...tbl.querySelectorAll('tr')].map(r =>
    [...r.querySelectorAll('th,td')].map(c => '"' + c.innerText.replace(/"/g,'""') + '"').join(',')
  );
  const blob = new Blob([rows.join('\n')], {type:'text/csv'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `commission_${tab}_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

init();
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    global MODEL, APPROVAL, SMTP_CONFIG, DATA_DIR, LOGO_PATH

    parser = argparse.ArgumentParser(description="Commission Calculator")
    parser.add_argument("--data-dir",   default="data",  help="Path to CSV data folder")
    parser.add_argument("--port",       default=8050, type=int, help="HTTP port")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser")
    args = parser.parse_args()

    DATA_DIR  = args.data_dir
    LOGO_PATH = os.path.join("assets", "normative_logo.png")

    SMTP_CONFIG = load_config("config.ini")
    APPROVAL    = ApprovalState(os.path.join(DATA_DIR, "approval_state.json"))

    print(f"[Commission Calculator] Loading data from '{DATA_DIR}'...")
    MODEL = run_pipeline(DATA_DIR)

    print(f"[Commission Calculator] Serving on http://localhost:{args.port}")
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")

    server = HTTPServer(("", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Commission Calculator] Stopped.")


if __name__ == "__main__":
    main()
