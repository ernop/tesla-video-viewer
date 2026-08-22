from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app
from app.plates import (
    cameras_for_plates,
    group_hits,
    normalize_plate,
    reset_for_tests,
    start_plate_scan,
)
from app.scan import Event


def test_normalize_plate_strips_noise() -> None:
    assert normalize_plate("7abc-123") == "7ABC123"
    assert normalize_plate("  CA 7ABC123 ") == "CA7ABC123"


def test_cameras_for_plates_skips_pillars() -> None:
    names = [
        "left_repeater",
        "front",
        "right_repeater",
        "left_pillar",
        "back",
        "right_pillar",
    ]
    assert cameras_for_plates(names) == ["front", "back", "left_repeater", "right_repeater"]
    assert cameras_for_plates(["left_pillar", "right_pillar"]) == ["left_pillar", "right_pillar"]


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
            },
        ]
    )
    assert [item["text"] for item in plates] == ["7ABC123", "XYZ987"]
    assert plates[0]["count"] == 2
    assert plates[0]["firstElapsedSec"] == 4.0
    assert plates[0]["cropId"] == "strong"
    assert plates[0]["region"] == "US"


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
