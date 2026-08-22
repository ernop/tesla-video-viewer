from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app.index_store import ClipIndex
from app.scan import DEFAULT_SEGMENT_SEC, Library, iter_clip_files, library_from_source_clips

LOGGER = logging.getLogger("tesla-video-viewer.scan")
ProgressFn = Callable[["ScanProgress"], None]
RECENT_LIMIT = 80


@dataclass
class ScanProgress:
    state: str
    files_seen: int = 0
    clips_indexed: int = 0
    clips_unchanged: int = 0
    skipped: int = 0
    current_path: str = ""
    source_path: str = ""
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    complete: bool = False
    elapsed_sec: float = 0.0
    files_per_sec: float = 0.0
    recent: list[dict[str, object]] = field(default_factory=list)
    started_mono: float = 0.0

    def tick_time(self) -> float:
        if self.started_mono:
            self.elapsed_sec = time.monotonic() - self.started_mono
        if self.elapsed_sec > 0:
            self.files_per_sec = self.files_seen / self.elapsed_sec
        return self.elapsed_sec

    def note(self, action: str, path: Path | str, *, log: bool = True) -> None:
        elapsed = self.tick_time()
        text = str(path)
        entry = {
            "action": action,
            "path": text,
            "elapsedSec": round(elapsed, 1),
        }
        self.recent.append(entry)
        if len(self.recent) > RECENT_LIMIT:
            self.recent = self.recent[-RECENT_LIMIT:]
        self.current_path = text
        if log:
            LOGGER.info(
                "%6.1fs  %-9s  indexed=%d  unchanged=%d  skipped=%d  %s",
                elapsed,
                action,
                self.clips_indexed,
                self.clips_unchanged,
                self.skipped,
                text,
            )

    def to_json(self) -> dict[str, object]:
        self.tick_time()
        return {
            "state": self.state,
            "filesSeen": self.files_seen,
            "clipsIndexed": self.clips_indexed,
            "clipsUnchanged": self.clips_unchanged,
            "skipped": self.skipped,
            "currentPath": self.current_path,
            "sourcePath": self.source_path,
            "error": self.error,
            "startedAt": self.started_at,
            "finishedAt": self.finished_at,
            "complete": self.complete,
            "elapsedSec": round(self.elapsed_sec, 1),
            "filesPerSec": round(self.files_per_sec, 2),
            "recent": list(self.recent[-40:]),
        }


def index_path_for(config_path: Path) -> Path:
    return config_path.parent / "clip-index.sqlite3"


def canonical_source(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def library_from_index(store: ClipIndex, sources: list[Path]) -> Library | None:
    if not sources:
        return None
    canons = [canonical_source(path) for path in sources]
    loaded = store.load_clips(canons)
    clips_by_source = {
        original: loaded.get(canon, [])
        for original, canon in zip(sources, canons)
    }
    return library_from_source_clips(sources, clips_by_source)


def scan_into_index(
    store: ClipIndex,
    sources: list[Path],
    skip_dirs: set[Path] | None,
    progress: ScanProgress,
    on_progress: ProgressFn | None = None,
    on_batch: Callable[[], None] | None = None,
    batch_size: int = 100,
    refresh_every: int = 250,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    progress.state = "running"
    progress.started_at = now
    progress.started_mono = time.monotonic()
    progress.finished_at = None
    progress.error = None
    progress.complete = False
    progress.files_seen = 0
    progress.clips_indexed = 0
    progress.clips_unchanged = 0
    progress.skipped = 0
    progress.recent = []
    progress.elapsed_sec = 0.0
    progress.files_per_sec = 0.0
    LOGGER.info("Scan start. %d source(s).", len(sources))
    if on_progress:
        on_progress(progress)

    store.drop_sources_not_in([canonical_source(path) for path in sources])
    scan_id = store.next_scan_id()
    skip = set(skip_dirs or set())
    seen_files: set[Path] = set()
    since_refresh = 0
    last_heartbeat = 0.0

    for source_index, source in enumerate(sources, start=1):
        progress.source_path = str(source)
        canon = canonical_source(source)
        LOGGER.info(
            "%6.1fs  source    %d/%d  %s",
            progress.tick_time(),
            source_index,
            len(sources),
            source,
        )
        if not source.is_dir():
            progress.note("missing", source)
            if on_progress:
                on_progress(progress)
            continue
        existing = store.stats_for_source(canon)
        pending = 0
        for path, clip in iter_clip_files(source, skip_dirs=skip, seen_files=seen_files):
            progress.files_seen += 1
            try:
                stat = path.stat()
            except OSError:
                progress.skipped += 1
                pending += 1
                progress.note("unreadable", path)
                continue
            if clip is None:
                progress.skipped += 1
                pending += 1
                if path.name.lower() != "event.mp4":
                    progress.note("skip", path)
                continue
            prev = existing.get(str(clip.path))
            if prev is not None and prev.mtime_ns == stat.st_mtime_ns and prev.size == stat.st_size:
                store.mark_seen(clip.path, scan_id)
                progress.clips_unchanged += 1
                progress.clips_indexed += 1
                progress.note("unchanged", clip.path)
            else:
                store.upsert_clip(
                    path=clip.path,
                    source_path=canon,
                    stamp=clip.stamp,
                    camera=clip.camera,
                    kind=clip.kind,
                    event_dir=clip.event_dir,
                    mtime_ns=stat.st_mtime_ns,
                    size=stat.st_size,
                    duration_sec=DEFAULT_SEGMENT_SEC,
                    duration_source="tesla-minute-default",
                    seen_scan=scan_id,
                )
                progress.clips_indexed += 1
                progress.note("new", clip.path)
            pending += 1
            since_refresh += 1
            elapsed = progress.tick_time()
            if elapsed - last_heartbeat >= 2.0:
                last_heartbeat = elapsed
                LOGGER.info(
                    "%6.1fs  progress  indexed=%d  files=%d  rate=%.1f/s  %s",
                    elapsed,
                    progress.clips_indexed,
                    progress.files_seen,
                    progress.files_per_sec,
                    progress.current_path,
                )
            if pending >= batch_size:
                store.commit()
                pending = 0
                if on_progress:
                    on_progress(progress)
            if since_refresh >= refresh_every:
                store.commit()
                pending = 0
                since_refresh = 0
                if on_batch:
                    on_batch()
        store.commit()
        store.prune_source(canon, scan_id)
        LOGGER.info(
            "%6.1fs  source-done  %s  indexed=%d",
            progress.tick_time(),
            source,
            progress.clips_indexed,
        )
        if on_progress:
            on_progress(progress)
        if on_batch:
            on_batch()

    progress.state = "complete"
    progress.complete = True
    progress.current_path = ""
    progress.finished_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    progress.tick_time()
    LOGGER.info(
        "%6.1fs  complete  indexed=%d  unchanged=%d  skipped=%d",
        progress.elapsed_sec,
        progress.clips_indexed,
        progress.clips_unchanged,
        progress.skipped,
    )
    if on_progress:
        on_progress(progress)
    if on_batch:
        on_batch()
