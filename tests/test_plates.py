from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.index_store import ClipIndex
from app.main import create_app
from app.plates import (
    cameras_for_plates,
    configure_plates,
    group_hits,
    normalize_plate,
    persist_scan,
    payload_from_store,
    plate_dossier,
    reset_for_tests,
    start_plate_scan,
    vehicle_crop_box,
    PlateProgress,
)
from app.scan import Event


def test_normalize_plate_strips_noise() -> None:
    assert normalize_plate("7abc-123") == "7ABC123"
    assert normalize_plate("  CA 7ABC123 ") == "CA7ABC123"


def test_cameras_for_plates_uses_front_only() -> None:
    names = [
        "left_repeater",
        "front",
        "right_repeater",
        "left_pillar",
        "back",
        "right_pillar",
    ]
    assert cameras_for_plates(names) == ["front"]
    assert cameras_for_plates(["left_pillar", "right_pillar"]) == []


def test_vehicle_crop_box_is_square_and_shifted_up() -> None:
    box = {"x1": 1400, "y1": 1000, "x2": 1490, "y2": 1054}
    left, top, right, bottom = vehicle_crop_box(box, 2896, 1876)
    assert right - left == bottom - top
    assert right - left >= 240
    plate_cy = (1000 + 1054) / 2
    crop_cy = (top + bottom) / 2
    assert crop_cy < plate_cy
    assert 0 <= left < right <= 2896
    assert 0 <= top < bottom <= 1876


def test_vehicle_crop_box_clamps_near_edge() -> None:
    box = {"x1": 10, "y1": 1800, "x2": 70, "y2": 1860}
    left, top, right, bottom = vehicle_crop_box(box, 2896, 1876)
    assert left >= 0
    assert top >= 0
    assert right <= 2896
    assert bottom <= 1876


def test_group_hits_keeps_best_crop() -> None:
    plates = group_hits(
        [
            {
                "text": "7ABC123",
                "elapsedSec": 12.0,
                "ocrConfidence": 0.5,
                "camera": "front",
                "cameraLabel": "Front",
                "cropId": "weak",
                "region": None,
            },
            {
                "text": "7ABC123",
                "elapsedSec": 4.0,
                "ocrConfidence": 0.9,
                "camera": "front",
                "cameraLabel": "Front",
                "cropId": "strong",
                "region": "US",
            },
            {
                "text": "XYZ987",
                "elapsedSec": 20.0,
                "ocrConfidence": 0.8,
                "camera": "back",
                "cameraLabel": "Rear",
                "cropId": "other",
                "region": None,
                "bbox": {"x1": 1, "y1": 2, "x2": 80, "y2": 40, "width": 79, "height": 38},
            },
        ]
    )
    assert [item["text"] for item in plates] == ["7ABC123", "XYZ987"]
    assert plates[0]["count"] == 2
    assert plates[0]["firstElapsedSec"] == 4.0
    assert plates[0]["cropId"] == "strong"
    assert plates[0]["region"] == "US"
    assert plates[0]["jurisdiction"]["code"] == "CA"
    assert plates[1]["hits"][0]["bbox"]["x1"] == 1


def _dummy_event() -> Event:
    return Event(
        id="abc123",
        kind="recent",
        folder=None,
        start=datetime(2026, 8, 21, 17, 26, 55),
        cameras={},
        source_path=Path("d:/"),
        source_label="D",
    )


def test_start_plate_scan_returns_cache(monkeypatch) -> None:
    reset_for_tests()
    calls: list[str] = []

    def fake_scan(event, progress, engine_factory=None) -> None:
        calls.append(event.id)
        progress.state = "complete"
        progress.complete = True
        progress.plates = [
            {
                "text": "7ABC123",
                "count": 1,
                "bestConfidence": 0.9,
                "firstElapsedSec": 3.0,
                "lastElapsedSec": 3.0,
                "camera": "front",
                "cameraLabel": "Front",
                "cropId": "crop1",
                "hits": [],
            }
        ]
        progress.message = "Found 1 plate."
        from app import plates

        plates._cache[event.id] = progress.to_json()

    monkeypatch.setattr("app.plates.scan_event", fake_scan)
    event = _dummy_event()
    first = start_plate_scan(event, blocking=True)
    second = start_plate_scan(event, blocking=True)
    assert first["complete"] is True
    assert first["plates"][0]["text"] == "7ABC123"
    assert second["plates"][0]["text"] == "7ABC123"
    assert calls == ["abc123"]


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_plate_routes(tmp_path: Path, monkeypatch) -> None:
    reset_for_tests()

    def fake_scan(event, progress, engine_factory=None) -> None:
        progress.state = "complete"
        progress.complete = True
        progress.plates = []
        progress.message = "Found 0 plates."
        from app import plates

        plates._cache[event.id] = progress.to_json()

    monkeypatch.setattr("app.plates.scan_event", fake_scan)
    root = tmp_path / "TeslaCam"
    folder = root / "SavedClips" / "2023-08-21_15-30-45"
    _touch(folder / "2023-08-21_15-30-45-front.mp4")
    config = AppConfig(
        sources=[root],
        output_dir=tmp_path / "shots",
        host="127.0.0.1",
        port=8765,
        path=tmp_path / "config.json",
    )
    client = TestClient(create_app(config, background_scan=False))
    event_id = client.get("/api/days/2023-08-21").json()["events"][0]["id"]
    idle = client.get(f"/api/events/{event_id}/plates").json()
    assert idle["state"] == "idle"
    started = client.post(f"/api/events/{event_id}/plates", json={"force": False})
    assert started.status_code == 200
    status = started.json()
    for _ in range(50):
        if status["state"] in {"complete", "error"}:
            break
        time.sleep(0.02)
        status = client.get(f"/api/events/{event_id}/plates").json()
    assert status["state"] == "complete"
    missing = client.get(f"/api/events/{event_id}/plates/crops/nonesuch")
    assert missing.status_code == 404
    catalog = client.get("/api/plates").json()
    assert catalog["total"] == 0
    assert catalog["classified"] == 0
    gone = client.get("/api/plates/crops/nonesuch")
    assert gone.status_code == 404


def test_plate_appearances_persist(tmp_path: Path) -> None:
    reset_for_tests()
    store = ClipIndex(tmp_path / "clip-index.sqlite3")
    configure_plates(store)
    event = _dummy_event()
    event.latitude = 30.2672
    event.longitude = -97.7431
    event.city = "Austin"
    event.street = "S Congress Ave"
    event.location_source = "event.json"
    progress = PlateProgress(state="complete", event_id=event.id)
    progress.hits = [
        {
            "cropId": "crop1",
            "text": "7ABC123",
            "region": "US",
            "ocrConfidence": 0.91,
            "detectConfidence": 0.8,
            "elapsedSec": 4.0,
            "camera": "front",
            "cameraLabel": "Front",
            "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "width": 100, "height": 40},
        }
    ]
    persist_scan(event, progress)
    rows = store.list_appearances(event.id)
    assert len(rows) == 1
    assert rows[0]["plate_text"] == "7ABC123"
    catalog = store.list_plates()
    assert len(catalog) == 1
    assert catalog[0]["jurisdiction"]["code"] == "CA"
    assert catalog[0]["bestEventId"] == event.id
    assert catalog[0]["appearanceCount"] == 1
    progress.hits.append(
        {
            "cropId": "crop2",
            "text": "XXXXXX",
            "region": None,
            "ocrConfidence": 0.7,
            "detectConfidence": 0.6,
            "elapsedSec": 8.0,
            "camera": "front",
            "cameraLabel": "Front",
            "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "width": 100, "height": 40},
        }
    )
    persist_scan(event, progress)
    catalog = store.list_plates()
    by_text = {item["text"]: item for item in catalog}
    assert by_text["7ABC123"]["jurisdiction"]["code"] == "CA"
    assert by_text["XXXXXX"]["jurisdiction"] is None
    assert {item["text"] for item in catalog} == {"7ABC123", "XXXXXX"}
    assert rows[0]["day"] == "2026-08-21"
    assert rows[0]["camera"] == "front"
    assert rows[0]["latitude"] == 30.2672
    assert rows[0]["longitude"] == -97.7431
    assert rows[0]["bbox_x1"] == 10
    assert rows[0]["city"] == "Austin"
    saved = payload_from_store(event.id)
    assert saved is not None
    assert saved["complete"] is True
    assert saved["plates"][0]["hits"][0]["bbox"]["width"] == 100
    again = start_plate_scan(event, blocking=True)
    assert again["complete"] is True
    assert again["plates"][0]["text"] == "7ABC123"


def test_plate_dossier_groups_every_clip(tmp_path: Path) -> None:
    reset_for_tests()
    store = ClipIndex(tmp_path / "clip-index.sqlite3")
    configure_plates(store)
    first = _dummy_event()
    first.latitude = 30.2672
    first.longitude = -97.7431
    first.city = "Austin"
    first.street = "S Congress Ave"
    progress = PlateProgress(state="complete", event_id=first.id)
    progress.hits = [
        {
            "cropId": "crop1",
            "text": "7ABC123",
            "region": "US",
            "ocrConfidence": 0.91,
            "detectConfidence": 0.8,
            "elapsedSec": 4.0,
            "camera": "front",
            "cameraLabel": "Front",
            "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "width": 100, "height": 40},
        }
    ]
    persist_scan(first, progress)
    second = Event(
        id="def456",
        kind="sentry",
        folder=None,
        start=datetime(2026, 8, 22, 9, 15, 0),
        cameras={},
        source_path=Path("d:/"),
        source_label="D",
        city="Cupertino",
        street="N De Anza Blvd",
        latitude=37.3318,
        longitude=-122.0312,
    )
    later = PlateProgress(state="complete", event_id=second.id)
    later.hits = [
        {
            "cropId": "crop3",
            "text": "7ABC123",
            "region": "US",
            "ocrConfidence": 0.88,
            "detectConfidence": 0.7,
            "elapsedSec": 2.0,
            "camera": "front",
            "cameraLabel": "Front",
            "bbox": {"x1": 12, "y1": 22, "x2": 112, "y2": 62, "width": 100, "height": 40},
        }
    ]
    persist_scan(second, later)
    assert plate_dossier("nosuch", None) is None
    dossier = plate_dossier("7abc-123", None)
    assert dossier is not None
    assert dossier["text"] == "7ABC123"
    assert dossier["eventCount"] == 2
    assert dossier["appearanceCount"] == 2
    assert [item["eventId"] for item in dossier["events"]] == ["abc123", "def456"]
    assert dossier["events"][0]["city"] == "Austin"
    assert dossier["events"][0]["clock"] == "17:26"
    assert dossier["events"][1]["city"] == "Cupertino"
    assert dossier["events"][1]["clock"] == "09:15"
    assert len(dossier["points"]) == 2
    clocks = [sight["clock"] for point in dossier["points"] for sight in point["sightings"]]
    assert "17:26" in clocks
    assert "09:15" in clocks


def test_plate_dossier_route(tmp_path: Path) -> None:
    reset_for_tests()
    root = tmp_path / "TeslaCam"
    folder = root / "SavedClips" / "2023-08-21_15-30-45"
    _touch(folder / "2023-08-21_15-30-45-front.mp4")
    config = AppConfig(
        sources=[root],
        output_dir=tmp_path / "shots",
        host="127.0.0.1",
        port=8765,
        path=tmp_path / "config.json",
    )
    client = TestClient(create_app(config, background_scan=False))
    missing = client.get("/api/plates/NOSUCH")
    assert missing.status_code == 404
    event_id = client.get("/api/days/2023-08-21").json()["events"][0]["id"]
    from app.main import get_event

    event = get_event(event_id)
    progress = PlateProgress(state="complete", event_id=event.id)
    progress.hits = [
        {
            "cropId": "crop1",
            "text": "7ABC123",
            "region": "US",
            "ocrConfidence": 0.91,
            "detectConfidence": 0.8,
            "elapsedSec": 4.0,
            "camera": "front",
            "cameraLabel": "Front",
            "bbox": {"x1": 10, "y1": 20, "x2": 110, "y2": 60, "width": 100, "height": 40},
        }
    ]
    persist_scan(event, progress)
    found = client.get("/api/plates/7ABC123")
    assert found.status_code == 200
    body = found.json()
    assert body["text"] == "7ABC123"
    assert body["eventCount"] == 1
    assert body["events"][0]["eventId"] == event_id
    assert body["events"][0]["available"] is True
    assert body["events"][0]["clip"] is not None
    assert body["events"][0]["clip"]["videoUrl"].endswith("/front/segments/0")
    catalog = client.get("/api/plates")
    assert catalog.status_code == 200
    assert catalog.json()["total"] >= 1


def test_second_event_is_queued(monkeypatch) -> None:
    reset_for_tests()
    started = threading.Event()
    release = threading.Event()

    def fake_scan(event, progress, engine_factory=None) -> None:
        started.set()
        release.wait(timeout=2)
        progress.state = "complete"
        progress.complete = True
        progress.plates = []
        progress.message = "Found 0 plates."

    monkeypatch.setattr("app.plates.scan_event", fake_scan)
    first = start_plate_scan(_dummy_event(), blocking=False)
    assert first["state"] in {"loading", "running"}
    assert started.wait(timeout=1)
    other = Event(
        id="other456",
        kind="recent",
        folder=None,
        start=datetime(2026, 8, 21, 18, 0, 0),
        cameras={},
        source_path=Path("d:/"),
        source_label="D",
    )
    queued = start_plate_scan(other, blocking=False)
    assert queued["state"] == "queued"
    release.set()
    reset_for_tests()
