from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import load_config, save_config


def test_legacy_video_root_becomes_sources(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"video_root": r"C:\tesla-video", "output_dir": str(tmp_path / "shots"), "host": "127.0.0.1", "port": 8765}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.sources == [Path(r"C:\tesla-video")]
    save_config(config)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert "video_root" not in saved
    assert saved["sources"] == [r"C:\tesla-video"]


def test_both_source_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "video_root": r"C:\tesla-video",
                "sources": [r"D:\TeslaCam"],
                "output_dir": str(tmp_path / "shots"),
                "host": "127.0.0.1",
                "port": 8765,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Keep sources only"):
        load_config(path)
