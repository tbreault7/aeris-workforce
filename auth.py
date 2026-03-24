import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone
from config import get_settings

settings = get_settings()


def make_token(employee_id: str, week: str) -> str:
    payload = f"{employee_id}:{week}"
    sig     = hmac.new(settings.magic_link_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw     = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_token(token: str) -> tuple[str, str]:
    """Returns (employee_id, week_start) or raises ValueError."""
    try:
        raw   = base64.urlsafe_b64decode(token.encode()).decode()
        parts = raw.split(":")
        if len(parts) != 3:
            raise ValueError("Malformed token")
        emp_id, week, sig = parts
        expected = hmac.new(
            settings.magic_link_secret.encode(),
            f"{emp_id}:{week}".encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Invalid signature")
        week_dt = datetime.strptime(week, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > week_dt + timedelta(days=10):
            raise ValueError("Token expired")
        return emp_id, week
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Bad token: {e}")


def verify_admin(password: str) -> bool:
    return hmac.compare_digest(password, settings.admin_password)


def current_week() -> str:
    """Monday of the current week as YYYY-MM-DD."""
    from datetime import date
    today = date.today()
    return str(today - timedelta(days=today.weekday()))
