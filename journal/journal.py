"""Захищений журнал подій (M3, FR-14, NFR-01, NFR-06).

Записи утворюють криптографічний ланцюжок: хеш кожного запису
покриває попередній, тому несанкціоновану зміну журналу виявляє
verify_chain(). PIN-коди до журналу не потрапляють (NFR-01).
"""

import hashlib
import json
import sqlite3
import time


class Journal:
    def __init__(self, path: str = ":memory:"):
        """path — файл SQLite (у стенді за замовчуванням база в пам'яті)."""
        self._db = sqlite3.connect(path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " id TEXT, kind TEXT, status TEXT, data TEXT,"
            " prev_hash TEXT, hash TEXT, ts REAL)")
        last = self._db.execute(
            "SELECT hash FROM events ORDER BY rowid DESC LIMIT 1").fetchone()
        self._last_hash = last[0] if last else "GENESIS"   # продовження ланцюжка

    def write(self, event_id: str, kind: str, status: str, data: dict | None = None) -> None:
        row = {
            "id": event_id,
            "kind": kind,
            "status": status,
            "data": data or {},
            "prev_hash": self._last_hash,
            "ts": time.time(),
        }
        row["hash"] = hashlib.sha256(
            json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        self._db.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            (row["id"], row["kind"], row["status"],
             json.dumps(row["data"], ensure_ascii=False),
             row["prev_hash"], row["hash"], row["ts"]))
        self._db.commit()
        self._last_hash = row["hash"]

    def events(self, kind: str | None = None) -> list[tuple]:
        if kind is None:
            return self._db.execute("SELECT * FROM events").fetchall()
        return self._db.execute(
            "SELECT * FROM events WHERE kind=?", (kind,)).fetchall()

    def close(self) -> None:
        self._db.close()

    def verify_chain(self) -> bool:
        rows = self._db.execute(
            "SELECT id, kind, status, data, prev_hash, hash, ts"
            " FROM events ORDER BY rowid").fetchall()
        prev = "GENESIS"
        for id_, kind, status, data, prev_hash, hash_, ts in rows:
            if prev_hash != prev:
                return False
            row = {"id": id_, "kind": kind, "status": status,
                   "data": json.loads(data), "prev_hash": prev, "ts": ts}
            expected = hashlib.sha256(
                json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            if expected != hash_:
                return False
            prev = hash_
        return True
