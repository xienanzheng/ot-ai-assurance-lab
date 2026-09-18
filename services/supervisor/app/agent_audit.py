"""Local, persistent inference evidence. Model-emitted text is not verified intent."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from .database import AgentAuditRecord, SessionLocal


def create_audit(domain, payload):
    identifier = str(uuid4())
    body = dict(id=identifier, domain=domain, status="inferencing", created_at=datetime.now(timezone.utc).isoformat(),
                request=payload, provenance="local Ollama model", gate=None, outcome=None,
                interpretation="Model-emitted reasoning and rationale are observations, not verified internal reasoning or intent.")
    with SessionLocal() as db:
        db.add(AgentAuditRecord(id=identifier, domain=domain, payload=body))
        db.commit()
    return identifier


def update_audit(identifier, **changes):
    if not identifier:
        return
    with SessionLocal() as db:
        record = db.get(AgentAuditRecord, identifier)
        if record:
            record.payload = {**record.payload, **deepcopy(changes)}
            from .lesson_memory import archive
            archive(db, record.payload)
            db.commit()


def get_audit(identifier):
    with SessionLocal() as db:
        record = db.get(AgentAuditRecord, identifier)
        return deepcopy(record.payload) if record else None


def list_audits(domain=None, limit=30):
    with SessionLocal() as db:
        query = select(AgentAuditRecord).order_by(AgentAuditRecord.created_at.desc()).limit(limit)
        if domain:
            query = query.where(AgentAuditRecord.domain == domain)
        return [deepcopy(row.payload) for row in db.scalars(query)]
