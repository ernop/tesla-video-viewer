from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = "config.json"


@dataclass
class AppConfig:
    sources: list[Path] = field(default_factory=list)
    output_dir: Path = Path()
    host: str = "127.0.0.1"
    port: int = 8765
    path: Path = Path(CONFIG_NAME)

    def to_json(self) -> dict[str, object]:
        return {
            "sources": [str(path) for path in self.sources],
            "output_dir": str(self.output_dir),
            "host": self.host,
            "port": self.port,
        }


def default_config_path() -> Path:
    env = os.environ.get("TESLA_VIDEO_VIEWER_CONFIG", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd() / CONFIG_NAME


def _parse_dir(value: object, field_name: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string path.")
    text = value.strip()
    if not text:
        raise ValueError(f"{field_name} must not be blank.")
    return Path(text).expanduser()


def _parse_sources(raw: dict[str, object]) -> list[Path]:
    has_sources = "sources" in raw
    video_root = raw.get("video_root")
    video_set = isinstance(video_root, str) and bool(video_root.strip())
    if has_sources and video_set:
        raise ValueError("Config has both sources and video_root. Keep sources only.")
    if has_sources:
        value = raw.get("sources")
        if not isinstance(value, list):
            raise ValueError("sources must be an array of folder paths.")
        paths: list[Path] = []
        seen: set[str] = set()
        for item in value:
            path = _parse_dir(item, "sources[]")
            key = str(path).casefold()
            if key in seen:
                raise ValueError(f"Duplicate source folder: {path}")
            seen.add(key)
            paths.append(path)
        return paths
    if video_root is None or video_root == "":
        return []
    return [_parse_dir(video_root, "video_root")]


def _parse_required_dir(value: object, fallback: Path) -> Path:
    if value is None or value == "":
        return fallback
    return _parse_dir(value, "output_dir")


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    raw: dict[str, object] = {}
    if config_path.is_file():
        try:
            loaded = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Config file is not valid JSON: {config_path}") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"Config file must be a JSON object: {config_path}")
        raw = loaded

    output_fallback = Path.cwd() / "screenshots"
    sources = _parse_sources(raw) if raw else []
    output_dir = _parse_required_dir(raw.get("output_dir"), output_fallback)
    host = raw.get("host", "127.0.0.1")
    port = raw.get("port", 8765)
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host must be a non-empty string.")
    if not isinstance(port, int) or isinstance(port, bool) or port < 1 or port > 65535:
        raise ValueError("port must be an integer from 1 to 65535.")
    return AppConfig(
        sources=sources,
        output_dir=output_dir,
        host=host.strip(),
        port=port,
        path=config_path,
    )


def save_config(config: AppConfig) -> None:
    config.path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config.to_json(), indent=2) + "\n"
    config.path.write_text(text, encoding="utf-8")
