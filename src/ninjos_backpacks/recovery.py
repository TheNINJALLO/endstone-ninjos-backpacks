"""Keep complete storage snapshots until the primary database confirms a write."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class PendingSave(OSError):
    """The complete new state is durable locally, awaiting the primary DB."""


class RecoveryJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pending (storage_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def put(self, storage_id, payload):
        encoded = json.dumps(payload, ensure_ascii=True)
        with self._connect() as db:
            db.execute('INSERT INTO pending VALUES (?, ?) ON CONFLICT(storage_id) DO UPDATE SET payload=excluded.payload',
                       (storage_id, encoded))
        return encoded

    def acknowledge(self, storage_id, encoded):
        with self._connect() as db:
            db.execute('DELETE FROM pending WHERE storage_id=? AND payload=?', (storage_id, encoded))

    def get(self, storage_id):
        with self._connect() as db:
            row = db.execute('SELECT payload FROM pending WHERE storage_id=?', (storage_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def entries(self):
        with self._connect() as db:
            rows = db.execute('SELECT storage_id,payload FROM pending').fetchall()
        return [(key, json.loads(payload)) for key, payload in rows]
