from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import AppConfig, load_config, save_config
from app.index_store import ClipIndex
from app.indexer import (
    ScanProgress,
    index_path_for,
    library_from_index,
    scan_into_index,
)
from app.media import MediaError, extract_png, probe_duration, require_tool
from app.scan import (
    DEFAULT_SEGMENT_SEC,
    Event,
    Library,
    camera_label,
    source_label_for,
)

LOGGER = logging.getLogger("tesla-video-viewer")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_SCREENSHOT_CAMERAS = 16

_lock = threading.Lock()
_config_lock = threading.Lock()
_scan_guard = threading.Lock()
_config: AppConfig | None = None
_library: Library | None = None
_store: ClipIndex | None = None
_scan_progress = ScanProgress(state="idle")
_scan_thread: threading.Thread | None = None
_duration_cache: dict[tuple[str, int, int], float] = {}


class ConfigUpdate(BaseModel):
    sources: list[str] | None = None
    output_dir: str | None = None


class ScreenshotRequest(BaseModel):
    elapsed_sec: float = Field(ge=0)
    cameras: list[str] | None = None


class OpenFolderRequest(BaseModel):
    path: str


def get_config() -> AppConfig:
    if _config is None:
        raise HTTPException(status_code=500, detail="Server config is not loaded.")
    return _config


def current_library() -> Library:
    if _library is None:
        raise HTTPException(
            status_code=400,
            detail="No clip sources are set. Add folders in Folders.",
        )
    return _library


def skip_dirs_for(config: AppConfig) -> set[Path]:
    skips: set[Path] = set()
    if config.output_dir:
        skips.add(config.output_dir)
    return skips


def get_store() -> ClipIndex:
    if _store is None:
        raise HTTPException(status_code=500, detail="Clip index is not open.")
    return _store


def rebuild_library_from_index() -> None:
    cfg = get_config()
    replace_library(library_from_index(get_store(), cfg.sources))


def scan_status_payload() -> dict[str, object]:
    return _scan_progress.to_json()


def _scan_worker() -> None:
    cfg = get_config()
    store = get_store()
    try:
        scan_into_index(
            store,
            cfg.sources,
            skip_dirs_for(cfg),
            _scan_progress,
            on_batch=rebuild_library_from_index,
        )
    except Exception as exc:
        LOGGER.exception("Scan failed")
        _scan_progress.state = "error"
        _scan_progress.error = str(exc)
        _scan_progress.finished_at = None
        _scan_progress.complete = False


def scan_is_running() -> bool:
    if _scan_guard.locked():
        return True
    with _lock:
        return _scan_thread is not None and _scan_thread.is_alive()


def start_scan(*, blocking: bool) -> bool:
    global _scan_thread
    cfg = get_config()
    if not cfg.sources:
        replace_library(None)
        _scan_progress.state = "idle"
        return False
    if blocking:
        if not _scan_guard.acquire(blocking=False):
            return False
        try:
            _scan_worker()
        finally:
            _scan_guard.release()
        return True
    if not _scan_guard.acquire(blocking=False):
        return False

    def run() -> None:
        try:
            _scan_worker()
        finally:
            _scan_guard.release()

    with _lock:
        _scan_thread = threading.Thread(target=run, name="clip-scan", daemon=True)
        _scan_thread.start()
    return True


def replace_library(library: Library | None) -> None:
    global _library
    with _lock:
        _library = library


def cached_duration(path: Path) -> float:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
    with _lock:
        cached = _duration_cache.get(key)
    if cached is not None:
        return cached
    duration = probe_duration(path)
    with _lock:
        _duration_cache[key] = duration
    return duration


def probe_event(event: Event) -> Event:
    jobs: list[tuple[str, int, Path]] = []
    for camera, track in event.cameras.items():
        for segment in track.segments:
            jobs.append((camera, segment.index, segment.path))
    errors: list[str] = []
    measured: dict[tuple[str, int], float] = {}
    if not jobs:
        return event
    workers = min(8, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(cached_duration, path): (camera, index)
            for camera, index, path in jobs
        }
        for future in as_completed(future_map):
            camera, index = future_map[future]
            try:
                measured[(camera, index)] = future.result()
            except MediaError as exc:
                errors.append(str(exc))
    if errors:
        LOGGER.warning("Duration probe failed for %s segment(s); keep Tesla 60s default.", len(errors))
    assumed = False
    for camera, track in event.cameras.items():
        for segment in track.segments:
            duration = measured.get((camera, segment.index))
            if duration is None:
                segment.duration_sec = DEFAULT_SEGMENT_SEC
                segment.duration_source = "tesla-minute-default"
                assumed = True
                continue
            segment.duration_sec = duration
            segment.duration_source = "ffprobe"
            if _store is not None:
                _store.update_duration(segment.path, duration, "ffprobe")
    event.assumed_duration = assumed
    return event


def event_payload(event: Event, include_segments: bool) -> dict[str, object]:
    cameras = []
    for name in event.camera_names():
        track = event.cameras[name]
        camera_body: dict[str, object] = {
            "id": name,
            "label": track.label,
            "segmentCount": len(track.segments),
        }
        if include_segments:
            camera_body["segments"] = [
                {
                    "index": segment.index,
                    "stamp": segment.stamp.isoformat(timespec="seconds"),
                    "durationSec": segment.duration_sec,
                    "durationSource": segment.duration_source,
                    "offsetSec": (segment.stamp - event.start).total_seconds(),
                }
                for segment in track.segments
            ]
        cameras.append(camera_body)
    return {
        "id": event.id,
        "kind": event.kind,
        "start": event.start.isoformat(timespec="seconds"),
        "end": event.end().isoformat(timespec="seconds"),
        "durationSec": event.duration_sec(),
        "layout": event.layout(),
        "cameras": cameras,
        "label": event.label,
        "city": event.city,
        "reason": event.reason,
        "date": event.start.strftime("%Y-%m-%d"),
        "time": event.start.strftime("%H:%M:%S"),
        "sourcePath": str(event.source_path),
        "sourceLabel": event.source_label,
        "assumedDuration": event.assumed_duration,
    }


def serialize_sources(cfg: AppConfig, library: Library | None) -> list[dict[str, object]]:
    if library is not None:
        return [
            {
                "path": str(item.path),
                "label": item.label,
                "available": item.available,
                "clipCount": item.clip_count,
                "skipped": item.skipped,
                "error": item.error,
            }
            for item in library.sources
        ]
    return [
        {
            "path": str(path),
            "label": source_label_for(path, cfg.sources),
            "available": path.is_dir(),
            "clipCount": 0,
            "skipped": 0,
            "error": None if path.is_dir() else "Folder is not attached.",
        }
        for path in cfg.sources
    ]


def parse_source_paths(values: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for item in values:
        text = item.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Source folder must not be blank.")
        path = Path(text).expanduser()
        if not path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Source folder does not exist: {path}",
            )
        key = str(path.resolve()).casefold()
        if key in seen:
            raise HTTPException(status_code=400, detail=f"Duplicate source folder: {path}")
        seen.add(key)
        paths.append(path)
    return paths


def get_event(event_id: str) -> Event:
    library = current_library()
    event = library.events.get(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Unknown event {event_id}.")
    return event


def create_app(config: AppConfig, *, background_scan: bool = True) -> FastAPI:
    global _config, _store
    _config = config
    _store = ClipIndex(index_path_for(config.path))
    try:
        rebuild_library_from_index()
    except OSError as exc:
        LOGGER.warning("%s", exc)
        replace_library(None)
    if config.sources:
        start_scan(blocking=not background_scan)

    app = FastAPI(title="Tesla video viewer", docs_url=None, redoc_url=None)

    @app.get("/api/health")
    def health() -> dict[str, object]:
        ffmpeg_ok = True
        try:
            require_tool("ffmpeg")
            require_tool("ffprobe")
        except MediaError:
            ffmpeg_ok = False
        library = _library
        return {
            "ok": True,
            "ffmpeg": ffmpeg_ok,
            "clipCount": 0 if library is None else library.clip_count,
        }

    @app.get("/api/config")
    def read_config() -> dict[str, object]:
        cfg = get_config()
        library = _library
        return {
            "sources": serialize_sources(cfg, library),
            "outputDir": str(cfg.output_dir),
            "host": cfg.host,
            "port": cfg.port,
            "hasLibrary": library is not None,
            "clipCount": 0 if library is None else library.clip_count,
            "skipped": 0 if library is None else library.skipped,
            "eventCount": 0 if library is None else len(library.events),
            "ffmpeg": _ffmpeg_ok(),
            "scan": scan_status_payload(),
        }

    @app.put("/api/config")
    def update_config(body: ConfigUpdate) -> dict[str, object]:
        if not _config_lock.acquire(blocking=False):
            raise HTTPException(
                status_code=409,
                detail="A folder save is already in progress.",
            )
        try:
            if scan_is_running():
                raise HTTPException(
                    status_code=409,
                    detail="A scan is already running. Wait for it to finish.",
                )
            cfg = get_config()
            if body.sources is not None:
                cfg.sources = parse_source_paths(body.sources)
            if body.output_dir is not None:
                text = body.output_dir.strip()
                if not text:
                    raise HTTPException(status_code=400, detail="output_dir must not be blank.")
                cfg.output_dir = Path(text).expanduser()
            save_config(cfg)
            get_store().drop_sources_not_in(
                [path.resolve() if path.exists() else path for path in cfg.sources]
            )
            rebuild_library_from_index()
            start_scan(blocking=False)
            return read_config()
        finally:
            _config_lock.release()

    @app.post("/api/rescan")
    def rescan() -> dict[str, object]:
        if scan_is_running():
            return read_config()
        start_scan(blocking=False)
        return read_config()

    @app.get("/api/scan")
    def scan_status() -> dict[str, object]:
        return scan_status_payload()

    @app.get("/api/library")
    def library_index() -> dict[str, object]:
        library = current_library()
        span = library.span()
        months = sorted({day[:7] for day in library.days})
        return {
            "sources": serialize_sources(get_config(), library),
            "clipCount": library.clip_count,
            "skipped": library.skipped,
            "eventCount": len(library.events),
            "span": None
            if span is None
            else {
                "start": span[0].isoformat(timespec="seconds"),
                "end": span[1].isoformat(timespec="seconds"),
            },
            "months": months,
            "days": [
                {
                    "date": summary.date,
                    "eventCount": summary.event_count,
                    "durationSec": summary.duration_sec,
                    "times": summary.times,
                }
                for _, summary in sorted(library.days.items())
            ],
        }

    @app.get("/api/days/{day}")
    def day_index(day: str) -> dict[str, object]:
        library = current_library()
        summary = library.days.get(day)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"No clips on {day}.")
        events = [library.events[event_id] for event_id in summary.event_ids]
        return {
            "date": day,
            "eventCount": summary.event_count,
            "durationSec": summary.duration_sec,
            "events": [event_payload(event, include_segments=False) for event in events],
        }

    @app.get("/api/events/{event_id}")
    def event_detail(event_id: str) -> dict[str, object]:
        event = get_event(event_id)
        try:
            probe_event(event)
        except MediaError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return event_payload(event, include_segments=True)

    @app.get("/api/events/{event_id}/cameras/{camera}/segments/{index}")
    def event_video(event_id: str, camera: str, index: int) -> FileResponse:
        event = get_event(event_id)
        track = event.cameras.get(camera)
        if track is None:
            raise HTTPException(status_code=404, detail=f"No {camera} camera in this event.")
        if index < 0 or index >= len(track.segments):
            raise HTTPException(status_code=404, detail=f"No segment {index} for {camera}.")
        path = track.segments[index].path
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"Clip file is missing: {path.name}")
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=path.name,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.post("/api/events/{event_id}/screenshot")
    def screenshot(event_id: str, body: ScreenshotRequest) -> dict[str, object]:
        cfg = get_config()
        event = get_event(event_id)
        try:
            probe_event(event)
        except MediaError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if body.elapsed_sec > event.duration_sec() + 0.5:
            raise HTTPException(
                status_code=400,
                detail="Screenshot time is past the end of this event.",
            )
        names = body.cameras if body.cameras is not None else event.camera_names()
        if not names:
            raise HTTPException(status_code=400, detail="No cameras requested.")
        if len(names) > MAX_SCREENSHOT_CAMERAS:
            raise HTTPException(status_code=400, detail="Too many cameras requested.")
        unknown = [name for name in names if name not in event.cameras]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown camera(s) in this event: {', '.join(unknown)}",
            )
        stamp = event.start + timedelta(seconds=body.elapsed_sec)
        folder = cfg.output_dir / event.start.strftime("%Y-%m-%d_%H-%M-%S")
        written: list[dict[str, str]] = []
        failures: list[str] = []
        for camera in names:
            resolved = event.segment_for(camera, body.elapsed_sec)
            if resolved is None:
                failures.append(f"{camera_label(camera)} has no clip at this time.")
                continue
            segment, offset = resolved
            filename = f"{stamp.strftime('%Y-%m-%d_%H-%M-%S')}_{camera}.png"
            dest = folder / filename
            try:
                extract_png(segment.path, offset, dest)
            except MediaError as exc:
                failures.append(str(exc))
                continue
            written.append(
                {
                    "camera": camera,
                    "label": camera_label(camera),
                    "path": str(dest),
                }
            )
        if not written:
            raise HTTPException(
                status_code=500,
                detail="No screenshots were written. " + " ".join(failures),
            )
        return {
            "folder": str(folder),
            "stamp": stamp.isoformat(timespec="milliseconds"),
            "written": written,
            "failures": failures,
        }

    @app.post("/api/open-folder")
    def open_folder(body: OpenFolderRequest) -> dict[str, object]:
        path = Path(body.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Folder does not exist: {path}")
        target = str(path.resolve())
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", target], close_fds=True)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", target], close_fds=True)
            else:
                subprocess.Popen(["xdg-open", target], close_fds=True)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Could not open folder: {exc}") from exc
        return {"ok": True, "path": target}

    if not WEB_DIR.is_dir():
        raise FileNotFoundError(f"Missing web UI folder: {WEB_DIR}")
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
    return app


def _ffmpeg_ok() -> bool:
    try:
        require_tool("ffmpeg")
        require_tool("ffprobe")
        return True
    except MediaError:
        return False


def run() -> None:
    parser = argparse.ArgumentParser(description="Tesla multi-camera video viewer.")
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Clip folder. Repeat to add more sources.",
    )
    parser.add_argument(
        "--video-root",
        action="append",
        default=[],
        help="Same as --source.",
    )
    parser.add_argument("--output-dir", help="Folder for full-resolution PNG dumps.")
    parser.add_argument("--host", help="Bind host. Default comes from config.json.")
    parser.add_argument("--port", type=int, help="Bind port. Default comes from config.json.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    config = load_config()
    extra_sources = list(args.source) + list(args.video_root)
    if extra_sources:
        seen = {str(path.resolve()).casefold() for path in config.sources if path.exists()}
        seen.update(str(path).casefold() for path in config.sources)
        for item in extra_sources:
            path = Path(item).expanduser()
            key = str(path.resolve() if path.exists() else path).casefold()
            if key in seen:
                continue
            seen.add(key)
            config.sources.append(path)
    if args.output_dir:
        config.output_dir = Path(args.output_dir).expanduser()
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if config.sources:
        for path in config.sources:
            LOGGER.info("Source: %s", path)
    else:
        LOGGER.info("Source: (none)")
    LOGGER.info("Screenshot folder: %s", config.output_dir)
    app = create_app(config)
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    run()
