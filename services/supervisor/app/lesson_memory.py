"""Evidence-backed, operator-reviewed context. Never changes control authority.

Events and lesson revisions are append-only through this application. Database
administrators can still modify them; this is not tamper-proof storage or RL.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from .database import CriticalEventRecord, LessonRecord, SessionLocal


def archive(db, record):
    plant = (record.get('before') or {}).get('plant') or {}
    gate = record.get('gate') or {}
    observed = record.get('applied') is True and (record.get('outcome') or {}).get('status') == 'observed'
    critical = (gate.get('status') in {'rejected', 'modified', 'not_submitted'}
                or record.get('status') == 'invalid_or_unavailable'
                or plant.get('safety_state') not in {None, 'normal'}
                or plant.get('active_alarms') or plant.get('alarms') or observed)
    if not critical or record.get('domain') not in {'water', 'nuclear', 'grid'}:
        return None
    payload = deepcopy(record)
    identifier = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if db.get(CriticalEventRecord, identifier) is None:
        db.add(CriticalEventRecord(id=identifier, domain=record['domain'], payload=payload))
        db.flush()
    return identifier


def events(limit=30):
    if not 1 <= limit <= 100:
        raise ValueError('limit must be 1–100')
    with SessionLocal() as db:
        # Full evidence is available on explicit event lookup, not in listings.
        return [{'event_id':r.id,'domain':r.domain,'audit_id':r.payload.get('id'),
                 'scenario':((r.payload.get('before') or {}).get('plant') or {}).get('scenario')}
                for r in db.scalars(select(CriticalEventRecord).limit(limit))]


def get_event(identifier):
    with SessionLocal() as db:
        row = db.get(CriticalEventRecord, identifier)
        if row is None: raise ValueError('Unknown event')
        return deepcopy(row.payload)


def propose(event_ids, text, expires_days=30):
    if not isinstance(text,str) or not 10 <= len(text.strip()) <= 600:
        raise ValueError('Lesson text must be 10–600 characters')
    if not event_ids or len(event_ids)>8 or not 1 <= expires_days <= 90:
        raise ValueError('Use 1–8 source events and 1–90 days')
    with SessionLocal() as db:
        sources = [db.get(CriticalEventRecord, i) for i in set(event_ids)]
        if any(s is None for s in sources): raise ValueError('Unknown source event')
        scopes = {(s.domain, ((s.payload.get('before') or {}).get('plant') or {}).get('scenario'),
                   (s.payload.get('request') or {}).get('model')) for s in sources}
        if len(scopes)!=1 or any(not v for v in next(iter(scopes))):
            raise ValueError('Sources require one exact domain, scenario and model scope')
        domain, scenario, model = next(iter(scopes))
        now = datetime.now(timezone.utc)
        payload = dict(lesson_id=str(uuid4()), version=1, status='candidate', domain=domain,
                       scenario=scenario, model=model, text=text.strip(), event_ids=sorted(set(event_ids)),
                       created_at=now.isoformat(), expires_at=(now+timedelta(days=expires_days)).isoformat(),
                       authority='context_only', validation='No performance improvement established')
        db.add(LessonRecord(lesson_id=payload['lesson_id'],version=1,payload=payload)); db.commit()
        return payload


def _latest(db):
    latest = select(func.max(LessonRecord.id)).group_by(LessonRecord.lesson_id)
    return db.scalars(select(LessonRecord).where(LessonRecord.id.in_(latest)).order_by(LessonRecord.id.desc())).all()


def lessons():
    with SessionLocal() as db: return [deepcopy(r.payload) for r in _latest(db)]


def review(identifier, expected_version, status, reviewer, reason):
    if status not in {'approved','rejected','revoked'} or not reviewer.strip() or len(reason.strip())<8:
        raise ValueError('Explicit operator, disposition and review reason required')
    with SessionLocal() as db:
        row = db.scalars(select(LessonRecord).where(LessonRecord.lesson_id==identifier).order_by(LessonRecord.version.desc())).first()
        if row is None: raise ValueError('Unknown lesson')
        if row.version != expected_version: raise ValueError('Lesson version changed; reread before review')
        if row.payload['status'] in {'revoked','rejected'}: raise ValueError('Create a new candidate for reconsideration')
        if datetime.fromisoformat(row.payload['expires_at']) <= datetime.now(timezone.utc): raise ValueError('Lesson expired')
        payload = {**deepcopy(row.payload), 'version':row.version+1, 'status':status,
                   'reviewer':reviewer[:100], 'review_reason':reason[:1000],
                   'reviewed_at':datetime.now(timezone.utc).isoformat()}
        db.add(LessonRecord(lesson_id=identifier,version=payload['version'],payload=payload))
        try: db.commit()
        except IntegrityError as exc:
            db.rollback(); raise ValueError('Lesson version changed; reread before review') from exc
        return payload


def retrieve(domain, scenario, model, limit=3, now=None):
    if not 0 <= limit <= 3: raise ValueError('At most three reviewed lessons per call')
    if limit == 0: return []
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        found=[]
        for row in _latest(db):
            p=row.payload
            if (p['status']!='approved' or (p['domain'],p['scenario'],p['model'])!=(domain,scenario,model)
                    or datetime.fromisoformat(p['expires_at'])<=now): continue
            found.append({k:deepcopy(p[k]) for k in ['lesson_id','version','text','event_ids','expires_at','authority','validation']})
            if len(found)==limit: break
        return found


def prompt_context(domain, scenario, model):
    if os.getenv('LESSON_MEMORY_ENABLED', 'false').lower() != 'true': return []
    return retrieve(domain, scenario, model)


def main():
    # Deliberately operator-only CLI: no web endpoint for promoting lessons.
    import argparse
    from .database import initialize_database
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('events'); commands.add_parser('list')
    commands.add_parser('backfill')
    get=commands.add_parser('event');get.add_argument('id')
    draft=commands.add_parser('propose');draft.add_argument('--event',action='append',required=True)
    draft.add_argument('--text',required=True);draft.add_argument('--days',type=int,default=30)
    check=commands.add_parser('review');check.add_argument('id');check.add_argument('--version',type=int,required=True)
    check.add_argument('--status',choices=['approved','rejected','revoked'],required=True)
    check.add_argument('--operator',required=True);check.add_argument('--reason',required=True)
    args=parser.parse_args();initialize_database()
    try:
        if args.command=='events': result=events()
        elif args.command=='list': result=lessons()
        elif args.command=='event': result=get_event(args.id)
        elif args.command=='propose': result=propose(args.event,args.text,args.days)
        elif args.command=='backfill':
            from .database import AgentAuditRecord
            with SessionLocal() as db:
                result={'eligible_events':sum(archive(db,r.payload) is not None for r in db.scalars(select(AgentAuditRecord)).all())}
                db.commit()
        else: result=review(args.id,args.version,args.status,args.operator,args.reason)
        print(json.dumps(result,indent=2))
    except ValueError as exc: parser.error(str(exc))


if __name__=='__main__': main()
