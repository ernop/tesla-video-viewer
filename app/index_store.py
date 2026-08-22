from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.scan import DEFAULT_SEGMENT_SEC, ClipFile

SCHEMA_VERSION = "1"


@dataclass
class StoredStat:
    mtime_ns: int
    size: int
    duration_sec: float
    duration_source: str


class ClipIndex:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS clips (
                    path TEXT PRIMARY KEY,
                    source_path TEXT NOT NULL,
                    stamp TEXT NOT NULL,
                    camera TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    event_dir TEXT,
                    mtime_ns INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    duration_sec REAL NOT NULL,
                    duration_source TEXT NOT NULL,
                    seen_scan INTEGER NOT NULL DEFAULT 0,
                    skipped INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS clips_source ON clips(source_path);
                """
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', ?)",
                (SCHEMA_VERSION,),
            )
            self._conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES ('scan_id', '0')",
            )
            self._conn.commit()
        stored = self.get_meta("schema")
        if stored != SCHEMA_VERSION:
            raise ValueError(f"clip-index.sqlite3 schema {stored!r} is not {SCHEMA_VERSION}.")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def get_meta(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def next_scan_id(self) -> int:
        current = int(self.get_meta("scan_id") or "0")
        nxt = current + 1
        self.set_meta("scan_id", str(nxt))
        return nxt

    def stats_for_source(self, source_path: Path) -> dict[str, StoredStat]:
        key = str(source_path)
        with self._lock:
            rows = self._conn.execute(
                "SELECT path, mtime_ns, size, duration_sec, duration_source FROM clips WHERE source_path = ? AND skipped = 0",
                (key,),
            ).fetchall()
        return {
            str(row["path"]): StoredStat(
                mtime_ns=int(row["mtime_ns"]),
                size=int(row["size"]),
                duration_sec=float(row["duration_sec"]),
                duration_source=str(row["duration_source"]),
            )
            for row in rows
        }

    def upsert_clip(
        self,
        *,
        path: Path,
        source_path: Path,
        stamp: datetime,
        camera: str,
        kind: str,
        event_dir: str | None,
        mtime_ns: int,
        size: int,
        duration_sec: float,
        duration_source: str,
        seen_scan: int,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO clips(
                    path, source_path, stamp, camera, kind, event_dir,
                    mtime_ns, size, duration_sec, duration_source, seen_scan, skipped
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(path) DO UPDATE SET
                    source_path = excluded.source_path,
                    stamp = excluded.stamp,
                    camera = excluded.camera,
                    kind = excluded.kind,
                    event_dir = excluded.event_dir,
                    mtime_ns = excluded.mtime_ns,
                    size = excluded.size,
                    duration_sec = CASE
                        WHEN clips.mtime_ns = excluded.mtime_ns AND clips.size = excluded.size
                        THEN clips.duration_sec
                        ELSE excluded.duration_sec
                    END,
                    duration_source = CASE
                        WHEN clips.mtime_ns = excluded.mtime_ns AND clips.size = excluded.size
                        THEN clips.duration_source
                        ELSE excluded.duration_source
                    END,
                    seen_scan = excluded.seen_scan,
                    skipped = 0
                """,
                (
                    str(path),
                    str(source_path),
                    stamp.isoformat(timespec="seconds"),
                    camera,
                    kind,
                    event_dir,
                    mtime_ns,
                    size,
                    duration_sec,
                    duration_source,
                    seen_scan,
                ),
            )

    def mark_seen(self, path: Path, seen_scan: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE clips SET seen_scan = ?, skipped = 0 WHERE path = ?",
                (seen_scan, str(path)),
            )

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def prune_source(self, source_path: Path, seen_scan: int) -> int:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM clips WHERE source_path = ? AND seen_scan < ?",
                (str(source_path), seen_scan),
            )
            self._conn.commit()
            return int(cur.rowcount)

    def drop_sources_not_in(self, sources: list[Path]) -> None:
        keep = {str(path) for path in sources}
        with self._lock:
            rows = self._conn.execute("SELECT DISTINCT source_path FROM clips").fetchall()
            for row in rows:
                if str(row["source_path"]) not in keep:
                    self._conn.execute(
                        "DELETE FROM clips WHERE source_path = ?",
                        (row["source_path"],),
                    )
            self._conn.commit()

    def update_duration(self, path: Path, duration_sec: float, duration_source: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE clips SET duration_sec = ?, duration_source = ? WHERE path = ?",
                (duration_sec, duration_source, str(path)),
            )
            self._conn.commit()

    def load_clips(self, sources: list[Path]) -> dict[Path, list[ClipFile]]:
        by_key = {str(path): path for path in sources}
        result: dict[Path, list[ClipFile]] = {path: [] for path in sources}
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT path, source_path, stamp, camera, kind, event_dir,
                       duration_sec, duration_source
                FROM clips
                WHERE skipped = 0
                ORDER BY stamp, path
                """
            ).fetchall()
        for row in rows:
            source = by_key.get(str(row["source_path"]))
            if source is None:
                continue
            result[source].append(
                ClipFile(
                    path=Path(str(row["path"])),
                    stamp=datetime.fromisoformat(str(row["stamp"])),
                    camera=str(row["camera"]),
                    kind=str(row["kind"]),
                    event_dir=None if row["event_dir"] is None else str(row["event_dir"]),
                    duration_sec=float(row["duration_sec"]),
                    duration_source=str(row["duration_source"]),
                )
            )
        return result

    def clip_count(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM clips WHERE skipped = 0").fetchone()
        return 0 if row is None else int(row["n"])
