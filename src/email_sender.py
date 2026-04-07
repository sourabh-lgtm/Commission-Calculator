"""Gmail SMTP email sender for commission statements."""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr


def send_statement(
    smtp_config: dict,
    employee: dict,
    month_label: str,        # e.g. "February 2026"
    total_commission: float,
    currency: str,
    pdf_path: str,
    cc_emails: list[str],
) -> dict:
    """Send a commission statement PDF to the employee, CC'ing managers/CFO/SD.

    Returns {"success": True} or {"success": False, "error": "..."}.
    """
    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"PDF not found: {pdf_path}"}

    to_email   = employee.get("email", "")
    to_name    = employee.get("name", "")
    from_email = smtp_config.get("user", "")
    from_name  = smtp_config.get("from_name", "Normative Commissions")

    if not to_email:
        return {"success": False, "error": "Employee has no email address"}

    sym = {"SEK": "kr", "GBP": "£", "EUR": "€"}.get(currency, "")
    total_fmt = f"{sym}{total_commission:,.2f}" if currency != "SEK" else f"{total_commission:,.2f} {sym}"

    subject = f"Commission Statement — {to_name} — {month_label}"

    body_html = f"""
    <html><body style="font-family: Arial, sans-serif; color: #000;">
    <p>Hi {to_name.split()[0]},</p>
    <p>Please find attached your commission statement for <strong>{month_label}</strong>.</p>
    <table style="border-collapse:collapse; margin: 16px 0;">
      <tr>
        <td style="padding: 8px 16px 8px 0; color: #595959; font-size: 13px;">Period</td>
        <td style="padding: 8px 0; font-weight: bold;">{month_label}</td>
      </tr>
      <tr>
        <td style="padding: 8px 16px 8px 0; color: #595959; font-size: 13px;">Total Commission</td>
        <td style="padding: 8px 0; font-weight: bold; font-size: 16px;">{total_fmt}</td>
      </tr>
    </table>
    <p>The attached PDF contains a full breakdown of your commission workings for the period.
    If you have any questions, please contact your manager.</p>
    <p style="color: #595959; font-size: 12px; margin-top: 24px;">
      This statement is confidential and intended for the addressee only.<br>
      Normative — Commission &amp; Incentive Team
    </p>
    </body></html>
    """

    body_text = (
        f"Hi {to_name.split()[0]},\n\n"
        f"Please find attached your commission statement for {month_label}.\n\n"
        f"Total Commission: {total_fmt}\n\n"
        f"Please see the attached PDF for full workings.\n\n"
        f"Normative — Commission & Incentive Team"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = formataddr((from_name, from_email))
    msg["To"]      = formataddr((to_name, to_email))

    cc_list = [e for e in cc_emails if e and e != to_email]
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    # Attach PDF
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    pdf_part = MIMEApplication(pdf_data, _subtype="pdf")
    pdf_filename = os.path.basename(pdf_path)
    pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_filename)
    msg.attach(pdf_part)

    all_recipients = [to_email] + cc_list

    try:
        host = smtp_config.get("host", "smtp.gmail.com")
        port = int(smtp_config.get("port", 587))
        user = smtp_config.get("user", "")
        password = smtp_config.get("password", "")

        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            if user and password:
                server.login(user, password)
            server.sendmail(from_email, all_recipients, msg.as_string())

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def send_excel_report(
    smtp_config: dict,
    to_email: str,
    subject: str,
    body_text: str,
    excel_bytes: bytes,
    filename: str,
) -> dict:
    """Send an Excel report as an email attachment."""
    from_email = smtp_config.get("user", "")
    from_name  = smtp_config.get("from_name", "Normative Commissions")

    if not from_email:
        return {"success": False, "error": "SMTP not configured"}

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = formataddr((from_name, from_email))
    msg["To"]      = to_email

    msg.attach(MIMEText(body_text, "plain"))

    xlsx_mime = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    part = MIMEApplication(excel_bytes, _subtype=xlsx_mime)
    part.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(part)

    try:
        host     = smtp_config.get("host", "smtp.gmail.com")
        port     = int(smtp_config.get("port", 587))
        user     = smtp_config.get("user", "")
        password = smtp_config.get("password", "")
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.ehlo(); server.starttls(); server.ehlo()
            if user and password:
                server.login(user, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def build_cc_list(employees_df, employee_id: str) -> list[str]:
    """Return CC emails: manager + all CFO + all sales_director roles."""
    cc = []

    emp_row = employees_df[employees_df["employee_id"] == employee_id]
    if not emp_row.empty:
        manager_id = emp_row.iloc[0].get("manager_id", "")
        if manager_id:
            mgr = employees_df[employees_df["employee_id"] == manager_id]
            if not mgr.empty:
                email = mgr.iloc[0].get("email", "")
                if email:
                    cc.append(email)

    for role in ("cfo", "sales_director"):
        role_rows = employees_df[employees_df["role"] == role]
        for _, r in role_rows.iterrows():
            email = r.get("email", "")
            if email:
                cc.append(email)

    return list(dict.fromkeys(cc))   # deduplicate preserving order
