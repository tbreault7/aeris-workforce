from datetime import datetime, timedelta
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from config import get_settings
import logging

settings = get_settings()
log = logging.getLogger(__name__)


def _send(to_email: str, subject: str, html: str):
    if not settings.sendgrid_api_key:
        log.warning(f"[EMAIL SKIPPED — no API key] To: {to_email} | Subject: {subject}")
        return
    msg = Mail(
        from_email   = (settings.sendgrid_from_email, "Aeris Technical Solutions"),
        to_emails    = to_email,
        subject      = subject,
        html_content = html,
    )
    SendGridAPIClient(settings.sendgrid_api_key).send(msg)


def send_reminder_email(to_email: str, to_name: str, week: str,
                        portal_url: str, zero_url: str):
    dt         = datetime.strptime(week, "%Y-%m-%d")
    week_label = f"{dt.strftime('%B %d')} – {(dt + timedelta(days=6)).strftime('%B %d, %Y')}"
    subject    = f"Action Required: Submit Your Timesheet for {week_label}"
    html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f6f9;margin:0;padding:20px}}
  .card{{background:#fff;max-width:560px;margin:0 auto;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
  .hdr{{background:#1A3A5C;padding:28px 32px}}.hdr h1{{color:#fff;margin:0;font-size:20px}}
  .hdr p{{color:#a8c4e0;margin:4px 0 0;font-size:13px}}
  .body{{padding:28px 32px;color:#333}}.body p{{line-height:1.6;margin:0 0 16px}}
  .btn-p{{display:inline-block;background:#1A3A5C;color:#fff;padding:12px 28px;border-radius:6px;text-decoration:none;font-weight:700;font-size:15px;margin-bottom:12px}}
  .btn-s{{display:inline-block;background:#f0f0f0;color:#555;padding:10px 24px;border-radius:6px;text-decoration:none;font-size:13px}}
  hr{{border:none;border-top:1px solid #e8e8e8;margin:20px 0}}
  .foot{{background:#f9f9f9;padding:16px 32px;color:#999;font-size:12px;border-top:1px solid #eee}}
</style></head><body>
<div class="card">
  <div class="hdr"><h1>Aeris Technical Solutions</h1><p>Timesheet Reminder</p></div>
  <div class="body">
    <p>Hi {to_name},</p>
    <p>Your timesheet for the week of <strong>{week_label}</strong> is due.</p>
    <p><a class="btn-p" href="{portal_url}">Submit My Timesheet</a></p>
    <hr>
    <p style="color:#888;font-size:13px">If you have <strong>no hours to record</strong> this week:</p>
    <a class="btn-s" href="{zero_url}">No hours this week →</a>
  </div>
  <div class="foot">Aeris Technical Solutions · Automated Timesheet System</div>
</div></body></html>"""
    _send(to_email, subject, html)
    log.info(f"Reminder sent → {to_email} for week {week}")


def send_confirmation_email(to_email: str, to_name: str, week: str):
    dt         = datetime.strptime(week, "%Y-%m-%d")
    week_label = f"{dt.strftime('%B %d')} – {(dt + timedelta(days=6)).strftime('%B %d, %Y')}"
    subject    = f"Timesheet Submitted — {week_label}"
    html = f"""
<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f6f9;margin:0;padding:20px}}
  .card{{background:#fff;max-width:560px;margin:0 auto;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)}}
  .hdr{{background:#1A3A5C;padding:28px 32px}}.hdr h1{{color:#fff;margin:0;font-size:20px}}
  .check{{font-size:48px;text-align:center;padding:24px 0 8px}}
  .body{{padding:8px 32px 28px;color:#333;text-align:center}}.body p{{line-height:1.6}}
  .foot{{background:#f9f9f9;padding:16px 32px;color:#999;font-size:12px;border-top:1px solid #eee;text-align:center}}
</style></head><body>
<div class="card">
  <div class="hdr"><h1>Aeris Technical Solutions</h1></div>
  <div class="check">✓</div>
  <div class="body">
    <p>Hi {to_name},</p>
    <p>Your timesheet for <strong>{week_label}</strong> has been successfully submitted.</p>
  </div>
  <div class="foot">Aeris Technical Solutions · Automated Timesheet System</div>
</div></body></html>"""
    _send(to_email, subject, html)
