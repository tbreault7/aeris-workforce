import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler

from config import get_settings
from database import init_db, get_db, Employee, PurchaseOrder, EmployeePO, Submission, Attachment
from auth import make_token, verify_token, verify_admin, current_week
from email_sender import send_reminder_email, send_confirmation_email
from generators import generate_excel, generate_pdf
from sharepoint import upload_to_sharepoint

logging.basicConfig(level=logging.INFO)
log      = logging.getLogger(__name__)
settings = get_settings()

# ── Scheduler ─────────────────────────────────────────────────────────────────
scheduler = BackgroundScheduler()


def reminder_job():
    """Runs Mon–Fri at 8 AM ET. Send reminders to employees without a submission."""
    from database import SessionLocal
    db   = SessionLocal()
    week = current_week()
    try:
        employees = db.query(Employee).filter(Employee.active == True).all()
        for emp in employees:
            existing = db.query(Submission).filter(
                Submission.employee_id == emp.id,
                Submission.week_start  == week,
            ).first()
            if existing:
                continue
            token    = make_token(emp.id, week)
            portal   = f"{settings.portal_base_url}/portal?token={token}"
            zero_url = f"{settings.portal_base_url}/api/timesheet/zero?token={token}"
            send_reminder_email(emp.email, emp.name, week, portal, zero_url)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Path(settings.upload_dir).mkdir(exist_ok=True)
    # Mon–Fri 8 AM ET (13:00 UTC)
    scheduler.add_job(reminder_job, "cron", day_of_week="mon-fri", hour=13, minute=0)
    scheduler.start()
    log.info("Scheduler started")
    yield
    scheduler.shutdown()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Aeris Workforce", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# Serve static portals
if Path("static/portal").exists():
    app.mount("/portal-static", StaticFiles(directory="static/portal"), name="portal-static")
if Path("static/admin").exists():
    app.mount("/admin-static", StaticFiles(directory="static/admin"), name="admin-static")


# ── Helpers ───────────────────────────────────────────────────────────────────
def require_admin(request: Request):
    pw = request.headers.get("X-Admin-Password") or request.query_params.get("adminpw")
    if not pw or not verify_admin(pw):
        raise HTTPException(401, "Unauthorized")

def get_employee_pos(db: Session, employee_id: str) -> list[dict]:
    rows = (db.query(PurchaseOrder)
              .join(EmployeePO, EmployeePO.po_id == PurchaseOrder.id)
              .filter(EmployeePO.employee_id == employee_id,
                      PurchaseOrder.status == "open")
              .all())
    return [{
        "id":     po.id,
        "number": po.po_number,
        "client": po.client,
        "label":  f"{po.po_number} — {po.client}",
    } for po in rows]


# ── Health ─────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ── Portal HTML ────────────────────────────────────────────────────────────────
@app.get("/portal", response_class=HTMLResponse)
def portal_page():
    p = Path("static/portal/index.html")
    return HTMLResponse(p.read_text()) if p.exists() else HTMLResponse("<h1>Portal not found</h1>", 404)


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    p = Path("static/admin/index.html")
    return HTMLResponse(p.read_text()) if p.exists() else HTMLResponse("<h1>Admin not found</h1>", 404)


@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse("""<!DOCTYPE html><html><head><title>Aeris Workforce</title>
<style>body{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#f0f2f4;}
.card{background:#fff;padding:48px;border-radius:12px;text-align:center;
box-shadow:0 2px 12px rgba(0,0,0,.08);max-width:400px;}
h1{color:#1A3A5C;margin-bottom:8px;}p{color:#666;margin-bottom:24px;}
a{display:inline-block;margin:8px;padding:10px 24px;border-radius:6px;
text-decoration:none;font-weight:700;font-size:14px;}
.emp{background:#1A3A5C;color:#fff;}.adm{background:#f0f2f4;color:#333;border:1px solid #ddd;}
</style></head><body><div class="card">
<h1>Aeris Workforce</h1>
<p>Timesheet management system</p>
<a class="adm" href="/admin">Admin Dashboard</a>
</div></body></html>""")


# ── Timesheet: load ────────────────────────────────────────────────────────────
@app.get("/api/timesheet")
def get_timesheet(token: str, db: Session = Depends(get_db)):
    try:
        emp_id, week = verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")

    assigned_pos = get_employee_pos(db, emp_id)

    sub = db.query(Submission).filter(
        Submission.employee_id == emp_id,
        Submission.week_start  == week,
    ).first()

    last_week = str((datetime.strptime(week, "%Y-%m-%d") -
                     __import__("datetime").timedelta(days=7)).date())
    lw_sub = db.query(Submission).filter(
        Submission.employee_id == emp_id,
        Submission.week_start  == last_week,
    ).first()

    return {
        "employee":   {"id": emp.id, "name": emp.name, "email": emp.email},
        "week":       week,
        "assigned_pos": assigned_pos,
        "submission": {
            "rows":   sub.rows or [],
            "status": sub.status,
        } if sub else None,
        "last_week_data": lw_sub.rows if lw_sub else None,
    }


# ── Timesheet: save / submit ───────────────────────────────────────────────────
class TimesheetPayload(BaseModel):
    token:  str
    action: str = "save"   # "save" | "submit"
    rows:   list = []


@app.post("/api/timesheet")
def save_timesheet(payload: TimesheetPayload, db: Session = Depends(get_db)):
    try:
        emp_id, week = verify_token(payload.token)
    except ValueError as e:
        raise HTTPException(401, str(e))

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")

    sub = db.query(Submission).filter(
        Submission.employee_id == emp_id,
        Submission.week_start  == week,
    ).first()

    if sub and sub.status == "submitted":
        raise HTTPException(409, "Timesheet already submitted and locked")

    status = "submitted" if payload.action == "submit" else "draft"

    if sub:
        sub.rows       = payload.rows
        sub.status     = status
        sub.updated_at = datetime.now(timezone.utc)
    else:
        sub = Submission(
            employee_id = emp_id,
            week_start  = week,
            status      = status,
            rows        = payload.rows,
        )
        db.add(sub)
    db.commit()

    if payload.action == "submit":
        _generate_and_upload(emp, week, payload.rows)
        send_confirmation_email(emp.email, emp.name, week)

    return {"status": status, "week": week}


# ── Timesheet: zero hours (from email link) ────────────────────────────────────
@app.get("/api/timesheet/zero", response_class=HTMLResponse)
def submit_zero(token: str, db: Session = Depends(get_db)):
    try:
        emp_id, week = verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))

    sub = db.query(Submission).filter(
        Submission.employee_id == emp_id,
        Submission.week_start  == week,
    ).first()

    if sub and sub.status == "submitted":
        return HTMLResponse(_zero_html("Already submitted", "Your timesheet was already recorded. No changes made."))

    if sub:
        sub.status     = "submitted"
        sub.zero_hours = True
        sub.rows       = []
        sub.updated_at = datetime.now(timezone.utc)
    else:
        db.add(Submission(
            employee_id = emp_id,
            week_start  = week,
            status      = "submitted",
            zero_hours  = True,
            rows        = [],
        ))
    db.commit()
    return HTMLResponse(_zero_html("✓ No hours recorded",
        "Your timesheet has been marked with zero hours. No further reminders will be sent."))


def _zero_html(title: str, msg: str) -> str:
    return f"""<!DOCTYPE html><html><head><title>Aeris</title>
<style>body{{font-family:Arial,sans-serif;display:flex;align-items:center;justify-content:center;
min-height:100vh;margin:0;background:#f5f5f5;}}
.card{{background:#fff;padding:48px;border-radius:12px;text-align:center;
box-shadow:0 2px 12px rgba(0,0,0,.08);max-width:400px;}}
h2{{color:#1A3A5C;margin-bottom:12px;}}p{{color:#666;}}</style></head>
<body><div class="card"><h2>{title}</h2><p>{msg}</p></div></body></html>"""


# ── Timesheet: file upload ─────────────────────────────────────────────────────
@app.post("/api/timesheet/upload")
async def upload_file(
    token: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        emp_id, week = verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))

    safe = "".join(c for c in file.filename if c.isalnum() or c in "._- ")
    dest = Path(settings.upload_dir) / week / emp_id
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / safe

    content = await file.read()
    path.write_bytes(content)

    db.add(Attachment(
        employee_id = emp_id,
        week_start  = week,
        filename    = safe,
        path        = str(path),
    ))
    db.commit()
    return {"filename": safe, "size": len(content)}


# ── Timesheet: download export ─────────────────────────────────────────────────
@app.get("/api/timesheet/export")
def export_timesheet(token: str, fmt: str = "xlsx", db: Session = Depends(get_db)):
    try:
        emp_id, week = verify_token(token)
    except ValueError as e:
        raise HTTPException(401, str(e))

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")

    sub = db.query(Submission).filter(
        Submission.employee_id == emp_id,
        Submission.week_start  == week,
    ).first()
    rows   = sub.rows if sub else []
    client = rows[0].get("client", "General") if rows else "General"

    week_dt  = datetime.strptime(week, "%Y-%m-%d")
    filename = f"TB_{week_dt.strftime('%m%d%Y')}_{emp.name.replace(' ','_')}_Timesheet"

    if fmt == "pdf":
        data = generate_pdf(emp.name, week, client, rows)
        return StreamingResponse(
            __import__("io").BytesIO(data),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )
    else:
        data = generate_excel(emp.name, week, client, rows)
        return StreamingResponse(
            __import__("io").BytesIO(data),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
        )


# ── Admin: employees ───────────────────────────────────────────────────────────
class EmployeeIn(BaseModel):
    name:        str
    email:       str
    assigned_pos: list[str] = []
    active:      bool = True


@app.get("/api/admin/employees")
def list_employees(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    emps = db.query(Employee).order_by(Employee.name).all()
    result = []
    for emp in emps:
        po_ids = [ep.po_id for ep in db.query(EmployeePO).filter(EmployeePO.employee_id == emp.id).all()]
        result.append({
            "id": emp.id, "name": emp.name, "email": emp.email,
            "active": emp.active, "assigned_pos": po_ids,
        })
    return result


@app.post("/api/admin/employees", status_code=201)
def create_employee(body: EmployeeIn, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    emp_id = body.email.split("@")[0].lower().replace(".", "_").replace("-", "_")
    if db.query(Employee).filter(Employee.id == emp_id).first():
        emp_id = emp_id + "_2"

    emp = Employee(id=emp_id, name=body.name, email=body.email, active=body.active)
    db.add(emp)
    db.flush()

    for po_id in body.assigned_pos:
        db.add(EmployeePO(employee_id=emp_id, po_id=po_id))
    db.commit()
    return {"id": emp_id, "created": True}


class EmployeeUpdate(BaseModel):
    name:        Optional[str] = None
    email:       Optional[str] = None
    active:      Optional[bool] = None
    assigned_pos: Optional[list[str]] = None


@app.patch("/api/admin/employees/{emp_id}")
def update_employee(emp_id: str, body: EmployeeUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Not found")
    if body.name  is not None: emp.name   = body.name
    if body.email is not None: emp.email  = body.email
    if body.active is not None: emp.active = body.active
    if body.assigned_pos is not None:
        db.query(EmployeePO).filter(EmployeePO.employee_id == emp_id).delete()
        for po_id in body.assigned_pos:
            db.add(EmployeePO(employee_id=emp_id, po_id=po_id))
    db.commit()
    return {"updated": True}


# ── Admin: purchase orders ─────────────────────────────────────────────────────
class POIn(BaseModel):
    number:       str
    client:       str
    description:  str = ""
    status:       str = "open"
    budget_hours: float = 0


@app.get("/api/admin/pos")
def list_pos(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    pos = db.query(PurchaseOrder).order_by(PurchaseOrder.client).all()
    return [{"id": p.id, "number": p.po_number, "client": p.client,
             "description": p.description, "status": p.status,
             "budget_hours": p.budget_hours} for p in pos]


@app.post("/api/admin/pos", status_code=201)
def create_po(body: POIn, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    po_id = body.number.replace(" ", "_").upper()
    po    = PurchaseOrder(id=po_id, po_number=body.number, client=body.client,
                          description=body.description, status=body.status,
                          budget_hours=body.budget_hours)
    db.add(po)
    db.commit()
    return {"id": po_id, "created": True}


class POUpdate(BaseModel):
    number:       Optional[str] = None
    client:       Optional[str] = None
    description:  Optional[str] = None
    status:       Optional[str] = None
    budget_hours: Optional[float] = None


@app.patch("/api/admin/pos/{po_id}")
def update_po(po_id: str, body: POUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(404, "Not found")
    if body.number      is not None: po.po_number    = body.number
    if body.client      is not None: po.client        = body.client
    if body.description is not None: po.description   = body.description
    if body.status      is not None: po.status        = body.status
    if body.budget_hours is not None: po.budget_hours = body.budget_hours
    db.commit()
    return {"updated": True}


# ── Admin: submissions grid ────────────────────────────────────────────────────
@app.get("/api/admin/submissions")
def admin_submissions(request: Request, week: Optional[str] = None,
                      db: Session = Depends(get_db)):
    require_admin(request)
    week = week or current_week()
    emps = db.query(Employee).filter(Employee.active == True).all()
    subs = {s.employee_id: s for s in
            db.query(Submission).filter(Submission.week_start == week).all()}
    grid = []
    for emp in emps:
        sub = subs.get(emp.id)
        grid.append({
            "employee_id":   emp.id,
            "employee_name": emp.name,
            "email":         emp.email,
            "status":        sub.status if sub else "pending",
            "zero_hours":    sub.zero_hours if sub else False,
            "updated_at":    sub.updated_at.isoformat() if sub and sub.updated_at else "",
        })
    return {"week": week, "submissions": grid}


# ── Admin: manual remind ───────────────────────────────────────────────────────
@app.post("/api/admin/remind/{emp_id}")
def admin_remind(emp_id: str, request: Request,
                 week: Optional[str] = None, db: Session = Depends(get_db)):
    require_admin(request)
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    week     = week or current_week()
    token    = make_token(emp_id, week)
    portal   = f"{settings.portal_base_url}/portal?token={token}"
    zero_url = f"{settings.portal_base_url}/api/timesheet/zero?token={token}"
    send_reminder_email(emp.email, emp.name, week, portal, zero_url)
    return {"sent": True, "to": emp.email}


# ── Admin: magic link ──────────────────────────────────────────────────────────
@app.get("/api/admin/magic-link")
def admin_magic_link(employee_id: str, request: Request,
                     week: Optional[str] = None):
    require_admin(request)
    week  = week or current_week()
    token = make_token(employee_id, week)
    url   = f"{settings.portal_base_url}/portal?token={token}"
    return {"url": url, "week": week, "employee_id": employee_id}


# ── Admin: bulk export ─────────────────────────────────────────────────────────
@app.get("/api/admin/export")
def admin_export(request: Request, week: Optional[str] = None,
                 fmt: str = "xlsx", db: Session = Depends(get_db)):
    require_admin(request)
    import zipfile, io as _io
    week = week or current_week()
    subs = db.query(Submission).filter(
        Submission.week_start == week,
        Submission.status     == "submitted",
    ).all()

    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for sub in subs:
            emp = db.query(Employee).filter(Employee.id == sub.employee_id).first()
            if not emp:
                continue
            rows   = sub.rows or []
            client = rows[0].get("client", "General") if rows else "General"
            week_dt = datetime.strptime(week, "%Y-%m-%d")
            fname  = f"{emp.name.replace(' ','_')}_{week_dt.strftime('%m%d%Y')}_Timesheet"
            if fmt == "pdf":
                zf.writestr(f"{fname}.pdf", generate_pdf(emp.name, week, client, rows))
            else:
                zf.writestr(f"{fname}.xlsx", generate_excel(emp.name, week, client, rows))

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="timesheets_{week}.zip"'},
    )


# ── Internal: generate + upload ────────────────────────────────────────────────
def _generate_and_upload(emp: Employee, week: str, rows: list):
    by_client: dict[str, list] = {}
    for row in rows:
        by_client.setdefault(row.get("client", "General"), []).append(row)
    if not by_client:
        by_client["General"] = []

    week_dt    = datetime.strptime(week, "%Y-%m-%d")
    week_fmt   = week_dt.strftime("%m%d%Y")
    folder_fmt = week_dt.strftime("%m-%d-%y")

    for client, client_rows in by_client.items():
        po_num    = client_rows[0].get("po_number", "NA") if client_rows else "NA"
        base_name = f"TB_{po_num}_{week_fmt}_Timesheet"
        folder    = f"Documents/Week Start ({folder_fmt})/{client}"

        upload_to_sharepoint(generate_excel(emp.name, week, client, client_rows),
                             f"{folder}/{base_name}.xlsx")
        upload_to_sharepoint(generate_pdf(emp.name, week, client, client_rows),
                             f"{folder}/{base_name}.pdf")
