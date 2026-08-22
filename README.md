# Tesla video viewer

[![CI](https://github.com/ernop/tesla-video-viewer/actions/workflows/ci.yml/badge.svg)](https://github.com/ernop/tesla-video-viewer/actions/workflows/ci.yml)

Local web app for Tesla Model Y saved clips. It groups the separate camera
files from one save, lets you move by day and time, and plays every camera
together.

Tesla writes one MP4 per camera. A 2023 Model Y typically has six files per
minute: `front`, `back`, `left_repeater`, `right_repeater`, `left_pillar`,
and `right_pillar`. File names look like:

`2023-08-21_15-30-45-front.mp4`

Point the app at every folder that holds those files. The calendar
merges them. A missing drive stays listed and drops out of the scan
until you attach it and rescan.

## Run

Install Python 3.13+, ffmpeg, and ffprobe. ffmpeg is already on this
workstation.

```powershell
cd C:\proj\tesla-video-viewer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy config.example.json config.json
```

Edit `config.json`:

- `sources`: one or more TeslaCam folders, USB drives, or clip dumps
- `output_dir`: folder for full-resolution PNG dumps

Start the server:

```powershell
python -m app
```

Open http://127.0.0.1:8765/

Add folders in **Folders**. Example sources:

- `C:\tesla-video`
- a TeslaCam folder on `D:`

You can also pass folders on the command line:

```powershell
python -m app --source C:\tesla-video --source D:\TeslaCam --output-dir C:\proj\tesla-video-viewer\screenshots
```

The scan writes a SQLite index next to `config.json` as `clip-index.sqlite3`.
Clip files stay in place. Restarting the server loads that index at once.
A later scan only re-reads files whose size or mtime changed.

Save and scan returns immediately. A status line shows files seen while
the walk runs in the background. If the walk stops early, already written
rows stay in SQLite. The next scan continues from those rows and only
removes missing files after it finishes a source folder.

## Use

1. Days with clips are amber on the calendar. Empty days stay dark.
2. Open a day. The 24-hour rail shows clip times. The list shows each event.
3. Open an event. All cameras play on one clock.
4. Click a camera to enlarge it. Click **Show all cameras** to restore the grid.
5. **Screenshot this camera** writes one PNG. **Screenshot all cameras**
   writes every camera at the current time.
6. PNGs land in `output_dir/<event-start>/`. Names include the frame time
   and camera.

Keyboard in the viewer:

- Space: play or pause
- Left / Right: skip 10 seconds (Ctrl: 1 minute)
- s: screenshot the focused camera
- Shift+S: screenshot every camera
- Esc: leave focus, then return to the day

## Tests

```powershell
python -m pytest
```
