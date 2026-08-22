from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import create_app


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_library_and_day_routes(tmp_path: Path) -> None:
    root = tmp_path / "TeslaCam"
    folder = root / "SavedClips" / "2023-08-21_15-30-45"
    _touch(folder / "2023-08-21_15-30-45-front.mp4")
    _touch(folder / "2023-08-21_15-30-45-back.mp4")
    _touch(folder / "2023-08-21_15-30-45-left_repeater.mp4")
    _touch(folder / "2023-08-21_15-30-45-right_repeater.mp4")
    config = AppConfig(
        sources=[root],
        output_dir=tmp_path / "shots",
        host="127.0.0.1",
        port=8765,
        path=tmp_path / "config.json",
    )
    client = TestClient(create_app(config, background_scan=False))
    home = client.get("/")
    assert home.status_code == 200
    assert b"Tesla video viewer" in home.content
    library = client.get("/api/library").json()
    assert library["clipCount"] == 4
    assert library["sources"][0]["available"] is True
    assert library["days"][0]["date"] == "2023-08-21"
    day = client.get("/api/days/2023-08-21").json()
    assert day["eventCount"] == 1
    event_id = day["events"][0]["id"]
    event = client.get(f"/api/events/{event_id}").json()
    assert event["layout"] == "four"
    assert {cam["id"] for cam in event["cameras"]} == {
        "front",
        "back",
        "left_repeater",
        "right_repeater",
    }
    missing = client.get("/api/days/1999-01-01")
    assert missing.status_code == 404
    scan = client.get("/api/scan").json()
    assert scan["state"] == "complete"
    assert scan["clipsIndexed"] == 4
    assert "elapsedSec" in scan
    assert "recent" in scan


def test_put_rejected_while_scan_running(tmp_path: Path) -> None:
    import app.main as mainmod

    root = tmp_path / "TeslaCam"
    _touch(root / "2023-08-21_15-30-45-front.mp4")
    config = AppConfig(
        sources=[root],
        output_dir=tmp_path / "shots",
        host="127.0.0.1",
        port=8765,
        path=tmp_path / "config.json",
    )
    client = TestClient(create_app(config, background_scan=False))
    acquired = mainmod._scan_guard.acquire(blocking=False)
    assert acquired is True
    try:
        response = client.put(
            "/api/config",
            json={"sources": [str(root)], "output_dir": str(tmp_path / "shots")},
        )
        assert response.status_code == 409
    finally:
        mainmod._scan_guard.release()
