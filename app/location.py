from __future__ import annotations

import json
import logging
import math
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.scan import Event

LOGGER = logging.getLogger("tesla-video-viewer.location")

PROBE_TIMEOUT_SEC = 12
SEI_READ_LIMIT = 32 * 1024 * 1024


@dataclass
class ClipLocation:
    city: str | None = None
    street: str | None = None
    reason: str | None = None
    timestamp: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    source: str | None = None

    @property
    def label(self) -> str | None:
        return self.reason or self.city or self.timestamp


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def parse_coord(value: object, *, kind: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if kind == "lat" and not -90.0 <= number <= 90.0:
        return None
    if kind == "lon" and not -180.0 <= number <= 180.0:
        return None
    if abs(number) < 1e-6:
        return None
    return number


def read_event_sidecar(folder: Path) -> ClipLocation:
    sidecar = folder / "event.json"
    empty = ClipLocation()
    if not sidecar.is_file():
        return empty
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        LOGGER.warning("Ignore malformed event.json at %s: %s", sidecar, exc)
        return empty
    if not isinstance(data, dict):
        LOGGER.warning("Ignore non-object event.json at %s", sidecar)
        return empty
    city = _clean_text(data.get("city"))
    street = _clean_text(data.get("street"))
    reason = _clean_text(data.get("reason"))
    timestamp = _clean_text(data.get("timestamp"))
    latitude = parse_coord(data.get("est_lat"), kind="lat")
    longitude = parse_coord(data.get("est_lon"), kind="lon")
    source = "event.json" if (city or street or latitude is not None) else None
    return ClipLocation(
        city=city,
        street=street,
        reason=reason,
        timestamp=timestamp,
        latitude=latitude,
        longitude=longitude,
        source=source,
    )


def map_url(latitude: float, longitude: float) -> str:
    return (
        f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}"
        f"#map=17/{latitude}/{longitude}"
    )


def _first_clip_path(event: Event) -> Path | None:
    preferred = (
        "front",
        "back",
        "left_repeater",
        "right_repeater",
        "left_pillar",
        "right_pillar",
    )
    for name in preferred:
        track = event.cameras.get(name)
        if track and track.segments:
            path = track.segments[0].path
            if path.is_file():
                return path
    for track in event.cameras.values():
        if track.segments and track.segments[0].path.is_file():
            return track.segments[0].path
    return None


def probe_mp4_place(path: Path) -> tuple[str | None, str | None]:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream_tags=title,comment:format_tags=title,comment",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    if completed.returncode != 0 or not completed.stdout.strip():
        return None, None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, None
    tags: dict[str, object] = {}
    format_tags = (payload.get("format") or {}).get("tags") or {}
    if isinstance(format_tags, dict):
        tags.update(format_tags)
    for stream in payload.get("streams") or []:
        stream_tags = (stream or {}).get("tags") or {}
        if isinstance(stream_tags, dict):
            tags.update(stream_tags)
    return _clean_text(tags.get("title")), _clean_text(tags.get("comment"))


def _find_mdat(fp, limit: int) -> tuple[int, int]:
    fp.seek(0)
    while fp.tell() < limit:
        header = fp.read(8)
        if len(header) < 8:
            raise RuntimeError("mdat atom not found")
        size32, atom_type = struct.unpack(">I4s", header)
        if size32 == 1:
            large = fp.read(8)
            if len(large) != 8:
                raise RuntimeError("truncated extended atom size")
            atom_size = struct.unpack(">Q", large)[0]
            header_size = 16
        else:
            atom_size = size32 if size32 else 0
            header_size = 8
        if atom_type == b"mdat":
            payload_size = atom_size - header_size if atom_size else 0
            return fp.tell(), payload_size
        if atom_size < header_size:
            raise RuntimeError("invalid MP4 atom size")
        fp.seek(atom_size - header_size, 1)
    raise RuntimeError("mdat atom not found")


def _strip_emulation_prevention_bytes(data: bytes) -> bytes:
    stripped = bytearray()
    zero_count = 0
    for byte in data:
        if zero_count >= 2 and byte == 0x03:
            zero_count = 0
            continue
        stripped.append(byte)
        zero_count = zero_count + 1 if byte == 0 else 0
    return bytes(stripped)


def _varint(buf: bytes, index: int) -> tuple[int, int] | None:
    value = 0
    shift = 0
    while index < len(buf):
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7
        if shift > 63:
            return None
    return None


def _proto_double(buf: bytes, field: int) -> float | None:
    index = 0
    while index < len(buf):
        parsed = _varint(buf, index)
        if parsed is None:
            return None
        key, index = parsed
        number = key >> 3
        wire = key & 7
        if wire == 0:
            parsed = _varint(buf, index)
            if parsed is None:
                return None
            index = parsed[1]
        elif wire == 1:
            if index + 8 > len(buf):
                return None
            if number == field:
                return struct.unpack("<d", buf[index : index + 8])[0]
            index += 8
        elif wire == 2:
            parsed = _varint(buf, index)
            if parsed is None:
                return None
            length, index = parsed
            index += length
        elif wire == 5:
            index += 4
        else:
            return None
    return None


def first_sei_gps(path: Path) -> tuple[float | None, float | None]:
    try:
        with path.open("rb") as fp:
            offset, size = _find_mdat(fp, SEI_READ_LIMIT)
            fp.seek(offset)
            consumed = 0
            limit = size if size else SEI_READ_LIMIT
            while consumed < min(limit, SEI_READ_LIMIT):
                header = fp.read(4)
                if len(header) < 4:
                    break
                nal_size = struct.unpack(">I", header)[0]
                if nal_size < 2 or nal_size > 2_000_000:
                    if nal_size > 0:
                        fp.seek(min(nal_size, SEI_READ_LIMIT), 1)
                    consumed += 4 + max(nal_size, 0)
                    continue
                first_two = fp.read(2)
                if len(first_two) != 2:
                    break
                if (first_two[0] & 0x1F) != 6 or first_two[1] != 5:
                    fp.seek(nal_size - 2, 1)
                    consumed += 4 + nal_size
                    continue
                rest = fp.read(nal_size - 2)
                consumed += 4 + nal_size
                payload = first_two + rest
                proto: bytes | None = None
                for index in range(3, len(payload) - 1):
                    if payload[index] == 0x42:
                        continue
                    if payload[index] == 0x69 and index > 2:
                        proto = _strip_emulation_prevention_bytes(payload[index + 1 : -1])
                    break
                if not proto:
                    continue
                latitude = parse_coord(_proto_double(proto, 11), kind="lat")
                longitude = parse_coord(_proto_double(proto, 12), kind="lon")
                if latitude is not None and longitude is not None:
                    return latitude, longitude
    except (OSError, RuntimeError, struct.error):
        return None, None
    return None, None


def enrich_event_location(event: Event) -> None:
    if event.city and event.street and event.latitude is not None and event.longitude is not None:
        return
    path = _first_clip_path(event)
    if path is None:
        return
    if not event.city or not event.street:
        city, street = probe_mp4_place(path)
        if city and not event.city:
            event.city = city
            event.location_source = event.location_source or "mp4"
        if street and not event.street:
            event.street = street
            event.location_source = event.location_source or "mp4"
    if event.latitude is not None and event.longitude is not None:
        return
    latitude, longitude = first_sei_gps(path)
    if latitude is None or longitude is None:
        return
    event.latitude = latitude
    event.longitude = longitude
    event.location_source = "sei"
