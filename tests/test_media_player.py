from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppConfig
from app.main import MEDIA_PLAYER_DIR, create_app

INDEX = Path(__file__).resolve().parent.parent / "web" / "index.html"


def _client(tmp_path: Path) -> TestClient:
    config = AppConfig(
        sources=[],
        output_dir=tmp_path / "shots",
        host="127.0.0.1",
        port=8765,
        path=tmp_path / "config.json",
    )
    return TestClient(create_app(config, background_scan=False))


def test_the_page_loads_the_shared_media_player_before_its_own_files() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert html.index('href="/media-player/media-player.css"') < html.index('href="style.css')
    assert html.index('src="/media-player/media-player.js"') < html.index('src="app.js')


def test_the_viewer_has_no_controls_of_its_own() -> None:
    html = INDEX.read_text(encoding="utf-8")
    for old in ('id="scrubber"', 'id="btn-play"', 'id="btn-back-10"', 'id="scrub-readout"'):
        assert old not in html


def test_the_copy_is_the_librarys_files_unedited() -> None:
    checksums = {}
    for line in (MEDIA_PLAYER_DIR / "media-player.sha256").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        checksums[name.lstrip("*")] = digest
    assert sorted(checksums) == ["media-player.css", "media-player.js"]
    for name, digest in checksums.items():
        # Git may check text files out with CRLF line endings on Windows.
        data = (MEDIA_PLAYER_DIR / name).read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(data).hexdigest() == digest, (
            f"web/media-player/{name} was edited: change the media-player library, "
            "then run its copy-into.sh web/media-player from here"
        )


def test_the_copy_is_served_for_checking_on_every_load(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for name in ("media-player.js", "media-player.css"):
        found = client.get(f"/media-player/{name}")
        assert found.status_code == 200
        assert found.headers["cache-control"] == "no-cache"
        assert found.content == (MEDIA_PLAYER_DIR / name).read_bytes()
