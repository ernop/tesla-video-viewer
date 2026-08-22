from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROBE_TIMEOUT_SEC = 20
EXTRACT_TIMEOUT_SEC = 60


class MediaError(RuntimeError):
    pass


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise MediaError(f"{name} is not on PATH.")
    return path


def probe_duration(path: Path) -> float:
    ffprobe = require_tool("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
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
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffprobe timed out for {path.name}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "unknown ffprobe error").strip()
        raise MediaError(f"ffprobe failed for {path.name}: {err}")
    text = completed.stdout.strip()
    try:
        duration = float(text)
    except ValueError as exc:
        raise MediaError(f"ffprobe returned a non-numeric duration for {path.name}: {text!r}") from exc
    if duration <= 0:
        raise MediaError(f"ffprobe returned a non-positive duration for {path.name}: {duration}")
    return duration


def extract_png(source: Path, offset_sec: float, dest: Path) -> None:
    if offset_sec < 0:
        raise MediaError("Screenshot offset is negative.")
    ffmpeg = require_tool("ffmpeg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{offset_sec:.3f}",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-update",
        "1",
        str(dest),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=EXTRACT_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffmpeg timed out writing {dest.name}") from exc
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        err = (completed.stderr or completed.stdout or "ffmpeg wrote no PNG").strip()
        raise MediaError(f"ffmpeg failed for {source.name} at {offset_sec:.3f}s: {err}")
