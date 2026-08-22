# Tesla video viewer

Local web app for browsing TeslaCam footage on this machine. It is a calendar
and multi-camera player for clips the car already wrote to USB or a copy of
that disk. It does not talk to Tesla servers and does not move the video
files.

Repo: https://github.com/ernop/tesla-video-viewer

## Who it is for

Someone with a Tesla (this install was built around a 2023 Model Y with six
cameras) who keeps SavedClips, SentryClips, and RecentClips on a USB drive
or a folder dump, and wants to:

- find a save by day and time
- watch every camera on one clock
- grab full-resolution stills
- read license plates from a clip
- see where a save happened

## What Tesla writes

Tesla stores one MP4 per camera per minute. A 2023 Model Y typically has:

- `front`
- `back` (sometimes named `rear`)
- `left_repeater`
- `right_repeater`
- `left_pillar`
- `right_pillar`

Names look like `2023-08-21_15-30-45-front.mp4`. Layout on the USB drive:

- `TeslaCam/RecentClips/` — rolling buffer of recent driving. No `event.json`.
- `TeslaCam/SavedClips/<stamp>/` — honk / dashcam button saves. Has `event.json`
  and usually `thumb.png`.
- `TeslaCam/SentryClips/<stamp>/` — Sentry triggers. Same sidecar as Saved.
- `TeslaCam/EncryptedClips/` — same folders, but the MP4s and often
  `event.json` are encrypted. Only the recording car or
  https://dashcam.tesla.com (local decrypt after fetching keys) can open them.
  This app skips those files.

MP4s are H.264 High, `mp42`, with the `moov` atom at the end. Front is often
2896×1876; other cameras 1448-wide. About one minute per file, ~36 fps.
There is no standard EXIF/GPS atom and no GPX sidecar.

## Location

Tesla records place in three independent ways. The viewer shows the best
place name and pin it can read without decrypting files.

### 1. `event.json` (Saved and Sentry)

Every plaintext SavedClips / SentryClips folder has a small JSON file:

```json
{
  "timestamp": "2026-03-17T17:52:09",
  "city": "Cupertino",
  "street": "N De Anza Blvd",
  "est_lat": "37.3359",
  "est_lon": "-122.033",
  "reason": "user_interaction_dashcam_launcher_action_tapped",
  "camera": "0"
}
```

This is the event pin Tesla wrote at save/trigger time. City and street are
human labels. `est_lat` / `est_lon` are coarse (about 4 / 3 decimal places).
The viewer shows them on the day list and in the player, with a link to
OpenStreetMap. Source label: **Tesla event pin**.

RecentClips have no sidecar. Encrypted `event.json` is a binary blob and is
ignored.

### 2. MP4 stream tags (newer driving clips)

On later firmware, the H.264 stream tags include:

- `title` — city (`San Carlos`, `Mountain View`)
- `comment` — street (`US-101 S`, `Grant Rd`)

No coordinates live in those tags. The player fills city/street from tags
when `event.json` did not supply them. Source label: **clip tags**.

December 2025 clips on this library did not have the tags. June 2026 and
later driving clips did.

### 3. Per-frame GPS in the video (SEI)

From Tesla firmware **2025.44.25** (2025 Holiday Update) on HW3+, driving
clips embed a protobuf in H.264 SEI NAL units. Official spec and tools:

- https://github.com/teslamotors/dashcam
- https://teslamotors.github.io/dashcam/sei_explorer.html

Fields include `latitude_deg`, `longitude_deg`, `heading_deg`, speed,
steering, gear, blinkers, brake, and Autopilot state. About 36 samples per
second. Parked Sentry clips usually have none. Encrypted clips have none
until decrypted.

When an event has no `est_lat` / `est_lon`, the player reads the first SEI
GPS sample from one camera file and uses that as the pin. Source label:
**clip GPS**. This is how RecentClips get coordinates. A full moving map
from the SEI track is not in the UI yet.

## Product surface

1. **Folders** — one or more TeslaCam roots. Missing disks stay listed and
   drop out of the scan until they are attached again.
2. **Calendar** — days with clips are amber. Months with clips are listed.
3. **Day** — 24-hour rail plus a list: time, Saved/Sentry/Recent, source,
   place, cameras, duration.
4. **Viewer** — all cameras on one scrubber. Click a camera to enlarge it.
5. **Screenshots** — current camera or all cameras as full-resolution PNGs
   under `output_dir/<event-start>/`.
6. **Plates** — FastALPR on front, rear, and repeater cameras. Click a plate
   to jump to that time.
7. **Location** — city, street, coordinates, and a map link as above.

Keyboard in the viewer: Space play/pause, arrows skip 10s (Ctrl: 1 min),
`s` screenshot focused camera, Shift+S all cameras, Esc leave focus then
back to the day.

## Runtime

- Python 3.13+, ffmpeg, ffprobe
- FastAPI + uvicorn on `127.0.0.1:8765`
- SQLite index `clip-index.sqlite3` next to `config.json`
- FastALPR + ONNX Runtime (DirectML on Windows)
- GitHub Actions runs pytest on Python 3.13

Config (`config.json`, not committed):

- `sources` — clip folders
- `output_dir` — PNG dump folder
- `host` / `port`

`config.example.json` is the committed template. Local paths, the SQLite
index, virtualenv, and MP4s are gitignored.

Scan is incremental: a later walk only re-reads files whose size or mtime
changed. Save-and-scan returns immediately; a status line shows files while
the walk runs in the background.

## Out of scope

- Decrypting `EncryptedClips`
- Uploading clips or talking to Tesla's fleet APIs
- Editing or deleting footage on the USB drive
- A live GPS trail during playback (SEI is only used for a single pin today)
