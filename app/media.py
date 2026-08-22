from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

PROBE_TIMEOUT_SEC = 20
EXTRACT_TIMEOUT_SEC = 60
JPEG_SEQUENCE_TIMEOUT_SEC = 180


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


def probe_video_size(path: Path) -> tuple[int, int]:
    ffprobe = require_tool("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=p=0",
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
        raise MediaError(f"ffprobe timed out reading size for {path.name}") from exc
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "unknown ffprobe error").strip()
        raise MediaError(f"ffprobe failed reading size for {path.name}: {err}")
    parts = completed.stdout.strip().split(",")
    if len(parts) != 2:
        raise MediaError(f"ffprobe returned a bad size for {path.name}: {completed.stdout!r}")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise MediaError(f"ffprobe returned a non-integer size for {path.name}: {completed.stdout!r}") from exc
    if width < 2 or height < 2:
        raise MediaError(f"ffprobe returned a tiny frame for {path.name}: {width}x{height}")
    return width, height


def clamp_region(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    frame_w: int,
    frame_h: int,
    pad: int = 8,
) -> tuple[int, int, int, int]:
    left = max(0, int(x1) - pad)
    top = max(0, int(y1) - pad)
    right = min(int(frame_w), int(x2) + pad)
    bottom = min(int(frame_h), int(y2) + pad)
    width = max(2, right - left)
    height = max(2, bottom - top)
    if width % 2:
        if left + width + 1 <= frame_w:
            width += 1
        elif width > 2:
            width -= 1
    if height % 2:
        if top + height + 1 <= frame_h:
            height += 1
        elif height > 2:
            height -= 1
    if left + width > frame_w:
        left = max(0, frame_w - width)
    if top + height > frame_h:
        top = max(0, frame_h - height)
    return left, top, width, height


def extract_png_region(
    source: Path,
    offset_sec: float,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    dest: Path,
    pad: int = 8,
) -> None:
    if offset_sec < 0:
        raise MediaError("Screenshot offset is negative.")
    frame_w, frame_h = probe_video_size(source)
    left, top, width, height = clamp_region(x1, y1, x2, y2, frame_w, frame_h, pad)
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
        "-vf",
        f"crop={width}:{height}:{left}:{top}",
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
        raise MediaError(f"ffmpeg timed out cropping {dest.name}") from exc
    if completed.returncode != 0 or not dest.is_file() or dest.stat().st_size == 0:
        err = (completed.stderr or completed.stdout or "ffmpeg wrote no PNG").strip()
        raise MediaError(f"ffmpeg failed cropping {source.name} at {offset_sec:.3f}s: {err}")


def extract_jpeg_sequence(source: Path, dest_dir: Path, fps: float = 1.0) -> list[Path]:
    if fps <= 0:
        raise MediaError("Frame sample rate must be positive.")
    ffmpeg = require_tool("ffmpeg")
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / "f_%06d.jpg"
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps={fps}",
        "-q:v",
        "3",
        str(pattern),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=JPEG_SEQUENCE_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"ffmpeg timed out extracting frames from {source.name}") from exc
    files = sorted(dest_dir.glob("f_*.jpg"))
    if completed.returncode != 0 and not files:
        err = (completed.stderr or completed.stdout or "ffmpeg wrote no JPEGs").strip()
        raise MediaError(f"ffmpeg failed extracting frames from {source.name}: {err}")
    return files
