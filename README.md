# Aeris Workforce — Railway Prototype

FastAPI + PostgreSQL version for Railway deployment.
Identical feature set to the Azure version — swap Azure services for Railway equivalents.

## Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start a local Postgres (or use Railway's CLI tunnel)
#    Or set DATABASE_URL in .env to point at your Railway DB

# 3. Copy and fill in env
cp .env.example .env

# 4. Run
uvicorn main:app --reload --port 8000
```

Then open:
- http://localhost:8000/admin   → Admin dashboard
- http://localhost:8000/portal  → Employee portal (needs ?token=...)

## Deploy to Railway

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_ORG/aeris-workforce.git
git push -u origin main
```

### Step 2 — Create Railway project
1. Go to railway.app → New Project → Deploy from GitHub repo
2. Select your repo
3. Railway auto-detects Python via nixpacks and uses the Procfile

### Step 3 — Add PostgreSQL
1. In Railway dashboard → + New → Database → PostgreSQL
2. Railway automatically sets `DATABASE_URL` in your service — no manual config needed

### Step 4 — Set environment variables
In Railway dashboard → your service → Variables, add:

```
MAGIC_LINK_SECRET     = (generate: python -c "import secrets; print(secrets.token_hex(32))")
ADMIN_PASSWORD        = your-strong-admin-password
PORTAL_BASE_URL       = https://your-app.railway.app
SENDGRID_API_KEY      = your-sendgrid-key
SENDGRID_FROM_EMAIL   = noreply@aeristechnicalsolutions.com

# Optional — leave blank to skip SharePoint uploads during prototype
SP_SITE_URL           = https://aeristechnicalsolutions.sharepoint.com/sites/TimeTracking
SP_CLIENT_ID          = your-app-registration-client-id
SP_CLIENT_SECRET      = your-app-registration-secret
```

### Step 5 — Deploy
Railway deploys automatically on every push to main.
Once live, visit `https://your-app.railway.app/admin` to get started.

## Project Structure

```
aeris-railway/
├── main.py              # FastAPI app — all routes
├── database.py          # SQLAlchemy models + init
├── auth.py              # Magic link sign/verify, admin auth
├── config.py            # Pydantic settings (reads from .env / Railway vars)
├── generators.py        # Excel + PDF output (openpyxl + reportlab)
├── email_sender.py      # SendGrid emails
├── sharepoint.py        # SharePoint upload (optional)
├── static/
│   ├── portal/index.html   # Employee timesheet portal
│   └── admin/index.html    # Admin dashboard
├── requirements.txt
├── Procfile
└── railway.toml
```

## API Reference

All admin endpoints require `X-Admin-Password` header.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/health` | — | Health check |
| GET | `/portal` | — | Employee portal HTML |
| GET | `/admin` | — | Admin dashboard HTML |
| GET | `/api/timesheet?token=` | token | Load timesheet |
| POST | `/api/timesheet` | token in body | Save / submit |
| GET | `/api/timesheet/zero?token=` | token | Zero-hours submit |
| POST | `/api/timesheet/upload?token=` | token | Upload attachment |
| GET | `/api/timesheet/export?token=&fmt=xlsx\|pdf` | token | Download file |
| GET | `/api/admin/employees` | admin | List employees |
| POST | `/api/admin/employees` | admin | Create employee |
| PATCH | `/api/admin/employees/{id}` | admin | Update employee |
| GET | `/api/admin/pos` | admin | List POs |
| POST | `/api/admin/pos` | admin | Create PO |
| PATCH | `/api/admin/pos/{id}` | admin | Update PO |
| GET | `/api/admin/submissions?week=` | admin | Submission grid |
| POST | `/api/admin/remind/{emp_id}` | admin | Manual reminder |
| GET | `/api/admin/magic-link?employee_id=` | admin | Generate link |
| GET | `/api/admin/export?week=&fmt=` | admin | Bulk ZIP export |

## Migrating to Azure Later

When ready to move to Azure:
- `main.py` → split into `function_app.py` Azure Functions
- `database.py` SQLAlchemy models → Azure Table Storage entities
- APScheduler `reminder_job` → Azure Timer Trigger
- File uploads → Azure Blob Storage
- Static HTML → Azure Static Web Apps
- `DATABASE_URL` env var → `AZ_STORAGE_CONN_STRING`

Everything else (generators, email_sender, sharepoint, auth logic) is identical.
