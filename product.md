# Tesla video viewer

The current app is a local calendar and multi-camera player for TeslaCam
footage already on this machine. The target product is broader: ingest Tesla
and other video, turn it into durable linked evidence, and make it easy to
review footage, follow a plate or vehicle through its complete known history,
find correlations, and analyze temporal, geographic, plate, vehicle, route,
and FSD patterns. Current folder input reads videos in place; optional managed
copies and user-authorized Tesla/cloud retrieval are planned input modes, not
current behavior. Screenshots and analysis crops are new local files.

Repo: https://github.com/ernop/tesla-video-viewer

This file is the design record. Goals, intentions, product surface, hardware
limits, and decisions (including rejected approaches) live here so later work
can check them. A change is not finished until this file matches it: when a
feature is added, changed, or dropped, or something is learned that would
change a future design choice, write it here in the same turn, including
why. If a path was tested and rejected, record the result so it is not
proposed again as if it were unknown. How to run the app lives in
`README.md`. Do not put local paths, secrets, or clip contents here.

## Product goal

Turn Tesla and other vehicle-related video into a systematic, persistent body
of evidence for viewing and understanding the data:

- find footage by day, time, location, route, plate, vehicle, or interval
- treat a synchronized series as one **video set**, hiding normal one-minute
  file boundaries from the user
- watch every available camera on one clock and capture full-resolution stills
- detect and read plates automatically, keep the evidence across sessions,
  and retry or review weak results
- give each plate a focused page containing its complete known history,
  sightings, links to video, car images and attributes, time-of-day profile,
  location profile, counts, and history distributions
- find correlations between cars through repeated place, time, route, and
  co-occurrence patterns, always linked back to supporting footage
- chart plate jurisdictions, types, serial ranges, and likely issuance periods
  over selected time intervals; California sequence position is a specific
  useful issuance-year signal
- identify vehicle type, color, make, model, and year when evidence supports
  the claim and preserve uncertainty when it does not
- persist route and reliable FSD/driver-assistance state so maps can show where
  FSD was active, inactive, or unknown
- run meaningful or slow work in the background and store its results durably
  so pages load quickly instead of recomputing after every restart

Every main page has one focus: library, interval, video set, plate/vehicle,
aggregate vehicle and plate analysis, route/FSD map, or processing quality.
Navigation between an aggregate, identity, sighting, and exact video moment
must preserve context.

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
  The product intends to skip those files. The current filename-based scanner
  has no explicit `EncryptedClips` exclusion, so valid-looking encrypted names
  can still be indexed and then fail during playback or extraction; add the
  exclusion rather than treating that failure as supported decryption.

MP4s are H.264 High, `mp42`, with the `moov` atom at the end. Front is often
2896×1876; other cameras 1448-wide. About one minute per file, ~36 fps.
There is no standard EXIF/GPS atom and no GPX sidecar.

Filenames are stamped about a minute apart, but **the files are not a clean
60 seconds**. On this car, Recent clips are often ~61–63s long and the next
stamp is ~65–66s later, leaving a hole of a few seconds with no footage.
Probed duration of one file can overlap the next file’s start. Design the
player around that, not around “Tesla writes exact 60s minutes.”

## Playback (one clock)

The viewer plays every camera on one event clock. Clock logic lives in
`web/playback.js` so the browser and the stitch tests share it. `web/app.js`
is the DOM host (double-buffer, prefetch, screenshots).

Rules that were learned the hard way:

- A clip owns the timeline **until the next file’s stamp**, not until its
  probed duration runs out. Extra tail frames that overlap the next stamp
  are skipped.
- When a file ends and a later file exists, jump to that file’s offset even
  if there is a gap (no footage in the hole). Do not pause at 1:01 and leave
  a 7-minute event unfinished.
- Only the **master** camera (prefer front) advances the clock. A shorter
  repeater ending first must not steal a global “seeking” lock, or the
  master never loads minute two.
- Seeking is **per camera**. Loading the next MP4 blanks that element;
  keep the last frame visible on a second video under the tile, swap when
  the new file has a picture, and start prefetching the next minute a few
  seconds before the current one ends. Grid tracks use `minmax(0, fr)` so
  empty `<video>` tags cannot collapse the layout (that looked like a page
  refresh).

Validation: do not reason from invented 60s segments. The fixture
`tests/fixtures/event_2026-08-21_17-26-55.json` is probed offsets and
durations from a real Recent event (~7m 38s, seven files, first front file
~61.5s, next stamp at 66s). `tests/test_playback.js` ticks all six cameras
and must fail if playback freezes before 66s. CI installs Node for that
test. Disabling the ended-handoff in the sim is the detector for the 1:01
bug.

Rejected: treating probed duration as the occupancy window (first file
still “contains” 1:01); one boolean `seeking` for the whole grid; replacing
`src` on the visible video (black flash and layout collapse).

## Public docs

`README.md` is how to run the app and what the UI looks like. `product.md`
is goals, intent, and decisions. `PRODUCT_ONLY.md` is the standalone,
implementation-free description of the complete user-facing product: its
inputs, current capabilities, planned capabilities, privacy boundary, and
explicit exclusions. Keep it synchronized with this design record whenever
the product surface changes. Screenshots in `docs/` may show the real calendar
and day list. **Do not publish identifiable real plates** (OCR text or crop
photos of other people’s cars). Plate UI in the README uses obvious dummy
labels only (`SAMPLE`, `DEMO 42`, `EXAMPLE`). Real scans stay in local SQLite
and `plate-crops/`.

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

The full SEI route is now an explicit planned product surface. Persist
high-frequency GPS and reliable Autopilot/FSD state, then synchronize it with
playback and map route segments as FSD active, available but inactive, manual,
or unknown. Show distance, duration, transitions, and sightings by state. Do
not infer FSD from driving behavior when telemetry does not identify it.

## Product surface

1. **Inputs** — currently one or more TeslaCam roots. Missing disks stay
   listed and drop out of the scan until attached again. Planned adapters
   accept ordinary single- or multi-camera video, optional application-managed
   media copies, and user-authorized Tesla/account/cloud retrieval.
2. **Calendar** — days with clips are amber. Months with clips are listed.
3. **Day / interval** — the current day page is a 24-hour rail plus a list:
   time, Saved/Sentry/Recent, source, place, cameras, duration. The planned
   interval page also accepts custom ranges, trips, N video sets, or an
   approximate footage duration and summarizes plates, vehicles, states,
   issuance periods, places, time profiles, and correlations.
4. **Video set** — all cameras on one scrubber. Click a camera to enlarge it.
   Stitch and last-frame swap: see **Playback**. A video set is one conceptual
   event even when backed by many per-camera minute files; ordinary file
   boundaries are not user-facing.
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
   Filters: All / Classified / Unclassified. **Raw pixels** removes smoothing
   from catalog crop thumbnails. Unclassified plates stay in the list; they
   are not dropped. Click a row to open that plate’s car page. The catalog is
   the index; the car page is the dossier.
9. **Car page** — `#/p/{PLATE}` is the dossier for one OCR string: every
   stored clip it appeared in, inlined where/when, and a map of those
   pins. See **Car page** below.
10. **Plate / vehicle profile** — expand the current car page with a complete
    time-of-day profile, location profile, seen counts, first/last seen,
    history distributions, representative car images, likely vehicle
    attributes, issuance period, co-occurrences, and direct links to every
    supporting sighting and video set.
11. **Vehicle and plate analysis** — not built yet. For the full library or a
    selected interval, chart jurisdiction, plate type/series/range, estimated
    issuance period, vehicle type and attributes, classified/unclassified/
    rejected quality, and changes over time. Aggregate bins always drill down
    to their evidence.
12. **Quality and retry queue** — not built yet. Low-quality or pattern-invalid
    alleged plates are rejected with reason, retained as candidates, sent to
    review, or retried using better frames/crops/cameras/analysis. Do not
    silently promote them to trusted identities or silently discard plausible
    vanity, temporary, specialty, or unsupported-jurisdiction plates.
13. **Route / FSD map** — not built yet. Persist per-frame route and verified
    assistance state; map where FSD was active, inactive, or unknown and link
    every segment and transition to synchronized video.
14. **Background jobs** — discovery, synchronization, OCR, classification,
    vehicle analysis, telemetry decoding, quality review, and aggregates run
    without blocking the existing library. Durable results and job state are
    the source for quick page loads; meaningful results must not live only in
    process memory.

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

The product rule for all non-instant work is **background + durable**. A job
has queued/running/complete/failed/cancelled/needs-review state, progress, and
an analysis version. Store useful partial or completed results in the database
and load those first on every page. A restart resumes safe work or explicitly
re-queues it. New analysis must not destroy the prior usable result until its
replacement succeeds. Opening a page may prioritize its pending jobs, but
must not hold the page blank while recomputing data already derived before.

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

### Plate quality, retry, and issuance estimates — planned

A detector box plus OCR text is only a candidate. Trusted sightings should
consider detector/OCR confidence, crop size and sharpness, agreement across
nearby frames, stable character alternatives, legitimate serial patterns,
location consistency, and repeated evidence. If a reading matches no known
valid pattern, reject it with a reason, keep it as low confidence, send it to
**Needs review**, or schedule another pass over a better frame/crop/camera or
new analysis version. Pattern mismatch is strong quality evidence but is not
alone sufficient to permanently discard vanity, temporary, specialty, or
unsupported-jurisdiction plates.

User corrections, merge/split decisions, and false-positive rejections should
retain the original machine result and persist. The plate catalog and charts
must distinguish trusted, unclassified, rejected, and needs-review candidates.

California sequence position can estimate when many normal plate series were
issued. Add maintained serial ranges and produce an issuance year or range,
matched series, confidence, and exceptions. This is plate issuance, not
vehicle model year, registration ownership, or manufacturing date. Add the
same analysis for other jurisdictions only when reliable sequence data exists.

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

The planned plate page turns this dossier into the complete focused profile
for the OCR identity and associated vehicle evidence: representative car
images across dates/angles, likely type/color/make/model/year, issuance
period, first/last seen, distinct days, sampled time in view, time-of-day and
long-term distributions, location recurrence, co-occurring cars, and possible
OCR collisions or plate transfers. Every statistic and chart point links to
the underlying sightings and video sets.

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

### Make / model / year — planned, not implemented

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
Vehicle type/color/make/model/year is now an explicit planned product
capability, not an excluded one. Implement it with current-enough evidence,
confidence and alternatives, durable source images, and a review path. Viable
paths remain Car-1000 weights if published, training our own, accepting a
CLIP/SigLIP approach with clear uncertainty, or paying for a maintained
recognizer. Unsupported attributes remain unknown.

## Out of scope

- Circumventing or performing unauthorized decryption of protected clips
- Editing or deleting footage on the USB drive
- Binding the server on a public interface
- A vehicle-detector gate in front of plate OCR (tested; slower on this CPU)
- Authoritative identification of a vehicle owner
- Treating overlapping serial formats (e.g. `ABC1234`) as a single certain
  state; those stay multi-candidate or unclassified-looking (low confidence)
- Dropping unclassified plates from the catalog
- Silently promoting low-quality or pattern-invalid OCR to a trusted plate
- Silently discarding plausible unsupported, vanity, temporary, or specialty
  plates merely to make analytics look cleaner
- Claiming plate, vehicle, location, issuance year, or FSD state with certainty
  when the evidence does not support it
- Classifying jurisdiction from plate artwork without a validated method and
  explicit uncertainty
