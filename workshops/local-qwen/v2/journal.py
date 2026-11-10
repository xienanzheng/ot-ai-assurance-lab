"""Transactional journal. PostgreSQL at runtime; SQLite for isolated tests."""
import threading
from sqlalchemy import create_engine, MetaData, Table, Column, String, JSON, select, delete
from sqlalchemy.pool import StaticPool


class Journal:
    def __init__(self, url):
        options = {'poolclass':StaticPool,'connect_args':{'check_same_thread':False}} if url=='sqlite://' else {}
        self.engine=create_engine(url, **options)
        self.lock=threading.RLock()
        meta=MetaData()
        self.table=Table('v2_journal',meta,Column('key',String(240),primary_key=True),Column('body',JSON,nullable=False))
        meta.create_all(self.engine)

    def put_many(self, entries):
        with self.lock, self.engine.begin() as connection:
            for key, body in entries.items():
                connection.execute(delete(self.table).where(self.table.c.key==key))
                connection.execute(self.table.insert().values(key=key,body=body))

    def get(self,key):
        with self.lock, self.engine.connect() as connection:
            return connection.execute(select(self.table.c.body).where(self.table.c.key==key)).scalar_one_or_none()

    def list(self,prefix):
        with self.lock, self.engine.connect() as connection:
            return list(connection.execute(select(self.table.c.body).where(self.table.c.key.startswith(prefix))).scalars())
