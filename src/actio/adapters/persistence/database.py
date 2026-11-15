"""One known legacy schema, explicit creation and copy-only migration. No runtime imports."""
from pathlib import Path
import sqlite3

from actio.contracts.json import ContractError
from actio.adapters.filesystem.common import file_hash
from actio.adapters.filesystem.common import uid
from actio.adapters.filesystem.common import write_json

VERSION = 2


def connect(path, *, readonly=False):
    path = Path(path).resolve()
    if not path.is_file():
        raise ContractError('database missing; use init explicitly')
    db = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                         uri=True, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    return db


def structure(db):
    return [(r[0], r[1], ' '.join(r[2].split())) for r in db.execute(
        "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name")]


def inspect(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (0, VERSION, 3, 4):
        raise ContractError('unsupported database schema version: ' + str(version))
    with sqlite3.connect(':memory:') as expected:
        expected.executescript(Path(__file__).with_name('legacy_schema.sql' if version == 0 else 'schema.sql').read_text())
        if version in (3,4):
            expected.executescript(Path(__file__).with_name('candidate_schema.sql').read_text())
        if version == 4:
            expected.executescript(Path(__file__).with_name('evaluation_schema.sql').read_text())
        actual_structure = structure(db)
        expected_structure = structure(expected)
        # v2 databases created before the optional projection may not have
        # memory_outbox yet. They remain readable; writable connections lazily
        # install the additive table below.
        if version in (VERSION, 3, 4) and not any(name == 'memory_outbox' for _, name, _ in actual_structure):
            expected_structure = [(kind, name, sql) for kind, name, sql in expected_structure if name not in ('memory_outbox', 'memory_outbox_state')]
        if actual_structure != expected_structure:
            raise ContractError('unknown or incomplete database structure')
    if not db.execute("SELECT value FROM meta WHERE key='store'").fetchone():
        raise ContractError('database store identity missing')
    return version


def ensure_memory_outbox(db):
    """Install the optional outbox on an older writable Actio schema."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_outbox'").fetchone():
        db.executescript("""
        CREATE TABLE memory_outbox(
          id TEXT PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, run TEXT NOT NULL REFERENCES run(id),
          namespace TEXT NOT NULL, source_hash TEXT NOT NULL, payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('queued','in_flight','committed','duplicate','abstained','degraded','rejected','needs_reconcile')),
          attempts INTEGER NOT NULL DEFAULT 0, lease_until INTEGER, receipt TEXT, error TEXT,
          created INTEGER NOT NULL, updated INTEGER NOT NULL
        );
        CREATE INDEX memory_outbox_state ON memory_outbox(state, updated);
        """)


def create(path, *, lineage=False):
    path = Path(path).resolve()
    # Exclusive reservation distinguishes initialization from accidental lookup.
    with path.open('xb'):
        pass
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.executescript(Path(__file__).with_name('schema.sql').read_text())
        if lineage:
            db.executescript(Path(__file__).with_name('candidate_schema.sql').read_text())
        db.execute("INSERT INTO meta VALUES('store',?)", (uid(),))
    finally:
        db.close()


def migrate_copy(source, destination):
    """Never mutate the original DB, including its historical claims and pins."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ContractError('migration requires a new copy destination')
    src = connect(source, readonly=True)
    backup = destination.with_name(destination.name + '.backup.sqlite')
    record = destination.with_name(destination.name + '.migration.json')
    stage = destination.with_name(destination.name + '.migrating-' + uid())
    try:
        version = inspect(src)
        if version != 0:
            raise ContractError('migration only supports known Phase 1B version 0')
        if destination.exists():
            # Idempotency is for the same immutable snapshot, never overwrite a copy.
            old = connect(destination, readonly=True)
            try:
                inspect(old)
                row = old.execute('SELECT * FROM migration WHERE id=1').fetchone()
                if not row or not backup.is_file() or row['backup_hash'] != file_hash(backup):
                    raise ContractError('destination is not a verified migration copy')
                check = sqlite3.connect(':memory:')
                try:
                    src.backup(check)
                    saved = connect(backup, readonly=True)
                    try:
                        # Content comparison includes every old table and WAL-visible row.
                        if list(check.iterdump()) != list(saved.iterdump()):
                            raise ContractError('source changed since migration; choose new destination')
                    finally:
                        saved.close()
                finally:
                    check.close()
                return {'status': 'already_migrated', 'destination': str(destination), 'backup_sha256': row['backup_hash']}
            finally:
                old.close()
        if backup.exists() or record.exists():
            raise ContractError('prior migration attempt retained; choose new destination')
        with backup.open('xb'):
            pass
        copy = sqlite3.connect(backup)
        try:
            src.backup(copy, pages=256)
            copy.execute('PRAGMA journal_mode=DELETE')
        finally:
            copy.close()
        h = file_hash(backup)
        result = {'source': str(source), 'destination': str(destination), 'backup': str(backup),
                  'backup_sha256': h, 'from': 0, 'to': VERSION, 'status': 'backup_complete'}
        write_json(record, result)
        saved = connect(backup, readonly=True)
        target = sqlite3.connect(stage, isolation_level=None)
        try:
            saved.backup(target)
            target.execute('PRAGMA foreign_keys=ON')
            target.execute('BEGIN IMMEDIATE')
            for sql in Path(__file__).with_name('schema.sql').read_text().split(';'):
                if any(name in sql for name in ('request_identity', 'scenario_terminal', 'CREATE TABLE IF NOT EXISTS migration', 'memory_outbox')):
                    target.execute(sql)
            target.execute('INSERT INTO migration VALUES(1,0,?,?,?)',
                           (VERSION, h, target.execute("SELECT value FROM meta WHERE key='store'").fetchone()[0]))
            target.execute('PRAGMA user_version=2')
            inspect(target)
            target.commit()
            target.execute('PRAGMA journal_mode=DELETE')
        except BaseException:
            target.rollback()
            raise
        finally:
            target.close()
            saved.close()
        # Windows rename refuses an existing destination; no replacement of user data.
        stage.rename(destination)
        result['status'] = 'migrated'
        write_json(record, result)
        return result
    except BaseException as error:
        if backup.exists() and not destination.exists():
            write_json(record, {'status': 'failed', 'reason': str(error), 'backup': str(backup),
                                'backup_sha256': file_hash(backup), 'retained_stage': str(stage)})
        raise
    finally:
        src.close()


def migrate_lineage_copy(source, destination):
    """Explicit v2 -> v3 snapshot with backup; never upgrade an old run in place."""
    source, destination = Path(source).resolve(), Path(destination).resolve()
    backup = destination.with_name(destination.name + '.backup.sqlite')
    record = destination.with_name(destination.name + '.migration.json')
    stage = destination.with_name(destination.name + '.migrating-' + uid())
    if source == destination or any(p.exists() for p in (destination,backup,record)):
        raise ContractError('new lineage migration destination required')
    src = connect(source, readonly=True)
    try:
        if inspect(src) != 2: raise ContractError('lineage migration requires v2')
        with backup.open('xb'): pass
        saved = sqlite3.connect(backup)
        try: src.backup(saved); saved.execute('PRAGMA journal_mode=DELETE')
        finally: saved.close()
        saved = connect(backup, readonly=True); target = sqlite3.connect(stage, isolation_level=None)
        try:
            saved.backup(target)
            target.executescript('BEGIN IMMEDIATE;\n' + Path(__file__).with_name('candidate_schema.sql').read_text() + '\nCOMMIT;')
            inspect(target); target.execute('PRAGMA journal_mode=DELETE')
        finally: target.close(); saved.close()
        stage.rename(destination)
        result={'status':'migrated','from':2,'to':3,'backup_sha256':file_hash(backup),'source':str(source),'destination':str(destination)}
        write_json(record,result); return result
    except BaseException as error:
        if backup.exists():
            write_json(record,{'status':'failed','reason':str(error),'backup':str(backup),
                               'backup_sha256':file_hash(backup),'retained_stage':str(stage)})
        raise
    finally: src.close()
