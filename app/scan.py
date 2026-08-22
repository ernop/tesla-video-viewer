from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from app.location import read_event_sidecar

LOGGER = logging.getLogger("tesla-video-viewer.scan")

CLIP_NAME = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<time>\d{2}-\d{2}-\d{2})-(?P<camera>.+)\.mp4$",
    re.IGNORECASE,
)

# Tesla writes one-minute files. A gap larger than this starts a new event.
ADJACENT_GAP = timedelta(seconds=90)
DEFAULT_SEGMENT_SEC = 60.0

CAMERA_ALIASES = {
    "rear": "back",
}

CAMERA_LABELS = {
    "front": "Front",
    "back": "Rear",
    "left_repeater": "Left repeater",
    "right_repeater": "Right repeater",
    "left_pillar": "Left pillar",
    "right_pillar": "Right pillar",
}

LAYOUT_SIX = [
    "left_repeater",
    "front",
    "right_repeater",
    "left_pillar",
    "back",
    "right_pillar",
]
LAYOUT_FOUR = ["left_repeater", "front", "right_repeater", "back"]


@dataclass
class ClipFile:
    path: Path
    stamp: datetime
    camera: str
    kind: str
    event_dir: str | None
    duration_sec: float = DEFAULT_SEGMENT_SEC
    duration_source: str = "tesla-minute-default"


@dataclass
class Segment:
    index: int
    stamp: datetime
    path: Path
    duration_sec: float
    duration_source: str


@dataclass
class CameraTrack:
    camera: str
    label: str
    segments: list[Segment]


@dataclass
class Event:
    id: str
    kind: str
    folder: Path | None
    start: datetime
    cameras: dict[str, CameraTrack]
    source_path: Path
    source_label: str
    label: str | None = None
    city: str | None = None
    street: str | None = None
    reason: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    location_source: str | None = None
    assumed_duration: bool = True

    def camera_names(self) -> list[str]:
        names = list(self.cameras.keys())
        known = [name for name in LAYOUT_SIX if name in self.cameras]
        extra = sorted(name for name in names if name not in LAYOUT_SIX)
        return known + extra

    def layout(self) -> str:
        names = set(self.cameras)
        if names - set(LAYOUT_SIX):
            return "free"
        if {"left_pillar", "right_pillar"} & names:
            return "six"
        if {"front", "back", "left_repeater", "right_repeater"} <= names:
            return "four"
        return "free"

    def stamps(self) -> list[datetime]:
        found: set[datetime] = set()
        for track in self.cameras.values():
            for segment in track.segments:
                found.add(segment.stamp)
        return sorted(found)

    def duration_sec(self) -> float:
        stamps = self.stamps()
        if not stamps:
            return 0.0
        last = stamps[-1]
        last_durations: list[float] = []
        for track in self.cameras.values():
            for segment in track.segments:
                if segment.stamp == last:
                    last_durations.append(segment.duration_sec)
        last_len = max(last_durations) if last_durations else DEFAULT_SEGMENT_SEC
        return (last - self.start).total_seconds() + last_len

    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.duration_sec())

    def segment_for(self, camera: str, elapsed_sec: float) -> tuple[Segment, float] | None:
        track = self.cameras.get(camera)
        if track is None:
            return None
        if elapsed_sec < 0:
            return None
        segments = track.segments
        for index, segment in enumerate(segments):
            start = (segment.stamp - self.start).total_seconds()
            local = elapsed_sec - start
            if local < -1e-3:
                continue
            nxt = segments[index + 1] if index + 1 < len(segments) else None
            if nxt is not None:
                next_start = (nxt.stamp - self.start).total_seconds()
                if elapsed_sec >= next_start:
                    continue
            if local < segment.duration_sec:
                return segment, max(0.0, local)
        if segments:
            last = segments[-1]
            local = elapsed_sec - (last.stamp - self.start).total_seconds()
            if 0 <= local <= last.duration_sec + 0.5:
                return last, min(max(local, 0.0), max(last.duration_sec - 0.001, 0.0))
        return None


@dataclass
class DaySummary:
    date: str
    event_ids: list[str]
    event_count: int
    duration_sec: float
    times: list[str]


@dataclass
class SourceScan:
    path: Path
    label: str
    available: bool
    clip_count: int
    skipped: int
    error: str | None = None


@dataclass
class Library:
    sources: list[SourceScan]
    events: dict[str, Event] = field(default_factory=dict)
    days: dict[str, DaySummary] = field(default_factory=dict)
    clip_count: int = 0
    skipped: int = 0

    def span(self) -> tuple[datetime, datetime] | None:
        if not self.events:
            return None
        starts = [event.start for event in self.events.values()]
        ends = [event.end() for event in self.events.values()]
        return min(starts), max(ends)


def camera_label(camera: str) -> str:
    return CAMERA_LABELS.get(camera, camera.replace("_", " "))


def normalize_camera(raw: str) -> str:
    name = raw.strip().lower()
    return CAMERA_ALIASES.get(name, name)


def parse_clip_name(name: str) -> tuple[datetime, str] | None:
    match = CLIP_NAME.match(name)
    if match is None:
        return None
    stamp_text = f"{match.group('date')} {match.group('time').replace('-', ':')}"
    try:
        stamp = datetime.strptime(stamp_text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    camera = normalize_camera(match.group("camera"))
    if not camera:
        return None
    return stamp, camera


def classify_path(path: Path, root: Path) -> tuple[str, str | None]:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    parts = [part.lower() for part in relative.parts]
    event_dir: str | None = None
    kind = "other"
    if "savedclips" in parts:
        kind = "saved"
        event_dir = _event_dir_of(relative, "savedclips")
    elif "sentryclips" in parts:
        kind = "sentry"
        event_dir = _event_dir_of(relative, "sentryclips")
    elif "recentclips" in parts:
        kind = "recent"
    return kind, event_dir


def _event_dir_of(relative: Path, folder_name: str) -> str | None:
    parts = relative.parts
    lowered = [part.lower() for part in parts]
    try:
        index = lowered.index(folder_name)
    except ValueError:
        return None
    if index + 1 >= len(parts) - 1:
        return None
    return str(Path(*parts[: index + 2]))


def source_label_for(path: Path, all_paths: list[Path]) -> str:
    if not path.name:
        return str(path)
    name_hits = [item for item in all_paths if item.name.casefold() == path.name.casefold()]
    if len(name_hits) > 1:
        return str(path)
    drive = path.drive.rstrip(":\\/")
    if drive:
        return f"{drive}: {path.name}"
    return path.name


def _event_id(source_key: str, kind: str, key: str, start: datetime) -> str:
    payload = f"{source_key}|{kind}|{key}|{start.strftime('%Y-%m-%d_%H-%M-%S')}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


KNOWN_SKIP_NAMES = {"event.mp4"}


def iter_clip_files(
    root: Path,
    skip_dirs: set[Path] | None = None,
    seen_files: set[Path] | None = None,
):
    skip = {path.resolve() for path in (skip_dirs or set())}
    seen = seen_files if seen_files is not None else set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        resolved_parent = path.parent.resolve()
        if any(resolved_parent == skipped or skipped in resolved_parent.parents for skipped in skip):
            continue
        parsed = parse_clip_name(path.name)
        if parsed is None:
            if path.suffix.lower() == ".mp4":
                seen.add(resolved)
                yield path, None
            continue
        seen.add(resolved)
        stamp, camera = parsed
        kind, event_dir = classify_path(path, root)
        yield path, ClipFile(
            path=resolved,
            stamp=stamp,
            camera=camera,
            kind=kind,
            event_dir=event_dir,
        )


def collect_clips(
    root: Path,
    skip_dirs: set[Path] | None = None,
    seen_files: set[Path] | None = None,
) -> tuple[list[ClipFile], int]:
    clips: list[ClipFile] = []
    skipped = 0
    for path, clip in iter_clip_files(root, skip_dirs=skip_dirs, seen_files=seen_files):
        if clip is None:
            skipped += 1
            if path.name.lower() not in KNOWN_SKIP_NAMES:
                LOGGER.info("Skip non-Tesla mp4 name: %s", path)
            continue
        clips.append(clip)
    return clips, skipped


def _tracks_from_clips(clips: list[ClipFile]) -> dict[str, CameraTrack]:
    by_camera: dict[str, list[ClipFile]] = {}
    for clip in clips:
        by_camera.setdefault(clip.camera, []).append(clip)
    tracks: dict[str, CameraTrack] = {}
    for camera, camera_clips in by_camera.items():
        camera_clips.sort(key=lambda item: (item.stamp, str(item.path)))
        segments = [
            Segment(
                index=index,
                stamp=item.stamp,
                path=item.path,
                duration_sec=item.duration_sec,
                duration_source=item.duration_source,
            )
            for index, item in enumerate(camera_clips)
        ]
        tracks[camera] = CameraTrack(
            camera=camera,
            label=camera_label(camera),
            segments=segments,
        )
    return tracks


def _event_from_clips(
    kind: str,
    key: str,
    clips: list[ClipFile],
    folder: Path | None,
    source_path: Path,
    source_label: str,
) -> Event:
    clips_sorted = sorted(clips, key=lambda item: item.stamp)
    start = clips_sorted[0].stamp
    source_key = str(source_path.resolve())
    event_id = _event_id(source_key, kind, key, start)
    meta = read_event_sidecar(folder) if folder is not None else None
    return Event(
        id=event_id,
        kind=kind,
        folder=folder,
        start=start,
        cameras=_tracks_from_clips(clips_sorted),
        source_path=source_path,
        source_label=source_label,
        label=None if meta is None else meta.label,
        city=None if meta is None else meta.city,
        street=None if meta is None else meta.street,
        reason=None if meta is None else meta.reason,
        latitude=None if meta is None else meta.latitude,
        longitude=None if meta is None else meta.longitude,
        location_source=None if meta is None else meta.source,
        assumed_duration=True,
    )


def _cluster_adjacent(clips: list[ClipFile]) -> list[list[ClipFile]]:
    if not clips:
        return []
    ordered = sorted(clips, key=lambda item: item.stamp)
    groups: list[list[ClipFile]] = []
    current = [ordered[0]]
    last_stamp = ordered[0].stamp
    for clip in ordered[1:]:
        if clip.stamp - last_stamp <= ADJACENT_GAP:
            current.append(clip)
            if clip.stamp > last_stamp:
                last_stamp = clip.stamp
            continue
        groups.append(current)
        current = [clip]
        last_stamp = clip.stamp
    groups.append(current)
    return groups


def build_events(root: Path, clips: list[ClipFile], source_label: str) -> list[Event]:
    grouped: dict[tuple[str, str], list[ClipFile]] = {}
    loose: dict[str, list[ClipFile]] = {}
    for clip in clips:
        if clip.event_dir:
            grouped.setdefault((clip.kind, clip.event_dir), []).append(clip)
            continue
        loose.setdefault(clip.kind, []).append(clip)

    events: list[Event] = []
    for (kind, event_dir), group in grouped.items():
        folder = root / event_dir
        if not folder.is_dir():
            folder = group[0].path.parent
        events.append(
            _event_from_clips(kind, event_dir, group, folder, root, source_label)
        )

    for kind, group in loose.items():
        for cluster in _cluster_adjacent(group):
            start = min(item.stamp for item in cluster)
            key = f"{kind}:{start.strftime('%Y-%m-%d_%H-%M-%S')}"
            events.append(_event_from_clips(kind, key, cluster, None, root, source_label))

    events.sort(key=lambda item: item.start)
    return events


def _time_label(stamp: datetime) -> str:
    return stamp.strftime("%H:%M")


def _library_from_events(sources: list[SourceScan], events: list[Event], skipped: int) -> Library:
    library = Library(
        sources=sources,
        clip_count=sum(item.clip_count for item in sources),
        skipped=skipped,
    )
    days: dict[str, list[Event]] = {}
    for event in events:
        library.events[event.id] = event
        date_key = event.start.strftime("%Y-%m-%d")
        days.setdefault(date_key, []).append(event)
    for date_key, day_events in days.items():
        day_events.sort(key=lambda item: (item.start, item.source_label, item.kind))
        times: list[str] = []
        for event in day_events:
            stamp = _time_label(event.start)
            if stamp not in times:
                times.append(stamp)
        library.days[date_key] = DaySummary(
            date=date_key,
            event_ids=[event.id for event in day_events],
            event_count=len(day_events),
            duration_sec=sum(event.duration_sec() for event in day_events),
            times=times,
        )
    return library


def library_from_source_clips(
    roots: list[Path],
    clips_by_source: dict[Path, list[ClipFile]],
    skipped_by_source: dict[Path, int] | None = None,
) -> Library:
    labels = {path: source_label_for(path, roots) for path in roots}
    skipped_map = skipped_by_source or {}
    events: list[Event] = []
    scans: list[SourceScan] = []
    skipped_total = 0
    for root in roots:
        label = labels[root]
        clips = clips_by_source.get(root, [])
        skipped = skipped_map.get(root, 0)
        skipped_total += skipped
        if not root.is_dir():
            scans.append(
                SourceScan(
                    path=root,
                    label=label,
                    available=False,
                    clip_count=len(clips),
                    skipped=skipped,
                    error="Folder is not attached.",
                )
            )
        else:
            scans.append(
                SourceScan(
                    path=root,
                    label=label,
                    available=True,
                    clip_count=len(clips),
                    skipped=skipped,
                    error=None,
                )
            )
        if clips:
            events.extend(build_events(root, clips, label))
    events.sort(key=lambda item: (item.start, item.source_label, item.kind))
    return _library_from_events(scans, events, skipped_total)


def build_combined_library(roots: list[Path], skip_dirs: set[Path] | None = None) -> Library:
    seen_files: set[Path] = set()
    clips_by_source: dict[Path, list[ClipFile]] = {}
    skipped_by_source: dict[Path, int] = {}
    for root in roots:
        if not root.is_dir():
            clips_by_source[root] = []
            skipped_by_source[root] = 0
            continue
        clips, skipped = collect_clips(root, skip_dirs=skip_dirs, seen_files=seen_files)
        clips_by_source[root] = clips
        skipped_by_source[root] = skipped
    return library_from_source_clips(roots, clips_by_source, skipped_by_source)


def build_library(root: Path, skip_dirs: set[Path] | None = None) -> Library:
    return build_combined_library([root], skip_dirs=skip_dirs)
