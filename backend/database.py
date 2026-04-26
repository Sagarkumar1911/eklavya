"""
database.py — SQLite persistence for RunArtifacts.

Design decision: store the full RunArtifact as a JSON blob in one column.
This keeps the schema dead simple while still making the full audit trail
queryable. We index on run_id, user_id, and final_status for the history endpoint.
"""

from sqlalchemy import create_engine, Column, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import datetime
from typing import Optional
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eklavya.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ── ORM Model ─────────────────────────────────────────────────────────────────
class RunArtifactRecord(Base):
    """
    One row = one full pipeline run.
    artifact_json holds the complete RunArtifact as a JSON string.
    """
    __tablename__ = "run_artifacts"

    id            = Column(String, primary_key=True)          # run_id (uuid)
    user_id       = Column(String, index=True, default="anonymous")
    grade         = Column(String)                            # for quick filtering
    topic         = Column(String)
    final_status  = Column(String, index=True)                # "approved" | "rejected"
    artifact_json = Column(Text, nullable=False)              # full RunArtifact JSON
    created_at    = Column(DateTime, default=datetime.utcnow)


# ── Initialise ─────────────────────────────────────────────────────────────────
def init_db():
    """Create tables if they don't exist yet."""
    Base.metadata.create_all(bind=engine)


# ── Dependency (FastAPI) ───────────────────────────────────────────────────────
def get_db():
    """Yield a DB session, close it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── CRUD helpers ───────────────────────────────────────────────────────────────
def save_artifact(db: Session, artifact_json: str, run_id: str,
                  user_id: str, grade: int, topic: str, final_status: str):
    """Insert a new RunArtifact record."""
    record = RunArtifactRecord(
        id           = run_id,
        user_id      = user_id,
        grade        = str(grade),
        topic        = topic,
        final_status = final_status,
        artifact_json= artifact_json,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_history(db: Session, user_id: Optional[str] = None) -> list[RunArtifactRecord]:
    """Return all artifacts, optionally filtered by user_id, newest first."""
    q = db.query(RunArtifactRecord)
    if user_id:
        q = q.filter(RunArtifactRecord.user_id == user_id)
    return q.order_by(RunArtifactRecord.created_at.desc()).all()