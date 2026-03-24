from datetime import datetime, timezone
from sqlalchemy import (
    create_engine, Column, String, Boolean, Integer,
    Float, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.dialects.postgresql import JSONB
from config import get_settings

settings = get_settings()

engine = SessionLocal = None


def init_db():
    global engine, SessionLocal
    db_url = settings.database_url
    # Railway injects DATABASE_URL with postgres:// — SQLAlchemy needs postgresql://
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"

    id         = Column(String, primary_key=True)   # slug e.g. "john_smith"
    name       = Column(String, nullable=False)
    email      = Column(String, nullable=False, unique=True)
    active     = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id           = Column(String, primary_key=True)
    po_number    = Column(String, nullable=False, unique=True)
    client       = Column(String, nullable=False)
    description  = Column(Text, default="")
    status       = Column(String, default="open")   # open | closed
    budget_hours = Column(Float, default=0)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class EmployeePO(Base):
    """Many-to-many: employees <-> purchase_orders"""
    __tablename__ = "employee_pos"
    __table_args__ = (UniqueConstraint("employee_id", "po_id"),)

    id          = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id", ondelete="CASCADE"))
    po_id       = Column(String, ForeignKey("purchase_orders.id", ondelete="CASCADE"))


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("employee_id", "week_start"),)

    id          = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id", ondelete="CASCADE"))
    week_start  = Column(String, nullable=False)   # YYYY-MM-DD (always Monday)
    status      = Column(String, default="draft")  # draft | submitted
    zero_hours  = Column(Boolean, default=False)
    rows        = Column(JSONB, default=list)       # list of row dicts
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))


class Attachment(Base):
    __tablename__ = "attachments"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, ForeignKey("employees.id", ondelete="CASCADE"))
    week_start  = Column(String, nullable=False)
    filename    = Column(String, nullable=False)
    path        = Column(String, nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
