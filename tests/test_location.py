from __future__ import annotations

import json
from pathlib import Path

from app.location import parse_coord, read_event_sidecar


def test_parse_coord_rejects_junk() -> None:
    assert parse_coord("30.2672", kind="lat") == 30.2672
    assert parse_coord("-97.7431", kind="lon") == -97.7431
    assert parse_coord("91", kind="lat") is None
    assert parse_coord("0", kind="lat") is None
    assert parse_coord("not-a-number", kind="lon") is None
    assert parse_coord("", kind="lat") is None


def test_read_event_sidecar_keeps_place_and_pin(tmp_path: Path) -> None:
    folder = tmp_path / "SavedClips" / "2023-08-21_15-30-45"
    folder.mkdir(parents=True)
    (folder / "event.json").write_text(
        json.dumps(
            {
                "timestamp": "2023-08-21T15:30:40",
                "city": "Austin",
                "street": "S Congress Ave",
                "est_lat": "30.2672",
                "est_lon": "-97.7431",
                "reason": "user_interaction_dashcam_launcher_action_tapped",
                "camera": "0",
            }
        ),
        encoding="utf-8",
    )
    meta = read_event_sidecar(folder)
    assert meta.city == "Austin"
    assert meta.street == "S Congress Ave"
    assert meta.latitude == 30.2672
    assert meta.longitude == -97.7431
    assert meta.source == "event.json"
    assert meta.label == "user_interaction_dashcam_launcher_action_tapped"


def test_read_event_sidecar_blank_street_is_omitted(tmp_path: Path) -> None:
    folder = tmp_path / "SentryClips" / "2023-08-21_15-30-45"
    folder.mkdir(parents=True)
    (folder / "event.json").write_text(
        '{"city":"Mountain View","street":"","est_lat":"37.3724","est_lon":"-122.088","reason":"sentry_aware_object_detection"}',
        encoding="utf-8",
    )
    meta = read_event_sidecar(folder)
    assert meta.city == "Mountain View"
    assert meta.street is None
    assert meta.latitude == 37.3724
    assert meta.longitude == -122.088


def test_encrypted_sidecar_is_ignored(tmp_path: Path) -> None:
    folder = tmp_path / "SavedClips" / "2023-08-21_15-30-45"
    folder.mkdir(parents=True)
    (folder / "event.json").write_bytes(b"\x00\x00_CONSOLE\xff")
    meta = read_event_sidecar(folder)
    assert meta.city is None
    assert meta.latitude is None
    assert meta.source is None
