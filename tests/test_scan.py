from __future__ import annotations

from datetime import datetime
from pathlib import Path

from app.scan import build_library, parse_clip_name


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")


def test_parse_clip_name_accepts_tesla_stamp() -> None:
    parsed = parse_clip_name("2023-08-21_15-30-45-front.mp4")
    assert parsed is not None
    stamp, camera = parsed
    assert stamp == datetime(2023, 8, 21, 15, 30, 45)
    assert camera == "front"


def test_parse_clip_name_maps_rear_to_back() -> None:
    parsed = parse_clip_name("2023-08-21_15-30-45-rear.MP4")
    assert parsed is not None
    assert parsed[1] == "back"


def test_parse_clip_name_rejects_other_mp4() -> None:
    assert parse_clip_name("clip.mp4") is None
    assert parse_clip_name("2023-08-21-front.mp4") is None


def test_saved_folder_is_one_event(tmp_path: Path) -> None:
    root = tmp_path / "TeslaCam"
    folder = root / "SavedClips" / "2023-08-21_15-30-45"
    _touch(folder / "2023-08-21_15-30-45-front.mp4")
    _touch(folder / "2023-08-21_15-30-45-back.mp4")
    _touch(folder / "2023-08-21_15-30-45-left_repeater.mp4")
    _touch(folder / "2023-08-21_15-30-45-right_repeater.mp4")
    _touch(folder / "2023-08-21_15-31-45-front.mp4")
    _touch(folder / "2023-08-21_15-31-45-back.mp4")
    (folder / "event.json").write_text(
        '{"city":"Austin","street":"S Congress Ave","est_lat":"30.2672","est_lon":"-97.7431","reason":"user_interaction"}',
        encoding="utf-8",
    )

    library = build_library(root)
    assert library.clip_count == 6
    assert len(library.events) == 1
    event = next(iter(library.events.values()))
    assert event.kind == "saved"
    assert event.reason == "user_interaction"
    assert event.city == "Austin"
    assert event.street == "S Congress Ave"
    assert event.latitude == 30.2672
    assert event.longitude == -97.7431
    assert event.location_source == "event.json"
    assert event.layout() == "four"
    assert event.duration_sec() == 120.0
    assert library.days["2023-08-21"].times == ["15:30"]


def test_recent_clips_split_on_time_gap(tmp_path: Path) -> None:
    root = tmp_path / "TeslaCam" / "RecentClips"
    _touch(root / "2023-08-22_08-00-00-front.mp4")
    _touch(root / "2023-08-22_08-01-00-front.mp4")
    _touch(root / "2023-08-22_10-00-00-front.mp4")

    library = build_library(root.parent)
    assert len(library.events) == 2
    starts = sorted(event.start for event in library.events.values())
    assert starts[0] == datetime(2023, 8, 22, 8, 0, 0)
    assert starts[1] == datetime(2023, 8, 22, 10, 0, 0)


def test_gap_between_tesla_minutes_has_no_segment(tmp_path: Path) -> None:
    folder = tmp_path / "RecentClips"
    _touch(folder / "2026-08-21_17-26-55-front.mp4")
    _touch(folder / "2026-08-21_17-28-01-front.mp4")
    library = build_library(tmp_path)
    event = next(iter(library.events.values()))
    for track in event.cameras.values():
        track.segments[0].duration_sec = 61.48
        track.segments[1].duration_sec = 62.22
    assert event.segment_for("front", 61.0)[0].stamp == datetime(2026, 8, 21, 17, 26, 55)
    assert event.segment_for("front", 63.0) is None
    later = event.segment_for("front", 66.5)
    assert later is not None
    assert later[0].stamp == datetime(2026, 8, 21, 17, 28, 1)
    assert later[1] == 0.5


def test_overlapping_minute_files_hand_off_at_next_stamp(tmp_path: Path) -> None:
    folder = tmp_path / "SavedClips" / "2026-08-21_17-27-56"
    _touch(folder / "2026-08-21_17-27-56-front.mp4")
    _touch(folder / "2026-08-21_17-28-56-front.mp4")
    library = build_library(tmp_path)
    event = next(iter(library.events.values()))
    for track in event.cameras.values():
        for segment in track.segments:
            segment.duration_sec = 61.0
            segment.duration_source = "ffprobe"
    early = event.segment_for("front", 59.0)
    assert early is not None
    assert early[0].stamp == datetime(2026, 8, 21, 17, 27, 56)
    assert early[1] == 59.0
    overlap = event.segment_for("front", 60.5)
    assert overlap is not None
    assert overlap[0].stamp == datetime(2026, 8, 21, 17, 28, 56)
    assert overlap[1] == 0.5


def test_six_camera_layout_and_segment_lookup(tmp_path: Path) -> None:
    folder = tmp_path / "SavedClips" / "2023-09-01_12-00-00"
    for camera in (
        "front",
        "back",
        "left_repeater",
        "right_repeater",
        "left_pillar",
        "right_pillar",
    ):
        _touch(folder / f"2023-09-01_12-00-00-{camera}.mp4")
        _touch(folder / f"2023-09-01_12-01-00-{camera}.mp4")

    library = build_library(tmp_path)
    event = next(iter(library.events.values()))
    assert event.layout() == "six"
    hit = event.segment_for("front", 75.0)
    assert hit is not None
    segment, offset = hit
    assert segment.stamp == datetime(2023, 9, 1, 12, 1, 0)
    assert offset == 15.0
    assert event.segment_for("front", 200.0) is None


def test_two_sources_merge_into_one_calendar(tmp_path: Path) -> None:
    first = tmp_path / "disk-d"
    second = tmp_path / "tesla-video"
    _touch(first / "SavedClips" / "2023-08-21_15-30-45" / "2023-08-21_15-30-45-front.mp4")
    _touch(second / "SavedClips" / "2023-08-22_09-00-00" / "2023-08-22_09-00-00-front.mp4")
    same = second / "SavedClips" / "2023-08-21_15-30-45"
    _touch(same / "2023-08-21_15-30-45-front.mp4")

    from app.scan import build_combined_library

    library = build_combined_library([first, second])
    assert library.clip_count == 3
    assert len(library.events) == 3
    assert set(library.days) == {"2023-08-21", "2023-08-22"}
    assert library.days["2023-08-21"].event_count == 2
    labels = {event.source_label for event in library.events.values()}
    assert len(labels) == 2


def test_missing_source_keeps_the_attached_one(tmp_path: Path) -> None:
    attached = tmp_path / "tesla-video"
    missing = tmp_path / "not-plugged-in"
    _touch(attached / "2023-08-21_15-30-45-front.mp4")
    from app.scan import build_combined_library

    library = build_combined_library([missing, attached])
    assert library.clip_count == 1
    assert library.sources[0].available is False
    assert library.sources[1].available is True
    assert library.sources[0].error == "Folder is not attached."


def test_sentry_stays_separate_from_saved(tmp_path: Path) -> None:
    saved = tmp_path / "SavedClips" / "2023-08-21_15-30-45"
    sentry = tmp_path / "SentryClips" / "2023-08-21_15-30-45"
    _touch(saved / "2023-08-21_15-30-45-front.mp4")
    _touch(sentry / "2023-08-21_15-30-45-front.mp4")

    library = build_library(tmp_path)
    assert len(library.events) == 2
    kinds = {event.kind for event in library.events.values()}
    assert kinds == {"saved", "sentry"}


def test_binary_event_json_does_not_abort_scan(tmp_path: Path) -> None:
    folder = tmp_path / "SavedClips" / "2023-08-21_15-30-45"
    _touch(folder / "2023-08-21_15-30-45-front.mp4")
    (folder / "event.json").write_bytes(b"\xd9\xffnot-json")
    library = build_library(tmp_path)
    assert library.clip_count == 1
    event = next(iter(library.events.values()))
    assert event.city is None
    assert event.street is None
    assert event.latitude is None
    assert event.longitude is None
