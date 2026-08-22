from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_playback_stitch_runs_real_tesla_timeline() -> None:
    node = shutil.which("node")
    assert node, "node is required to simulate the viewer stitch"
    completed = subprocess.run(
        [node, str(ROOT / "tests" / "test_playback.js")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "4 checks passed" in completed.stdout
