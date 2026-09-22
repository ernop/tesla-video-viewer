# Tesla Video Viewer — product-only system description

This document defines the intended product: what information it accepts, what
the user can learn from it, how its pages are organized, and how the product
should behave. It deliberately excludes software architecture, APIs,
dependencies, schemas, model names, and development history.

Status terms:

- **Available** — part of the working product today.
- **Planned** — part of the intended product, but not complete today.
- **Product rule** — behavior every implementation should preserve.

## Product goal

The product turns Tesla and other vehicle-related video into a systematic,
persistent body of evidence that is easy to review and understand.

It should let the user:

- find the relevant footage without manually opening individual files;
- treat synchronized multi-camera footage as one coherent video set;
- move smoothly between video sets, plate sightings, vehicle histories,
  places, times, and aggregate analyses;
- detect and read license plates automatically;
- track the complete known history of a plate and its associated vehicle;
- inspect images and likely attributes of the vehicle around each sighting;
- find temporal, geographic, and co-occurrence patterns between vehicles;
- analyze plate jurisdictions, series, likely issuance periods, and other
  useful ranges over selected time intervals;
- understand driving routes and where driver-assistance states, including
  FSD, were or were not active; and
- return to previously derived information immediately instead of repeatedly
  waiting for the same video analysis.

The product is primarily about viewing and understanding the data. Playback,
search, plate recognition, maps, profiles, and charts are different ways of
navigating the same connected history.

## Product principles

### Work at the level the user understands

**Product rule.** The interface should present meaningful concepts, not storage
implementation details.

A seven-minute multi-camera recording is one **video set** even when each
camera was stored as many short files. The user should normally see one title,
one duration, one clock, one scrubber, and one set of synchronized camera
views. File boundaries should appear only when diagnosing missing or damaged
media.

The same principle applies elsewhere:

- a plate is one identity with a history, not a list of recognition rows;
- a vehicle sighting is a moment linked to video, place, and time;
- a route is a continuous trip or interval, not a list of telemetry samples;
- an analysis interval is a user-selected span, not a batch of database
  records; and
- background processing is a durable job with progress, not a frozen page.

### Every page has one clear focus

**Product rule.** Each primary page should answer one main question and link
directly to the related evidence.

- **Library:** What footage and data exist?
- **Day or interval:** What happened during this span?
- **Video set:** What do all cameras show during this event?
- **Plate:** What is the complete known history of this plate and vehicle?
- **Vehicles:** What vehicles, plate types, and patterns exist across the
  library?
- **Map and driving state:** Where did recording, sightings, and FSD states
  occur?
- **Jobs and quality:** What is being processed, what needs review, and what
  should be retried?

### Derived data is persistent

**Product rule.** Meaningful information that is not instantly available must
be produced in the background and saved in the persistent database. Important
job state and results must not exist only in process memory.

This includes, when applicable:

- discovered and grouped media;
- durations and camera alignment;
- location and route information;
- driving and FSD state;
- detected plates and recognition attempts;
- plate crops, vehicle crops, and representative frames;
- jurisdiction and plate-series classification;
- likely issuance-year estimates;
- vehicle type, make, model, year, and color assessments;
- sighting links and co-occurrence relationships;
- quality decisions, rejection reasons, and retry state; and
- summaries and chart-ready aggregates.

The product must not keep important results only in memory and make the user
wait for the same work after a restart. Pages should load saved information
quickly, show partial results when useful, and update as background jobs
finish.

### Uncertainty stays visible

**Product rule.** Recognition and classification are evidence, not guaranteed
identity.

The product should preserve confidence, alternatives, provenance, and review
status. It should prefer **Unknown**, **Unclassified**, or **Needs review**
over a confident but unsupported claim.

## Inputs and media ownership

### Local video folders

**Available.** The user can add one or more local folders from attached drives
or copied archives. Multiple sources merge into one searchable library while
each video set retains its source identity.

Tesla-style timestamped, per-camera recordings are recognized and grouped as
Saved, Sentry, Recent, or other video sets. Common front, rear, repeater, and
pillar cameras are aligned on one event clock.

Missing drives remain configured and are clearly marked unavailable. Attached
sources remain usable while another source is missing.

### Other video input

**Planned.** The product should accept video that does not use Tesla's folder
or filename conventions. An import flow should let the user describe or
confirm:

- capture time and time zone;
- camera or viewpoint;
- whether files belong to the same video set;
- known location or route;
- source device; and
- any available metadata sidecars.

Single-camera video remains valid. Multi-camera input should be grouped and
synchronized when timestamps or user-provided alignment make that possible.

### Tesla-authorized and cloud input

**Planned.** Tesla account access, fleet interfaces, and cloud-video retrieval
may become additional user-authorized input sources when they provide useful,
lawful access to the user's own data.

These integrations must be optional, identify what will be retrieved, and
preserve the same local review and provenance rules as folder-based input.

### Referenced or managed media

**Available.** Existing local videos can be read in place without being moved
or changed.

**Planned.** The user may optionally copy selected source media into an
application-managed library for retention, portability, or protection from a
temporary drive being disconnected. The product must make the choice explicit,
show whether media is referenced or managed, and never silently delete the
original.

## Ingestion and background processing

### Source scanning

**Available.**

- Adding or changing folders starts a background scan.
- Rescan discovers new or changed media without repeating unchanged work.
- The current library remains usable while scanning.
- Progress reports elapsed time, files seen, processing rate, recent activity,
  completion, and failures.
- Completed work remains available if a later part of a scan fails.

### Durable job behavior

**Product rule.**

- Every non-trivial job has a durable state: queued, running, complete,
  failed, cancelled, or needs review.
- A restart resumes safe work or clearly re-queues it; it must not silently
  lose the job.
- Jobs expose progress and, when practical, estimated completion time.
- Expensive work is deduplicated by its inputs and analysis version.
- Updated analysis can be requested without destroying the prior usable result
  until the replacement succeeds.
- Pages load saved results first and then subscribe to updates.
- Partial results may appear when they are internally consistent and clearly
  labeled.

### Processing priorities

**Planned.** The user should be able to prioritize:

- the open video set;
- a selected day or interval;
- unprocessed footage;
- low-quality plate results needing another attempt; or
- a complete-library analysis.

Interactive review work should take priority over bulk enrichment.

## Core data concepts

### Video set

A **video set** is one coherent recording event or continuous interval. It may
contain one camera or several synchronized cameras and may be backed by many
physical files.

### Sighting

A **sighting** links a detected plate or vehicle to:

- a video set;
- event-relative and wall-clock time;
- camera and image region;
- location when known;
- representative plate, vehicle, and full-frame images;
- recognition quality; and
- driving or FSD state when known.

### Plate identity

A **plate identity** is normalized recognized text plus its classification and
review history. Similar but uncertain readings must not be merged without
retaining the original alternatives and evidence.

### Vehicle profile

A **vehicle profile** is the accumulated evidence associated with a plate:
images, likely type, color, make, model, year, locations, times, video sets,
and relationships to other sightings.

A plate is a practical index for a vehicle, not proof of permanent physical
identity. Plate transfers, OCR collisions, unreadable characters, and
temporary plates must remain possible.

### Analysis interval

An **analysis interval** is a selected day, custom time range, collection of
video sets, trip, or approximate footage duration. It is the unit used for
summary charts and comparisons.

## Library page

**Available.** The library is the entry point for discovering footage.

It provides:

- all configured sources and their attachment state;
- total files, video sets, and date range;
- month navigation;
- a calendar highlighting days with footage;
- event counts and first event times; and
- clear empty, missing-source, and scan-failure states.

**Planned.** The library should also expose processing completeness, data
quality, recent imports, saved intervals, and shortcuts into vehicle and route
analysis.

## Day and interval page

### Day review

**Available.** A day has a 24-hour rail and chronological video-set list. Each
video set can show time, recording type, source, place, cameras, and duration.

### Interval analysis

**Planned.** The user can choose a day, custom time span, trip, number of video
sets, or approximate footage duration and see:

- all video sets in the interval;
- distinct plates and vehicles;
- first, last, and repeated sightings;
- sampled time in view;
- jurisdictions and likely issuance periods;
- vehicle-type and make/model distributions;
- time-of-day and location distributions;
- plate-jurisdiction distribution charts;
- unknown, rejected, and needs-review counts;
- co-occurring vehicles and repeated sequences; and
- links from every aggregate back to the supporting plates and video sets.

Filters should include source, recording type, camera, location, jurisdiction,
plate series, confidence, review status, vehicle type, and driving/FSD state.

## Video-set page

The video-set page is focused on reviewing one coherent recording.

### Synchronized viewing

**Available.**

- All cameras share one event clock, scrubber, and play/pause state.
- The user can seek, skip, focus one camera, or restore the complete grid.
- Camera files hand off automatically despite overlaps, early endings, or
  short gaps.
- Missing footage is shown as a gap without exposing normal file boundaries.
- A loading camera retains the prior visible frame where possible.
- Place and event-level map information appear when known.

### Video-set evidence

**Available.**

- Save a full-resolution still from one camera or all available cameras.
- View automatically detected plate cards and timeline markers.
- Jump to a plate sighting and step through its sampled appearances.
- Inspect plate, vehicle-context, and full-frame images.
- Open the plate page without losing the return path to the video set.

**Planned.**

- Show detected vehicles independently of whether a plate is readable.
- Show likely vehicle type, color, make, model, and year with confidence.
- Show route position and driving/FSD state at the current time.
- Filter or annotate the timeline by plate, vehicle, location, and driving
  state.
- Allow user corrections and quality decisions to improve later processing.

### Controls

**Available.**

- Space: play or pause.
- Left/Right: move ten seconds.
- Ctrl/Command + Left/Right: move one minute.
- `s`: save the focused or primary camera.
- Shift+`S`: save every available camera.
- Escape: leave camera focus, then return to the prior page.

## Automatic plate reading

### Detection

**Available.** Opening an unprocessed video set queues background plate
recognition. Current processing samples the front camera approximately once
per second, stores its results, and can be run again on request.

**Planned.**

- Adapt sampling to motion, plate persistence, scene changes, and prior
  uncertainty instead of relying only on a fixed interval.
- Revisit uncertain frames at higher temporal or image resolution.
- Combine evidence across adjacent frames and useful cameras.
- Detect plate-like regions even when the first OCR attempt fails.

### Quality filters

**Product rule.** A detected rectangle is not automatically a valid plate
sighting.

Quality evaluation should consider:

- detector and OCR confidence;
- minimum useful image size and sharpness;
- agreement across adjacent frames;
- stable character alternatives;
- valid jurisdiction or plate-series patterns;
- consistency with location and neighboring sightings;
- repeated appearance of the same reading; and
- known temporary, specialty, vanity, and non-US formats.

If an alleged plate does not match any legitimate known pattern, the product
should not silently promote it to the trusted plate catalog. Depending on the
evidence, it should be:

- rejected with a recorded reason;
- retained as a low-confidence candidate;
- placed in a **Needs review** queue; or
- queued for a later recognition pass using a different crop, frame, camera,
  or analysis version.

Pattern mismatch alone must not permanently discard plausible vanity,
temporary, specialty, or unsupported-jurisdiction plates. The original crop
and recognition alternatives should remain available for review.

### Corrections and retries

**Planned.** The user can correct text, split incorrectly merged identities,
merge proven duplicates, reject false detections, and request another pass.
Corrections retain the original machine result and become durable evidence for
future processing.

## Plate page

The plate page is the complete known history of one plate identity and its
associated vehicle evidence.

### Summary

**Available in part.** The page currently shows normalized text, jurisdiction
assessment, best crop, total appearances, video-set count, known places, and
first/last seen times.

**Planned complete profile.** The focused summary should include:

- plate text, jurisdiction, series, confidence, and alternatives;
- likely issuance year or year range when inferable;
- first seen, last seen, total sightings, and distinct days;
- total sampled time in view;
- likely vehicle type, color, make, model, and year;
- representative plate and car images from different angles and dates;
- quality and review state; and
- direct actions to correct, reject, merge, split, or retry analysis.

### Full history

**Available.** Every stored video set containing the plate is listed with
date, time, recording type, source, place, hit times, preview, and a link that
opens the synchronized video at the first sighting. Historical metadata stays
visible when the original source is temporarily unavailable.

### Plate-focused profiles and visualizations

**Planned.**

- A time-of-day profile showing when the plate tends to appear.
- Day, week, month, and longer-term sighting distributions.
- A location profile with counts, recurrence, and first/last seen at each
  place.
- A map of all known sightings and chronological movement between distinct
  event pins.
- History-over-time charts with drill-down to each sighting.
- Image history showing changes in vehicle appearance or confidence.
- Co-occurrence links to plates and vehicles seen nearby in time or place.
- Repeated-route and repeated-sequence indicators.
- Comparison of conflicting vehicle attributes that may indicate OCR collision
  or plate transfer.

Every chart point, bin, count, and relationship must link back to its
supporting sightings and video sets.

## Vehicle and plate analysis page

**Planned.** A dedicated analysis section summarizes the full library or a
selected interval.

### Vehicle exploration

It should support:

- all known plate identities and vehicle profiles;
- classified, unclassified, rejected, and needs-review filters;
- search by plate text or partial text;
- vehicle type, color, make, model, and year filters;
- seen count, distinct days, first/last seen, and sampled time in view;
- recurring vehicles and newly observed vehicles;
- vehicles that repeatedly co-occur;
- vehicles sharing locations or time windows; and
- direct navigation to each plate page and supporting video set.

### Plate-series and jurisdiction charts

It should chart:

- plates by state or territory for a selected time interval;
- classified versus unclassified and rejected candidates;
- plate-series and format distributions;
- likely issuance-year or issuance-range distributions;
- jurisdiction by time of day, day, place, source, or route;
- changes in the observed jurisdiction mix over time; and
- data-quality and retry rates by category.

### California sequence analysis

**Planned.** California serial sequencing can provide an estimated issuance
period for many ordinary plate series. The product should use maintained
sequence ranges to estimate a year or year range and expose:

- the matched series;
- the sequence evidence;
- the estimated issuance period;
- confidence and known exceptions; and
- links to the source sightings.

The estimate describes likely plate issuance, not vehicle model year,
registration ownership, or guaranteed manufacturing date.

Other jurisdictions may gain issuance-period estimates when reliable sequence
data exists.

## Location, route, and driving-state page

### Event locations

**Available.** Saved metadata, video tags, or embedded GPS can provide city,
street, and event-level pins. Missing location does not prevent review.

### Routes

**Planned.** The product should decode and persist the available per-frame or
high-frequency route data and present:

- the route for one video set, trip, day, or interval;
- current route position synchronized with playback;
- speed, heading, and other useful driving-state overlays;
- sighting markers linked to plate and video-set pages; and
- clear gaps where telemetry is unavailable.

### FSD and driver-assistance state

**Planned.** When the footage contains reliable vehicle-state telemetry, the
product should detect and persist FSD and related assistance states.

The user should be able to see:

- a map colored or segmented by FSD active, available but inactive, manual
  driving, and unknown;
- when state transitions occurred;
- distance and duration in each state;
- state distribution by trip, day, road, or selected interval;
- the driving state associated with each sighting; and
- a link from every route segment or transition to synchronized video.

Unknown or unsupported telemetry must remain unknown rather than being inferred
from driving behavior alone.

## Navigation

**Product rule.** Navigation should preserve context.

- Opening a video from a plate history returns to that plate page.
- Opening a sighting from a map or chart returns to the originating analysis.
- Opening a plate from a video set returns to the same time in that video.
- Local page addresses should identify months, days, video sets, plate
  profiles, intervals, and saved analyses so they can be bookmarked.
- Back and Escape should move through conceptual pages, not expose media-file
  boundaries.

## Persistence, freshness, and provenance

**Available in part; product rule for all future analysis.**

- Clip indexing, plate results, crops, classifications, and sightings survive
  restarts.
- Missing media does not erase stored history.
- Every derived result should identify its source evidence and analysis
  version.
- Pages should indicate whether results are complete, partial, stale, failed,
  or awaiting review.
- Reprocessing should be possible when recognition improves.
- Aggregates should refresh from durable results without requiring all source
  video to be decoded again.
- User corrections and rejections must persist.

## Privacy and control

- Local folders remain local unless the user explicitly enables another input
  or storage action.
- The product does not silently upload footage, plate images, or vehicle
  profiles.
- Account and cloud integrations require explicit authorization and explain
  what they retrieve or store.
- Managed media copies require explicit user action.
- Maps may contact their named map provider; media is not included in map
  requests.
- The product is not intended to identify or expose a vehicle's owner.
- Original source videos are not edited or deleted by ordinary review and
  analysis actions.

## Remaining out of scope

The product does not intend to provide:

- circumvention or unauthorized decryption of protected video;
- silent modification or deletion of original source media;
- authoritative identification of a vehicle owner;
- certainty when plate text, jurisdiction, vehicle attributes, FSD state, or
  location are not supported by the evidence;
- hiding unclassified or low-quality results merely to make analytics appear
  cleaner; or
- public internet exposure of a private library by default.

## Product success

Starting from video and its available metadata, the user should be able to move
from a broad question—what happened, which vehicles appeared, where was FSD
used, or what plate populations were seen—to the exact supporting frame in a
few interactions.

The reverse path should be equally smooth: from one frame to a plate, from the
plate to its full history, from that history to places and time patterns, and
from those patterns to correlated vehicles and aggregate distributions.

Once the product has derived meaningful information, it should be durable,
quick to revisit, transparent about uncertainty, and always linked back to the
video evidence.
