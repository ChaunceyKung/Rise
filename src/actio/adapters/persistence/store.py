from contextlib import contextmanager
from pathlib import Path
from actio.contracts.json import ContractError
from actio.adapters.persistence import database

class Connection:
    def __init__(self, path, *, create=False, readonly=False, lineage=False):
        self.path = Path(path).resolve()
        self.claims = {}
        if create and not self.path.exists():
            database.create(self.path, lineage=lineage)
        self.db = database.connect(self.path, readonly=readonly)
        try:
            self.version = database.inspect(self.db)
            if self.version == 0 and not readonly:
                raise ContractError('legacy database is read-only; migrate to a new copy')
            if not readonly:
                database.ensure_memory_outbox(self.db)
            self.db.execute('PRAGMA foreign_keys=ON')
            if not readonly:
                self.db.execute('PRAGMA journal_mode=WAL')
                self.db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            self.db.close()
            raise
    def close(self):
        self.db.close()
    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()
    def row(self, sql, args=()):
        r = self.db.execute(sql, args).fetchone()
        return dict(r) if r else None
    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.execute(sql, args)]
