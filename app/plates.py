from __future__ import annotations

import hashlib
import logging
import statistics
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.index_store import ClipIndex
from app.location import map_url
from app.media import MediaError, extract_jpeg_sequence
from app.plate_region import classify_plate
from app.scan import Event, Library, camera_label

LOGGER = logging.getLogger("tesla-video-viewer.plates")

DETECTOR_MODEL = "yolo-v9-s-608-license-plate-end2end"
OCR_MODEL = "cct-s-v2-global-model"
SAMPLE_FPS = 1.0
MIN_PLATE_WIDTH = 40
MIN_OCR_CONF = 0.35
MIN_TEXT_LEN = 4
PREFERRED_CAMERAS = ("front",)


class PlateError(RuntimeError):
    pass


class PlateBusy(PlateError):
    pass


@dataclass
class PlateProgress:
    state: str = "idle"
    event_id: str | None = None
    frames_done: int = 0
    frames_total: int = 0
    hits: list[dict[str, object]] = field(default_factory=list)
    plates: list[dict[str, object]] = field(default_factory=list)
    error: str | None = None
    message: str = ""
    detector: str = DETECTOR_MODEL
    ocr: str = OCR_MODEL
    provider: str = ""
    complete: bool = False
    started_mono: float = 0.0
    elapsed_sec: float = 0.0

    def tick_time(self) -> float:
        if self.started_mono:
            self.elapsed_sec = time.monotonic() - self.started_mono
        return self.elapsed_sec

    def to_json(self) -> dict[str, object]:
        self.tick_time()
        eta = None
        if self.state == "running" and self.frames_done > 0 and self.frames_total > self.frames_done:
            rate = self.frames_done / max(self.elapsed_sec, 0.001)
            eta = (self.frames_total - self.frames_done) / rate if rate > 0 else None
        return {
            "state": self.state,
            "eventId": self.event_id,
            "framesDone": self.frames_done,
            "framesTotal": self.frames_total,
            "plates": list(self.plates),
            "error": self.error,
            "message": self.message,
            "detector": self.detector,
            "ocr": self.ocr,
            "provider": self.provider,
            "complete": self.complete,
            "elapsedSec": round(self.elapsed_sec, 1),
            "etaSec": None if eta is None else round(eta, 0),
            "queued": False,
        }


_lock = threading.Lock()
_guard = threading.Lock()
_thread: threading.Thread | None = None
_engine = None
_provider = ""
_progress = PlateProgress()
_cache: dict[str, dict[str, object]] = {}
_queue: list[Event] = []
_store: ClipIndex | None = None
_crop_root = Path(tempfile.mkdtemp(prefix="tesla-plates-"))


def configure_plates(store: ClipIndex) -> None:
    global _store, _crop_root
    _store = store
    _crop_root = store.path.parent / "plate-crops"
    _crop_root.mkdir(parents=True, exist_ok=True)
    store.reset_incomplete_plate_scans()
    store.reclassify_unclassified_plates()


def reset_for_tests() -> None:
    global _engine, _provider, _thread, _progress, _cache, _store, _queue, _crop_root
    if _thread is not None:
        _thread.join(timeout=2)
    _engine = None
    _provider = ""
    _thread = None
    _progress = PlateProgress()
    _cache = {}
    _queue = []
    _store = None
    _crop_root = Path(tempfile.mkdtemp(prefix="tesla-plates-"))


def crop_path(crop_id: str) -> Path:
    safe = "".join(ch for ch in crop_id if ch.isalnum())
    return _crop_root / f"{safe}.jpg"


def catalog_payload() -> dict[str, object]:
    if _store is None:
        return {"plates": [], "total": 0, "classified": 0, "unclassified": 0}
    plates = _store.list_plates()
    classified = sum(1 for item in plates if item.get("jurisdiction"))
    return {
        "plates": plates,
        "total": len(plates),
        "classified": classified,
        "unclassified": len(plates) - classified,
    }


def still_path(crop_id: str) -> Path:
    safe = "".join(ch for ch in crop_id if ch.isalnum())
    return _crop_root / f"{safe}-still.png"


def frame_path(crop_id: str) -> Path:
    safe = "".join(ch for ch in crop_id if ch.isalnum())
    return _crop_root / f"{safe}-frame.png"


def vehicle_path(crop_id: str) -> Path:
    safe = "".join(ch for ch in crop_id if ch.isalnum())
    return _crop_root / f"{safe}-vehicle.png"


def vehicle_crop_box(
    bbox: dict[str, object],
    frame_w: int,
    frame_h: int,
    *,
    scale: float = 10.0,
    upward: float = 0.28,
) -> tuple[int, int, int, int]:
    """Square crop around a plate, shifted up so more of the car is in view."""
    x1 = int(bbox["x1"])
    y1 = int(bbox["y1"])
    x2 = int(bbox["x2"])
    y2 = int(bbox["y2"])
    plate_w = max(1, x2 - x1)
    plate_h = max(1, y2 - y1)
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    side = max(plate_w * scale, plate_h * scale * 1.15, 240.0)
    side = min(side, float(min(frame_w, frame_h)))
    cy -= upward * side
    left = int(round(cx - side / 2.0))
    top = int(round(cy - side / 2.0))
    size = int(round(side))
    if left < 0:
        left = 0
    if top < 0:
        top = 0
    if left + size > frame_w:
        left = max(0, frame_w - size)
    if top + size > frame_h:
        top = max(0, frame_h - size)
    right = min(frame_w, left + size)
    bottom = min(frame_h, top + size)
    return left, top, right, bottom


def find_hit(event_id: str, crop_id: str) -> dict[str, object] | None:
    status = status_for(event_id)
    for plate in status.get("plates") or []:
        if not isinstance(plate, dict):
            continue
        for hit in plate.get("hits") or []:
            if isinstance(hit, dict) and str(hit.get("cropId") or "") == crop_id:
                return hit
    return None


def cameras_for_plates(names: list[str]) -> list[str]:
    return [name for name in PREFERRED_CAMERAS if name in names]


def normalize_plate(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def mean_confidence(value: float | list[float] | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, list):
        return statistics.mean(value) if value else 0.0
    return float(value)


def _hits_latlon(hits: list[dict[str, object]]) -> tuple[float | None, float | None]:
    for hit in hits:
        lat = hit.get("latitude")
        lon = hit.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon)
    return None, None


def group_hits(
    hits: list[dict[str, object]],
    lat: float | None = None,
    lon: float | None = None,
) -> list[dict[str, object]]:
    buckets: dict[str, list[dict[str, object]]] = {}
    for hit in hits:
        text = str(hit.get("text") or "")
        if not text:
            continue
        buckets.setdefault(text, []).append(hit)
    if lat is None or lon is None:
        found_lat, found_lon = _hits_latlon(hits)
        if lat is None:
            lat = found_lat
        if lon is None:
            lon = found_lon
    plates: list[dict[str, object]] = []
    for text, items in buckets.items():
        items.sort(key=lambda item: float(item["elapsedSec"]))
        best = max(items, key=lambda item: float(item["ocrConfidence"]))
        plates.append(
            {
                "text": text,
                "region": best.get("region"),
                "count": len(items),
                "bestConfidence": best["ocrConfidence"],
                "firstElapsedSec": items[0]["elapsedSec"],
                "lastElapsedSec": items[-1]["elapsedSec"],
                "camera": items[0]["camera"],
                "cameraLabel": items[0]["cameraLabel"],
                "cropId": best["cropId"],
                "hits": items,
                "jurisdiction": classify_plate(text, lat=lat, lon=lon),
            }
        )
    plates.sort(key=lambda item: (-int(item["count"]), float(item["firstElapsedSec"])))
    return plates


def hit_from_appearance(row: dict[str, object]) -> dict[str, object]:
    x1 = row.get("bbox_x1")
    y1 = row.get("bbox_y1")
    x2 = row.get("bbox_x2")
    y2 = row.get("bbox_y2")
    bbox = None
    if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
        bbox = {
            "x1": int(x1),
            "y1": int(y1),
            "x2": int(x2),
            "y2": int(y2),
            "width": int(x2) - int(x1),
            "height": int(y2) - int(y1),
        }
    return {
        "id": row.get("id") or row.get("crop_id"),
        "cropId": row.get("crop_id") or row.get("id"),
        "eventId": row.get("event_id"),
        "text": row["plate_text"],
        "rawText": row["plate_text"],
        "region": row.get("region"),
        "ocrConfidence": row.get("ocr_confidence") or 0,
        "detectConfidence": row.get("detect_confidence") or 0,
        "elapsedSec": row["elapsed_sec"],
        "camera": row["camera"],
        "cameraLabel": camera_label(str(row["camera"])),
        "videoPath": row.get("video_path"),
        "day": row.get("day"),
        "time": row.get("time"),
        "latitude": row.get("latitude"),
        "longitude": row.get("longitude"),
        "locationSource": row.get("location_source"),
        "city": row.get("city"),
        "street": row.get("street"),
        "bbox": bbox,
    }


def appearance_row(event: Event, hit: dict[str, object]) -> dict[str, object]:
    elapsed = float(hit["elapsedSec"])
    stamp = event.start + timedelta(seconds=elapsed)
    resolved = event.segment_for(str(hit["camera"]), elapsed)
    video_path = None if resolved is None else str(resolved[0].path)
    box = hit.get("bbox") if isinstance(hit.get("bbox"), dict) else {}
    return {
        "id": hit["cropId"],
        "plate_text": hit["text"],
        "day": stamp.strftime("%Y-%m-%d"),
        "time": stamp.isoformat(timespec="seconds"),
        "elapsed_sec": elapsed,
        "camera": hit["camera"],
        "video_path": video_path,
        "crop_id": hit["cropId"],
        "region": hit.get("region"),
        "detect_confidence": hit.get("detectConfidence"),
        "ocr_confidence": hit.get("ocrConfidence"),
        "bbox_x1": box.get("x1") if box else None,
        "bbox_y1": box.get("y1") if box else None,
        "bbox_x2": box.get("x2") if box else None,
        "bbox_y2": box.get("y2") if box else None,
        "latitude": event.latitude,
        "longitude": event.longitude,
        "location_source": event.location_source,
        "city": event.city,
        "street": event.street,
    }


def payload_from_store(event_id: str) -> dict[str, object] | None:
    if _store is None:
        return None
    scan = _store.get_plate_scan(event_id)
    if scan is None or str(scan.get("state")) != "complete":
        return None
    hits = [hit_from_appearance(row) for row in _store.list_appearances(event_id)]
    plates = group_hits(hits)
    count = len(plates)
    return {
        "state": "complete",
        "eventId": event_id,
        "framesDone": scan.get("frames_done") or 0,
        "framesTotal": scan.get("frames_total") or 0,
        "plates": plates,
        "error": scan.get("error"),
        "message": f"Found {count} plate{'s' if count != 1 else ''}.",
        "detector": scan.get("detector") or DETECTOR_MODEL,
        "ocr": scan.get("ocr") or OCR_MODEL,
        "provider": scan.get("provider") or "",
        "complete": True,
        "elapsedSec": 0,
        "etaSec": None,
        "queued": False,
    }


def queued_payload(event_id: str, position: int) -> dict[str, object]:
    return {
        "state": "queued",
        "eventId": event_id,
        "framesDone": 0,
        "framesTotal": 0,
        "plates": [],
        "error": None,
        "message": f"Queued behind {position} scan{'s' if position != 1 else ''}.",
        "detector": DETECTOR_MODEL,
        "ocr": OCR_MODEL,
        "provider": _provider,
        "complete": False,
        "elapsedSec": 0,
        "etaSec": None,
        "queued": True,
        "queuePosition": position,
    }


def _clock_from_iso(value: str) -> str:
    if "T" in value:
        return value.split("T", 1)[1][:5]
    return ""


def _clip_ref(
    library: Library | None,
    event_id: str,
    camera: str,
    elapsed: float,
) -> dict[str, object] | None:
    if library is None:
        return None
    event = library.events.get(event_id)
    if event is None:
        return None
    resolved = event.segment_for(camera, elapsed)
    if resolved is None:
        return None
    segment, local = resolved
    return {
        "camera": camera,
        "cameraLabel": camera_label(camera),
        "segmentIndex": segment.index,
        "localSec": round(float(local), 3),
        "elapsedSec": elapsed,
        "videoUrl": f"/api/events/{event_id}/cameras/{camera}/segments/{segment.index}",
    }


def plate_dossier(text: str, library: Library | None) -> dict[str, object] | None:
    if _store is None:
        return None
    key = normalize_plate(text)
    if not key:
        return None
    rows = _store.list_appearances_for_plate(key)
    if not rows:
        return None
    hits = [hit_from_appearance(row) for row in rows]
    groups: dict[str, list[dict[str, object]]] = {}
    for hit in hits:
        groups.setdefault(str(hit.get("eventId") or ""), []).append(hit)
    events_out: list[dict[str, object]] = []
    for eid, group in groups.items():
        if not eid:
            continue
        group.sort(key=lambda item: (float(item["elapsedSec"]), str(item["camera"])))
        first = group[0]
        last = group[-1]
        event = None if library is None else library.events.get(eid)
        lat = first.get("latitude")
        lon = first.get("longitude")
        city = first.get("city")
        street = first.get("street")
        if event is not None:
            if event.latitude is not None:
                lat = event.latitude
            if event.longitude is not None:
                lon = event.longitude
            if event.city:
                city = event.city
            if event.street:
                street = event.street
        lat_f = float(lat) if isinstance(lat, (int, float)) else None
        lon_f = float(lon) if isinstance(lon, (int, float)) else None
        start_iso = None if event is None else event.start.isoformat(timespec="seconds")
        time_iso = str(first.get("time") or start_iso or "")
        clock = _clock_from_iso(time_iso) or (event.start.strftime("%H:%M") if event else "")
        best = max(group, key=lambda item: float(item.get("ocrConfidence") or 0))
        events_out.append(
            {
                "eventId": eid,
                "available": event is not None,
                "kind": None if event is None else event.kind,
                "date": first.get("day") or (event.start.strftime("%Y-%m-%d") if event else None),
                "start": start_iso,
                "time": time_iso or None,
                "clock": clock,
                "city": city,
                "street": street,
                "latitude": lat_f,
                "longitude": lon_f,
                "mapUrl": map_url(lat_f, lon_f) if lat_f is not None and lon_f is not None else None,
                "sourceLabel": None if event is None else event.source_label,
                "firstElapsedSec": float(first["elapsedSec"]),
                "lastElapsedSec": float(last["elapsedSec"]),
                "hitCount": len(group),
                "camera": first["camera"],
                "cameraLabel": first["cameraLabel"],
                "cropId": best.get("cropId"),
                "clip": _clip_ref(library, eid, str(first["camera"]), float(first["elapsedSec"])),
                "hits": [
                    {
                        "elapsedSec": float(item["elapsedSec"]),
                        "time": item.get("time"),
                        "clock": _clock_from_iso(str(item.get("time") or "")),
                        "camera": item["camera"],
                        "cameraLabel": item["cameraLabel"],
                        "cropId": item.get("cropId"),
                        "latitude": item.get("latitude"),
                        "longitude": item.get("longitude"),
                    }
                    for item in group
                ],
            }
        )
    events_out.sort(
        key=lambda item: (str(item.get("date") or ""), str(item.get("clock") or ""), str(item["eventId"]))
    )
    clusters: dict[tuple[float, float], dict[str, object]] = {}
    for item in events_out:
        if item["latitude"] is None or item["longitude"] is None:
            continue
        cluster_key = (round(float(item["latitude"]), 4), round(float(item["longitude"]), 4))
        cluster = clusters.get(cluster_key)
        if cluster is None:
            cluster = {
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
                "city": item.get("city"),
                "street": item.get("street"),
                "mapUrl": item.get("mapUrl"),
                "sightings": [],
            }
            clusters[cluster_key] = cluster
        sightings = cluster["sightings"]
        if isinstance(sightings, list):
            sightings.append(
                {
                    "day": item.get("date"),
                    "time": item.get("time"),
                    "clock": item.get("clock"),
                    "eventId": item["eventId"],
                    "city": item.get("city"),
                    "street": item.get("street"),
                }
            )
    best_hit = max(hits, key=lambda item: float(item.get("ocrConfidence") or 0))
    lat, lon = _hits_latlon(hits)
    times = [str(hit.get("time") or "") for hit in hits if hit.get("time")]
    places: list[str] = []
    for item in events_out:
        label = ", ".join(part for part in [item.get("city"), item.get("street")] if part)
        if label and label not in places:
            places.append(label)
    return {
        "text": key,
        "region": best_hit.get("region"),
        "jurisdiction": classify_plate(key, lat=lat, lon=lon),
        "cropId": best_hit.get("cropId"),
        "appearanceCount": len(hits),
        "eventCount": len(events_out),
        "firstSeen": min(times) if times else None,
        "lastSeen": max(times) if times else None,
        "places": places,
        "events": events_out,
        "points": list(clusters.values()),
    }


def onnx_providers() -> list[str]:
    import onnxruntime as ort

    available = set(ort.get_available_providers())
    # DirectML is present on this PC but crashes native ONNX sessions
    # (0xC0000005) with the FastALPR plate models. Use CPU instead.
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def load_engine():
    global _engine, _provider
    with _lock:
        if _engine is not None:
            return _engine
    try:
        from fast_alpr import ALPR
    except ImportError as exc:
        raise PlateError("fast-alpr is not installed.") from exc
    providers = onnx_providers()
    LOGGER.info("Loading FastALPR detector=%s ocr=%s providers=%s", DETECTOR_MODEL, OCR_MODEL, providers)
    engine = ALPR(
        detector_model=DETECTOR_MODEL,
        detector_conf_thresh=0.35,
        detector_providers=providers,
        ocr_model=OCR_MODEL,
        ocr_device="cpu" if providers[0] == "CPUExecutionProvider" else "auto",
        ocr_providers=providers,
    )
    provider = providers[0]
    with _lock:
        _engine = engine
        _provider = provider
        _progress.provider = provider
    LOGGER.info("FastALPR ready on %s", provider)
    return engine


def _is_running() -> bool:
    return _guard.locked()


def status_for(event_id: str) -> dict[str, object]:
    queued_pos = None
    cached = None
    live = None
    with _lock:
        if _progress.event_id == event_id and _progress.state in {"loading", "running", "error", "complete"}:
            live = _progress.to_json()
        else:
            for index, queued in enumerate(_queue):
                if queued.id == event_id:
                    queued_pos = index + 1
                    break
            cached = _cache.get(event_id)
    if live is not None:
        return live
    if queued_pos is not None:
        return queued_payload(event_id, queued_pos)
    saved = payload_from_store(event_id)
    if saved is not None:
        return saved
    if cached is not None:
        return cached
    return PlateProgress(event_id=event_id).to_json()


def start_plate_scan(event: Event, *, force: bool = False, blocking: bool = False) -> dict[str, object]:
    global _thread
    if not force:
        saved = payload_from_store(event.id)
        if saved is not None:
            with _lock:
                if _is_running() and _progress.event_id == event.id:
                    return _progress.to_json()
            return saved
    with _lock:
        if _is_running():
            if _progress.event_id == event.id and not force:
                return _progress.to_json()
            if force:
                raise PlateBusy("A plate scan is already running.")
            if any(item.id == event.id for item in _queue):
                position = next(i for i, item in enumerate(_queue) if item.id == event.id) + 1
                return queued_payload(event.id, position)
            _queue.append(event)
            return queued_payload(event.id, len(_queue))
        cached = _cache.get(event.id)
        if cached is not None and not force:
            return cached
        _progress.state = "loading"
        _progress.event_id = event.id
        _progress.frames_done = 0
        _progress.frames_total = 0
        _progress.hits = []
        _progress.plates = []
        _progress.error = None
        _progress.message = "Loading plate models…"
        _progress.complete = False
        _progress.started_mono = time.monotonic()
        _progress.elapsed_sec = 0.0
        _progress.provider = _provider

    if blocking:
        if not _guard.acquire(blocking=False):
            raise PlateBusy("A plate scan is already running.")
        try:
            scan_event(event, _progress)
        finally:
            _guard.release()
        _start_next_queued()
        return status_for(event.id)

    if not _guard.acquire(blocking=False):
        raise PlateBusy("A plate scan is already running.")

    def run() -> None:
        try:
            scan_event(event, _progress)
        finally:
            _guard.release()
            _start_next_queued()

    with _lock:
        _thread = threading.Thread(target=run, name="plate-scan", daemon=True)
        _thread.start()
    return status_for(event.id)


def _start_next_queued() -> None:
    with _lock:
        if not _queue or _is_running():
            return
        nxt = _queue.pop(0)
    start_plate_scan(nxt, force=False, blocking=False)


def scan_event(event: Event, progress: PlateProgress, engine_factory: Callable | None = None) -> None:
    factory = engine_factory or load_engine
    try:
        progress.state = "loading"
        progress.message = "Loading plate models…"
        cameras = cameras_for_plates(event.camera_names())
        if not cameras:
            progress.state = "complete"
            progress.complete = True
            progress.message = "No front camera in this event."
            persist_scan(event, progress)
            snapshot = progress.to_json()
            with _lock:
                if progress.event_id:
                    _cache[progress.event_id] = snapshot
            return
        engine = factory()
        estimate = 0
        for camera in cameras:
            track = event.cameras.get(camera)
            if track is None:
                continue
            for segment in track.segments:
                estimate += max(1, int(segment.duration_sec * SAMPLE_FPS + 0.5))
        progress.frames_total = estimate
        progress.state = "running"
        progress.message = "Reading frames…"
        hits: list[dict[str, object]] = []
        done = 0
        for camera in cameras:
            track = event.cameras[camera]
            for segment in track.segments:
                offset = (segment.stamp - event.start).total_seconds()
                label = camera_label(camera)
                progress.message = f"{label} · {segment.path.name}"
                with tempfile.TemporaryDirectory(prefix="tesla-plate-frames-") as raw:
                    frame_dir = Path(raw)
                    try:
                        frames = extract_jpeg_sequence(segment.path, frame_dir, SAMPLE_FPS)
                    except MediaError as exc:
                        LOGGER.warning("%s", exc)
                        continue
                    for index, frame_path in enumerate(frames):
                        elapsed = offset + index / SAMPLE_FPS
                        hit_list = read_frame(engine, event.id, camera, elapsed, frame_path)
                        if hit_list:
                            hits.extend(hit_list)
                            progress.hits = hits
                            progress.plates = group_hits(hits, lat=event.latitude, lon=event.longitude)
                        done += 1
                        progress.frames_done = done
                        if done > progress.frames_total:
                            progress.frames_total = done
                        if frame_path.exists():
                            frame_path.unlink()
        progress.hits = hits
        progress.plates = group_hits(hits, lat=event.latitude, lon=event.longitude)
        progress.frames_done = done
        progress.frames_total = max(progress.frames_total, done)
        progress.state = "complete"
        progress.complete = True
        count = len(progress.plates)
        progress.message = f"Found {count} plate{'s' if count != 1 else ''}."
        persist_scan(event, progress)
        saved = payload_from_store(event.id)
        if saved is not None:
            progress.plates = saved["plates"]
            progress.message = str(saved["message"])
        snapshot = progress.to_json()
        with _lock:
            if progress.event_id:
                _cache[progress.event_id] = snapshot
        LOGGER.info("Plate scan complete for %s: %d plates from %d frames", event.id, count, done)
    except Exception as exc:
        LOGGER.exception("Plate scan failed")
        progress.state = "error"
        progress.complete = False
        progress.error = str(exc)
        progress.message = str(exc)


def persist_scan(event: Event, progress: PlateProgress) -> None:
    if _store is None:
        return
    rows = [appearance_row(event, hit) for hit in progress.hits]
    finished = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    _store.replace_event_appearances(
        event.id,
        rows,
        {
            "state": progress.state,
            "frames_done": progress.frames_done,
            "frames_total": progress.frames_total,
            "detector": progress.detector,
            "ocr": progress.ocr,
            "provider": progress.provider,
            "error": progress.error,
            "started_at": None,
            "finished_at": finished,
        },
    )


def read_frame(engine, event_id: str, camera: str, elapsed_sec: float, frame_path: Path) -> list[dict[str, object]]:
    import cv2

    image = cv2.imread(str(frame_path))
    if image is None:
        return []
    try:
        results = engine.predict(image)
    except Exception:
        LOGGER.exception("ALPR failed on %s", frame_path.name)
        return []
    hits: list[dict[str, object]] = []
    height, width = image.shape[:2]
    for result in results:
        box = result.detection.bounding_box
        if box.width < MIN_PLATE_WIDTH:
            continue
        ocr = result.ocr
        if ocr is None or not ocr.text:
            continue
        text = normalize_plate(ocr.text)
        if len(text) < MIN_TEXT_LEN:
            continue
        ocr_conf = mean_confidence(ocr.confidence)
        if ocr_conf < MIN_OCR_CONF:
            continue
        crop_id = hashlib.sha1(
            f"{event_id}|{camera}|{elapsed_sec:.2f}|{text}|{box.x1}|{box.y1}".encode("utf-8")
        ).hexdigest()[:16]
        pad = 6
        x1 = max(0, box.x1 - pad)
        y1 = max(0, box.y1 - pad)
        x2 = min(width, box.x2 + pad)
        y2 = min(height, box.y2 + pad)
        crop = image[y1:y2, x1:x2]
        if crop.size:
            cv2.imwrite(str(crop_path(crop_id)), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        hits.append(
            {
                "id": crop_id,
                "cropId": crop_id,
                "text": text,
                "rawText": ocr.text,
                "region": ocr.region,
                "ocrConfidence": round(ocr_conf, 3),
                "detectConfidence": round(float(result.detection.confidence), 3),
                "elapsedSec": round(elapsed_sec, 2),
                "camera": camera,
                "cameraLabel": camera_label(camera),
                "bbox": {
                    "x1": int(box.x1),
                    "y1": int(box.y1),
                    "x2": int(box.x2),
                    "y2": int(box.y2),
                    "width": int(box.width),
                    "height": int(box.height),
                },
            }
        )
    return hits
