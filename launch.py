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
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import pandas as pd

from src.pipeline import run_pipeline, CommissionModel
from src.reports import (
    team_overview, sdr_detail, monthly_summary,
    quarterly_summary, commission_workings,
    employee_list, available_months, org_chart,
    payroll_summary, accrual_summary,
    cs_overview, cs_quarterly,
    ae_overview, ae_detail, ae_monthly,
    am_overview, am_quarterly,
    se_overview, se_quarterly, se_detail,
)
from src.approval_state import ApprovalState
from src.helpers import clean_json
from src.pdf import generate_statement
from src.email_sender import send_statement, build_cc_list, send_excel_report
from export_excel import export_payroll_workbook, export_accrual_workbook
from src.dashboards import build_dashboard_html

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
MODEL: CommissionModel = None
APPROVAL: ApprovalState = None
SMTP_CONFIG: dict = {}
DATA_DIR: str = "data"
LOGO_PATH: str = "assets/normative-thumbnail-logo.jpg"


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
            role = _p("role", "sdr")
            html = build_dashboard_html(role)
            self._respond_bytes(html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/months":
            self._respond(available_months(MODEL))
            return

        if path == "/api/employees":
            self._respond(employee_list(MODEL))
            return

        if path == "/api/org_chart":
            self._respond(org_chart(MODEL))
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

        if path == "/api/cs_overview":
            month = _parse_month(_p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else None))
            self._respond(cs_overview(MODEL, month))
            return

        if path == "/api/cs_quarterly":
            yr = int(_p("year", pd.Timestamp.now().year))
            qt = int(_p("quarter", 1))
            self._respond(cs_quarterly(MODEL, yr, qt))
            return

        if path == "/api/am_overview":
            month = _parse_month(_p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else None))
            self._respond(am_overview(MODEL, month))
            return

        if path == "/api/am_quarterly":
            yr = int(_p("year", pd.Timestamp.now().year))
            qt = int(_p("quarter", 1))
            self._respond(am_quarterly(MODEL, yr, qt))
            return

        if path == "/api/se_overview":
            month = _parse_month(_p("month", MODEL.default_month.strftime("%Y-%m-%d") if MODEL.default_month else None))
            self._respond(se_overview(MODEL, month))
            return

        if path == "/api/se_quarterly":
            yr = int(_p("year", pd.Timestamp.now().year))
            qt = int(_p("quarter", 1))
            self._respond(se_quarterly(MODEL, yr, qt))
            return

        if path == "/api/se_detail":
            emp_id = _p("employee_id", "")
            self._respond(se_detail(MODEL, emp_id))
            return

        if path == "/api/commission_workings":
            emp_id  = _p("employee_id", "")
            q_str   = _p("quarter", "")
            yr_str  = _p("year", "")
            if q_str and yr_str:
                quarter = int(q_str)
                year    = int(yr_str)
                # quarter-end month for summary lookup
                month   = pd.Timestamp(year=year, month=quarter * 3, day=1)
                self._respond(commission_workings(MODEL, emp_id, month, quarter=quarter, year=year))
            else:
                month = _parse_month(_p("month"))
                self._respond(commission_workings(MODEL, emp_id, month))
            return

        if path == "/api/spifs":
            if MODEL.spif_awards.empty:
                self._respond([])
            else:
                _emp_role = MODEL.employees.set_index("employee_id")["role"].to_dict() if not MODEL.employees.empty else {}
                rows = []
                for _, r in MODEL.spif_awards.iterrows():
                    pm = r["payment_month"]
                    rows.append({
                        "employee_id":   r["employee_id"],
                        "name":          r["name"],
                        "role":          _emp_role.get(r["employee_id"], ""),
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

        if path == "/api/ae_overview":
            yr = int(_p("year", pd.Timestamp.now().year))
            self._respond(ae_overview(MODEL, yr))
            return

        if path == "/api/ae_detail":
            emp_id = _p("employee_id", "")
            yr = int(_p("year", pd.Timestamp.now().year))
            self._respond(ae_detail(MODEL, emp_id, yr))
            return

        if path == "/api/ae_monthly":
            yr = int(_p("year", pd.Timestamp.now().year))
            self._respond(ae_monthly(MODEL, yr))
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

        month_ts = _parse_month(month_str)
        if month_ts is None:
            return None

        # For role-split employees (e.g. sdr_lead Q1 → ae Q2+), pick the entry
        # whose plan window covers this month so the right PDF template is used.
        if len(emp_row) > 1:
            covering = emp_row[
                (emp_row["plan_start_date"].isna() | (emp_row["plan_start_date"] <= month_ts)) &
                (emp_row["plan_end_date"].isna()   | (emp_row["plan_end_date"]   >= month_ts))
            ]
            if not covering.empty:
                emp_row = covering
        emp = emp_row.iloc[0].to_dict()

        det = MODEL.commission_detail[
            (MODEL.commission_detail["employee_id"] == emp_id) &
            (MODEL.commission_detail["month"] == month_ts)
        ]
        summary = det.iloc[0].to_dict() if not det.empty else {}
        summary = {k: (v.strftime("%Y-%m-%d") if isinstance(v, pd.Timestamp) else v)
                   for k, v in summary.items()}

        q = (month_ts.month - 1) // 3 + 1
        wk = commission_workings(
            MODEL, emp_id, month_ts,
            quarter=q if emp["role"] == "ae" else None,
            year=month_ts.year if emp["role"] == "ae" else None,
        )
        rows = wk["rows"]

        acc = None
        if not MODEL.accelerators.empty:
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
    LOGO_PATH = os.path.join("assets", "normative-thumbnail-logo.jpg")

    SMTP_CONFIG = load_config("config.ini")
    APPROVAL    = ApprovalState(os.path.join(DATA_DIR, "approval_state.json"))

    print(f"[Commission Calculator] Loading data from '{DATA_DIR}'...")
    MODEL = run_pipeline(DATA_DIR)

    print(f"[Commission Calculator] Serving on http://localhost:{args.port}")
    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}")

    server = ThreadingHTTPServer(("", args.port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Commission Calculator] Stopped.")


if __name__ == "__main__":
    main()
