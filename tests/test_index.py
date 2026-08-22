from __future__ import annotations

from pathlib import Path

from app.index_store import ClipIndex
from app.indexer import ScanProgress, library_from_index, scan_into_index


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"abc")


def test_index_persists_and_skips_unchanged(tmp_path: Path) -> None:
    root = tmp_path / "TeslaCam"
    _touch(root / "2023-08-21_15-30-45-front.mp4")
    store = ClipIndex(tmp_path / "clip-index.sqlite3")
    progress = ScanProgress(state="idle")
    scan_into_index(store, [root], set(), progress)
    assert progress.complete is True
    assert progress.clips_indexed == 1
    first = progress.clips_unchanged
    library = library_from_index(store, [root])
    assert library is not None
    assert library.clip_count == 1

    progress2 = ScanProgress(state="idle")
    scan_into_index(store, [root], set(), progress2)
    assert progress2.clips_indexed == 1
    assert progress2.clips_unchanged == 1
    assert first == 0


def test_incomplete_scan_keeps_committed_clips(tmp_path: Path) -> None:
    root = tmp_path / "TeslaCam"
    _touch(root / "2023-08-21_15-30-45-front.mp4")
    store = ClipIndex(tmp_path / "clip-index.sqlite3")
    progress = ScanProgress(state="idle")
    scan_into_index(store, [root], set(), progress)
    _touch(root / "2023-08-21_15-31-45-front.mp4")
    store.next_scan_id()
    # A second file exists on disk but is not pruned because this scan never finished.
    library = library_from_index(store, [root])
    assert library is not None
    assert library.clip_count == 1
