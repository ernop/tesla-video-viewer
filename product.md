# Tesla video viewer

Local web app for browsing TeslaCam footage on this machine. It is a calendar
and multi-camera player for clips the car already wrote to USB or a copy of
that disk. It does not talk to Tesla servers and does not copy or move the
video files. Screenshots and plate crops are new files next to the app.

Repo: https://github.com/ernop/tesla-video-viewer

This file is the design record. Goals, intentions, product surface, hardware
limits, and decisions (including rejected approaches) live here so later work
can check them. A change is not finished until this file matches it: when a
feature is added, changed, or dropped, or something is learned that would
change a future design choice, write it here in the same turn, including
why. If a path was tested and rejected, record the result so it is not
proposed again as if it were unknown. How to run the app lives in
`README.md`. Do not put local paths, secrets, or clip contents here.

## Who it is for

Someone with a Tesla (this install was built around a 2023 Model Y with six
cameras) who keeps SavedClips, SentryClips, and RecentClips on a USB drive
or a folder dump, and wants to:

- find a save by day and time
- watch every camera on one clock
- grab full-resolution stills
- read license plates from a clip and keep them across sessions
- guess which US state (or territory) issued a plate from its serial format
- browse every stored plate, including ones that could not be classified
- open one plate and see every clip it appeared in, with when/where and a
  map of those pins
- see where a save happened
- later: summarize a span of clips (a day, N videos, ~30 minutes of footage)
  as the set of plates seen, how long each was in view, and which state
  each is from
- later: identify the car around a plate (make / model / year) if a library
  exists that covers current US cars, not a 2013–2016 frozen set

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
**clip GPS**. This is how RecentClips get coordinates.

Stored plate hits copy that **event-level** pin (`event.json` or first SEI
sample), not a per-frame GPS track. Hits in the same clip therefore share
one coordinate. A full moving map from the SEI track is not in the UI yet.
The car page map is those discrete stored pins with times of day, not a
live trail during playback.

## Product surface

1. **Folders** — one or more TeslaCam roots. Missing disks stay listed and
   drop out of the scan until they are attached again.
2. **Calendar** — days with clips are amber. Months with clips are listed.
3. **Day** — 24-hour rail plus a list: time, Saved/Sentry/Recent, source,
   place, cameras, duration.
4. **Viewer** — all cameras on one scrubber. Click a camera to enlarge it.
5. **Screenshots** — current camera or all cameras as full-resolution PNGs
   under `output_dir/<event-start>/`.
6. **Plates (per clip)** — FastALPR on the **front camera only**, sampled at
   **1 fps**. Opening a clip queues a scan if that event is not already stored.
   **Scan plates again** forces a new pass. Hits persist in SQLite.
   Iridescent boxes mark plates on the video (lerp between consecutive hits
   ≤1.5s apart). Scrubber marks and Prev/Next step through hits.    Open a hit
   for **Plate** (tight still), **Car** (heuristic square crop), or **Full
   frame**. The OCR text is classified to a US jurisdiction at write time
   (see below) and shown on the card and overlay. The plate number and
   **This car** open that plate’s car page. Prev/Next still seek inside
   the open clip; they do not navigate away.
7. **Location** — city, street, coordinates, and a map link as above.
8. **Plate catalog** — header **Plates** (`#/plates`) lists every unique
   plate in the database, not just the open clip. Columns: crop, text,
   state (or **Unclassified**), series, hit count, time in view, place.
   Filters: All / Classified / Unclassified. Unclassified plates stay in
   the list; they are not dropped. Click a row to open that plate’s car
   page. The catalog is the index; the car page is the dossier.
9. **Car page** — `#/p/{PLATE}` is the dossier for one OCR string: every
   stored clip it appeared in, inlined where/when, and a map of those
   pins. See **Car page** below.
10. **Day / span summary** — not built yet. The catalog and car page
    both read the same store: for a day with N videos totaling ~30
    minutes, the set of plates seen, how long each appeared, and which
    state each is from.

Keyboard in the viewer: Space play/pause, arrows skip 10s (Ctrl: 1 min),
`s` screenshot focused camera, Shift+S all cameras, Esc leave focus then
back to the day (or back to the car page if the clip was opened from
one). Esc on the car page and catalog returns to the previous list.

## Hardware this install runs on

12th-gen Intel i7-1255U, 32 GB RAM, Intel Iris Xe, **no NVIDIA GPU**. Inference
is **CPU**. `onnxruntime-directml` is installed on Windows but DirectML crashes
(`0xC0000005`) on the FastALPR models, so the app forces
`CPUExecutionProvider`. Do not assume a discrete GPU when choosing models.
Do not recommend a hardware upgrade; pick the largest model that fits this
machine, with offloading/streaming if needed.

## Runtime

- Python 3.13+, ffmpeg, ffprobe
- FastAPI + uvicorn bound to `127.0.0.1:8765`
- SQLite index `clip-index.sqlite3` next to `config.json`
- FastALPR detector `yolo-v9-s-608-license-plate-end2end`, OCR
  `cct-s-v2-global-model`, CPU ONNX Runtime
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

Plate tables in the same SQLite file (schema version still `"1"`, additive
columns on `plates`): `plates` (unique text, best crop, stored jurisdiction),
`plate_appearances` (bbox, camera, time, GPS if known), `plate_scans`.
Incomplete scans reset on startup. On startup, rows with a null jurisdiction
are classified. Crops live in `plate-crops/` next to the index
(`<crop_id>.jpg`, `-still.png`, `-vehicle.png`, `-frame.png`).

Event IDs are the first 24 hex chars of sha256(`source_key|kind|key|start`).

Isolated FastALPR on a 2896×1876 front PNG is about **0.8–1.0s per frame**
after models are loaded. ffmpeg JPEG extract for a ~60s clip at 1 fps is a
few seconds and is separate from recognition.

## Plates: US jurisdiction from serial format

The goal is to label OCR text with a likely issuing **state or territory**,
not to read the plate graphic. FastALPR's `region` field is too coarse
(often just `US`). Classification is **serial-pattern matching**: after
stripping spaces and dashes, the text is scored against packed formats for
all 50 states, DC, and five territories (~172 series as of 2026-08-21).

Sources compiled into `app/us_plate_data.py` (JSON dump at
`app/data/us_plate_series.json`):

- https://en.wikipedia.org/wiki/United_States_license_plate_designs_and_serial_formats
- https://en.wikipedia.org/wiki/Vehicle_registration_plates_of_California
- OpenALPR `runtime_data/postprocess/us.patterns` (copy at `app/data/us.patterns`)

California is modeled as the everyday series (~15), not only the current
passenger plate: passenger `1ABC123` (1980–2026) and `123ABC1` (2026–),
still-valid 1963/1969 six-character passenger, commercial `1A12345` /
`12345A1`, motorcycle, trailer / permanent trailer, apportioned, temporary
paper. Letter-skip rules are applied (California I/O/Q only as the middle
letter of the three-letter block; Texas/Tennessee drop vowels; and so on).

Scoring prefers distinctive masks (`7ABC123` → California, `1234ABC` →
Kansas, `AB1C2D` → Missouri). Formats shared by many states (`ABC1234`)
keep alternatives and a low confidence. Clip GPS, when present, boosts the
state the car is in, then neighbors; it does not force a single answer.
Vanity plates and unmatched strings stay **unclassified** and remain
visible in the catalog.

Classification runs when a plate row is written or refreshed
(`plates.jurisdiction_*`, `best_event_id`), not only when the clip viewer
renders. The catalog API is `GET /api/plates`. One plate’s sightings are
`GET /api/plates/{text}`. Crops without an event in the URL are
`GET /api/plates/crops/{crop_id}`.

## Car page

The identity of a car, for now, is the normalized OCR plate string. The
page exists so a hit in one clip is not a dead end: from that plate you
can see every other segment it was stored in, with enough where/when to
tell the story, and a map of those times and places.

Hash: `#/p/{PLATE}` (alphanumeric, uppercased). Entry points: plate
number or **This car** on a clip card; a row on the catalog. Back goes to
the clip, the catalog, the day, or the calendar depending on how the page
was opened. Opening a clip from the car page seeks to the first hit in
that event; viewer Back then returns to the car page.

Each sighting group is one `event_id`: date, clock time, Saved/Sentry/
Recent, city/street/coords, cameras and elapsed times of hits, best crop,
and **Open clip**. If that event is still in the library, one inlined
`<video>` uses the existing camera-segment URL and seeks to the local
offset of the first hit (`preload="none"` so a long history does not
download every file). Missing clips stay listed as metadata.

The map (Leaflet + OpenStreetMap tiles, loaded from a CDN) plots stored
GPS pins. Hits that share a coordinate to four decimal places collapse
to one marker whose tooltip/popup lists each **time of day** (and date
when the same pin was seen on more than one day). A polyline connects
distinct event pins in chronological order. If Leaflet is missing
(offline, blocked CDN), the same points fall back to OpenStreetMap
links. No pin is invented: events without lat/lon are in the list only.

This is not a per-frame drive path. Appearance rows store the event pin
available at scan time. Parked Sentry often has no SEI GPS; those clips
only appear on the map if `event.json` had `est_lat` / `est_lon`.

Why a dedicated hash page, not an expanding catalog row: the map, inline
clips, and per-event list need a full page, and the clip viewer already
uses Prev/Next for seeking. Identity click (the plate text) must not
steal that seek control.

This is not plate-artwork recognition (colors, slogans, stacked DP). It is
not Canadian or Mexican matching as a first-class path. It is the store
the future day summary will read.

## Plates: car crop and vehicle ID

The **Car** still is not a car detector. `vehicle_crop_box` draws a square
about **10× plate width**, shifted **up 28%**, because a rear plate in a
front-camera shot usually sits near the bottom of the car. Side angles,
trucks, and motorcycles break that. Real size and facing direction need a
vehicle detector box, not this heuristic.

### Vehicle detector as a plate skip — rejected for speed

The idea was: run RF-DETR (COCO car/truck/bus/motorcycle from
`open-image-models`) first, and skip FastALPR when no vehicle is in the
frame. Timed on this PC on a real Tesla front PNG (`2896×1876`, CPU):

| Model | Approx. time / frame |
| --- | --- |
| `rf-detr-nano-384-coco` | 3.8–6.6s (found 5 vehicles on the test frame) |
| `rf-detr-small-512-coco` | ~6.2s |
| FastALPR plate detector `yolo-v9-s-608` (already in the pipeline) | 3.1–3.6s |
| Tiny plate detector `yolo-v9-t-256` | ~0.5s, but dropped a plate the s-608 model kept |

RF-DETR nano is **not cheaper** than the plate detector we already run. On
frames with cars it would be both models. On empty frames it is still slower
than plate detect-then-skip-OCR. **Do not add RF-DETR as a time-saving gate.**
It remains a valid way to get real vehicle boxes for crops or make/model ID,
but that makes scans slower, not faster.

### Make / model / year — not implemented

There is no make/model/year library in this app. FastALPR reads plates only.

A wider search for a **current** free local classifier did not find one.
Downloadable weights are frozen on old datasets:

- VMMRdb (e.g. Hugging Face `Jordo23/vehicle-classifier`): ~8,949
  make+model+year classes, years stop around **2016**. Top-1 ~50%. The listed
  ONNX (~1 MB) is not a plausible EfficientNet-B4; the ~130 MB `.pth` is the
  real weights.
- Stanford Cars classifiers: ~196 classes, years stop around **2013**.
- VehicleDINO: detect + type + 42 makes + 323 CompCars models, **no year**.
  OCR is Chinese plates; do not replace FastALPR with it.

**Car-1000** (2025, 1,000 models, 166 brands, many post-2020) is the dataset
that actually covers recent cars. Authors published images, not a ready ONNX.

The maintained product that claims current coverage is commercial **Plate
Recognizer** make/model/color (9,000+ models, extra SDK fee). The free way
to avoid a 2016 freeze is CLIP/SigLIP against a make+model list we keep,
with weak year accuracy and extra CPU cost on a vehicle crop.

Do not wire Jordo23/Stanford Cars as if they ID current street traffic.
Revisit only if Car-1000 weights appear, we train our own, we accept CLIP, or
we pay for Plate Recognizer MMC.

## Out of scope

- Decrypting `EncryptedClips`
- Uploading clips or talking to Tesla's fleet APIs
- Editing or deleting footage on the USB drive
- A live GPS trail during playback (SEI is only used for a single event
  pin today; the car page maps those stored pins, not the 36 Hz track)
- Copying Tesla MP4s into the app tree
- Binding the server on a public interface
- A vehicle-detector gate in front of plate OCR (tested; slower on this CPU)
- Make/model/year ID until a library covers current US cars
- Treating overlapping serial formats (e.g. `ABC1234`) as a single certain
  state; those stay multi-candidate or unclassified-looking (low confidence)
- Dropping unclassified plates from the catalog
- Classifying from plate artwork instead of serial format
