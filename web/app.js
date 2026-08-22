const AREA_FOR_CAMERA = {
  left_repeater: "lrep",
  front: "front",
  right_repeater: "rrep",
  left_pillar: "lp",
  back: "back",
  right_pillar: "rp",
};

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const state = {
  config: null,
  library: null,
  month: null,
  day: null,
  dayDetail: null,
  event: null,
  elapsed: 0,
  playing: false,
  focused: null,
  lastDumpFolder: null,
  videos: new Map(),
  loadedSegment: new Map(),
  buffers: new Map(),
  loadToken: new Map(),
  plateStatus: null,
  selectedPlate: null,
  plateHitIndex: 0,
  plateZoomScale: 1,
  carPlate: null,
  carReturnEventId: null,
  carReturnDay: null,
  carReturnPlates: false,
  viewerReturnPlate: null,
  pendingSeek: null,
  platesCatalog: null,
  platesFilter: "all",
  platesRaw: false,
  selectedCatalogText: null,
  catalogZoom: 1,
};

let player = null;
let plateOverlayObserver = null;
let carMap = null;

let draftSources = [];

function sourceListFromConfig() {
  if (state.config && Array.isArray(state.config.sources)) {
    return state.config.sources.map((item) => item.path);
  }
  if (state.library && Array.isArray(state.library.sources)) {
    return state.library.sources.map((item) => item.path);
  }
  return [];
}

const els = {
  banner: document.getElementById("banner"),
  span: document.getElementById("span-readout"),
  empty: document.getElementById("empty-state"),
  libraryBody: document.getElementById("library-body"),
  libraryView: document.getElementById("library-view"),
  dayView: document.getElementById("day-view"),
  monthNav: document.getElementById("month-nav"),
  calendar: document.getElementById("calendar"),
  dayTitle: document.getElementById("day-title"),
  dayMeta: document.getElementById("day-meta"),
  dayRail: document.getElementById("day-rail"),
  hourScale: document.getElementById("hour-scale"),
  dayEvents: document.getElementById("day-events"),
  viewerView: document.getElementById("viewer-view"),
  viewerTitle: document.getElementById("viewer-title"),
  viewerPlace: document.getElementById("viewer-place"),
  viewerClock: document.getElementById("viewer-clock"),
  camGrid: document.getElementById("cam-grid"),
  play: document.getElementById("btn-play"),
  scrubber: document.getElementById("scrubber"),
  plateMarks: document.getElementById("plate-marks"),
  scrubReadout: document.getElementById("scrub-readout"),
  showAll: document.getElementById("btn-show-all"),
  dumpStatus: document.getElementById("dump-status"),
  openDump: document.getElementById("btn-open-dump"),
  findPlates: document.getElementById("btn-find-plates"),
  plateStatus: document.getElementById("plate-status"),
  plateList: document.getElementById("plate-list"),
  plateZoom: document.getElementById("plate-zoom"),
  plateZoomLabel: document.getElementById("plate-zoom-label"),
  plateZoomSize: document.getElementById("plate-zoom-size"),
  plateZoomImg: document.getElementById("plate-zoom-img"),
  plateZoomVehicle: document.getElementById("plate-zoom-vehicle"),
  plateZoomFrame: document.getElementById("plate-zoom-frame"),
  plateShotDialog: document.getElementById("plate-shot-dialog"),
  plateShotCaption: document.getElementById("plate-shot-caption"),
  plateShotImg: document.getElementById("plate-shot-img"),
  platesView: document.getElementById("plates-view"),
  platesMeta: document.getElementById("plates-meta"),
  platesEmpty: document.getElementById("plates-empty"),
  platesCatalog: document.getElementById("plates-catalog"),
  platesDetail: document.getElementById("plates-detail"),
  platesDetailText: document.getElementById("plates-detail-text"),
  platesDetailState: document.getElementById("plates-detail-state"),
  platesDetailInfo: document.getElementById("plates-detail-info"),
  platesDetailImg: document.getElementById("plates-detail-img"),
  platesRawToggle: document.getElementById("plates-raw-toggle"),
  openPlateEvent: document.getElementById("btn-open-plate-event"),
  sourceStatus: document.getElementById("source-status"),
  folders: document.getElementById("folders-dialog"),
  sourceList: document.getElementById("source-list"),
  sourceAdd: document.getElementById("source-add-input"),
  outputDir: document.getElementById("output-dir-input"),
  scanStatus: document.getElementById("scan-status"),
  scanPanel: document.getElementById("scan-panel"),
  scanLog: document.getElementById("scan-log"),
  carView: document.getElementById("car-view"),
  carTitle: document.getElementById("car-title"),
  carMeta: document.getElementById("car-meta"),
  carCrop: document.getElementById("car-crop"),
  carMapWrap: document.getElementById("car-map-wrap"),
  carMap: document.getElementById("car-map"),
  carMapEmpty: document.getElementById("car-map-empty"),
  carSightings: document.getElementById("car-sightings"),
  btnBackCar: document.getElementById("btn-back-car"),
};

function formatElapsed(sec) {
  const total = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function setScanControls(running) {
  document.getElementById("btn-rescan").disabled = running;
  document.getElementById("btn-save-folders").disabled = running;
}

function renderScanStatus(status) {
  if (!status || status.state === "idle") {
    els.scanPanel.hidden = true;
    els.scanStatus.textContent = "";
    els.scanLog.replaceChildren();
    setScanControls(false);
    return;
  }
  els.scanPanel.hidden = false;
  setScanControls(status.state === "running");
  if (status.state === "running") {
    const rate = status.filesPerSec ? `${status.filesPerSec.toFixed(1)} files/s` : "0 files/s";
    els.scanStatus.textContent = `Scanning ${formatElapsed(status.elapsedSec)} · ${status.clipsIndexed} clips · ${status.filesSeen} files · ${rate}`;
  } else if (status.state === "complete") {
    els.scanStatus.textContent = `Scan complete in ${formatElapsed(status.elapsedSec)}. ${status.clipsIndexed} clips indexed.`;
  } else if (status.state === "error") {
    els.scanStatus.textContent = `Scan failed after ${formatElapsed(status.elapsedSec)}: ${status.error || "unknown error"}`;
  }
  const rows = Array.isArray(status.recent) ? status.recent.slice().reverse() : [];
  els.scanLog.replaceChildren();
  for (const item of rows) {
    const line = document.createElement("li");
    const elapsed = formatElapsed(item.elapsedSec || 0);
    line.textContent = `${elapsed}  ${item.action}  ${item.path}`;
    els.scanLog.append(line);
  }
}

let scanTimer = null;
let scanWatchId = 0;
let plateWatchId = 0;
let lastLibraryReload = 0;
let putInFlight = false;

async function reloadLibrary() {
  state.config = await api("/api/config");
  if (!state.config.hasLibrary) {
    state.library = null;
    renderLibrary();
    return;
  }
  state.library = await api("/api/library");
  if (!state.month && state.library.months.length) {
    state.month = state.library.months[state.library.months.length - 1];
  }
  renderLibrary();
  if (els.dayView && !els.dayView.hidden && state.day) {
    try {
      state.dayDetail = await api(`/api/days/${state.day}`);
      renderDayPage();
    } catch (err) {
      showBanner(err.message);
    }
  }
}

async function pollScan(watchId) {
  if (watchId !== scanWatchId) {
    return;
  }
  try {
    const status = await api("/api/scan");
    if (watchId !== scanWatchId) {
      return;
    }
    renderScanStatus(status);
    if (status.state === "running") {
      const now = Date.now();
      if (now - lastLibraryReload > 5000) {
        lastLibraryReload = now;
        await reloadLibrary();
      }
      scanTimer = setTimeout(() => pollScan(watchId), 1000);
      return;
    }
    if (status.state === "complete" || status.state === "error") {
      await reloadLibrary();
    }
  } catch (err) {
    if (watchId !== scanWatchId) {
      return;
    }
    showBanner(err.message);
  }
}

function watchScan() {
  scanWatchId += 1;
  if (scanTimer) {
    clearTimeout(scanTimer);
    scanTimer = null;
  }
  lastLibraryReload = 0;
  pollScan(scanWatchId);
}

function showBanner(text) {
  if (!text) {
    els.banner.hidden = true;
    els.banner.textContent = "";
    return;
  }
  els.banner.hidden = false;
  els.banner.textContent = text;
}

async function api(path, options) {
  const response = await fetch(path, options);
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch (err) {
      throw new Error(text.slice(0, 300) || `HTTP ${response.status}`);
    }
  }
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body;
}

function formatClock(stampIso, elapsedSec) {
  const start = new Date(stampIso);
  const at = new Date(start.getTime() + elapsedSec * 1000);
  const pad = (n) => String(n).padStart(2, "0");
  return `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())} ${pad(at.getHours())}:${pad(at.getMinutes())}:${pad(at.getSeconds())}`;
}

function formatDuration(sec) {
  const total = Math.max(0, Math.round(sec));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) {
    return `${h}h ${m}m`;
  }
  if (m > 0) {
    return `${m}m ${s}s`;
  }
  return `${s}s`;
}

function formatScrub(sec) {
  const total = Math.max(0, Math.floor(sec));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function monthLabel(ym) {
  const [year, month] = ym.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleString("en-US", {
    month: "long",
    year: "numeric",
  });
}

function parseHash() {
  const raw = (location.hash || "#/").replace(/^#/, "");
  const parts = raw.split("/").filter(Boolean);
  if (parts[0] === "e" && parts[1]) {
    return { eventId: parts[1] };
  }
  if (parts[0] === "plates") {
    return { plates: true };
  }
  if (parts[0] === "p" && parts[1]) {
    try {
      return { plate: decodeURIComponent(parts[1]).toUpperCase() };
    } catch (err) {
      return { plate: parts[1].toUpperCase() };
    }
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(parts[0] || "")) {
    return { day: parts[0], month: parts[0].slice(0, 7) };
  }
  if (/^\d{4}-\d{2}$/.test(parts[0] || "")) {
    return { month: parts[0] };
  }
  return {};
}

function setHash(path) {
  const next = `#/${path.replace(/^\//, "")}`;
  if (location.hash !== next) {
    location.hash = next;
  }
}

function daysInMonth(ym) {
  const [year, month] = ym.split("-").map(Number);
  return new Date(year, month, 0).getDate();
}

function firstWeekday(ym) {
  const [year, month] = ym.split("-").map(Number);
  return new Date(year, month - 1, 1).getDay();
}

function kindLabel(kind) {
  if (kind === "saved") return "Saved";
  if (kind === "sentry") return "Sentry";
  if (kind === "recent") return "Recent";
  return "Other";
}

function formatCoord(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "";
  }
  return value.toFixed(5).replace(/\.?0+$/, "");
}

function placeLine(event) {
  return [event.city, event.street].filter(Boolean).join(" · ");
}

function coordLine(event) {
  if (typeof event.latitude !== "number" || typeof event.longitude !== "number") {
    return "";
  }
  return `${formatCoord(event.latitude)}, ${formatCoord(event.longitude)}`;
}

function locationSourceLabel(source) {
  if (source === "event.json") return "Tesla event pin";
  if (source === "sei") return "clip GPS";
  if (source === "mp4") return "clip tags";
  return "";
}

function renderViewerPlace(event) {
  if (!els.viewerPlace) {
    return;
  }
  const line = placeLine(event);
  const coords = coordLine(event);
  els.viewerPlace.replaceChildren();
  if (!line && !coords) {
    els.viewerPlace.hidden = true;
    return;
  }
  els.viewerPlace.hidden = false;
  if (line) {
    const place = document.createElement("span");
    place.textContent = line;
    els.viewerPlace.append(place);
  }
  if (coords) {
    if (event.mapUrl) {
      const link = document.createElement("a");
      link.href = event.mapUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = coords;
      els.viewerPlace.append(link);
    } else {
      const text = document.createElement("span");
      text.textContent = coords;
      els.viewerPlace.append(text);
    }
  }
  const source = locationSourceLabel(event.locationSource);
  if (source) {
    const note = document.createElement("span");
    note.className = "place-source";
    note.textContent = source;
    els.viewerPlace.append(note);
  }
}

function renderSpan() {
  if (!state.config) {
    els.span.textContent = "Add clip folders to begin.";
    return;
  }
  if (!state.config.hasLibrary) {
    els.span.textContent = "No clip folders are set.";
    return;
  }
  const lib = state.library;
  const sourceCount = state.config.sources ? state.config.sources.length : 0;
  if (!lib || !lib.span) {
    els.span.textContent = `${sourceCount} sources · ${state.config.clipCount} files. No Tesla clips found.`;
    return;
  }
  const start = lib.span.start.replace("T", " ").slice(0, 16);
  const end = lib.span.end.replace("T", " ").slice(0, 16);
  els.span.textContent = `${sourceCount} sources · ${lib.eventCount} events · ${lib.clipCount} files · ${start} → ${end}`;
}

function attachedSources() {
  const sources = (state.library && state.library.sources) || (state.config && state.config.sources) || [];
  return sources;
}

function renderSourceStatus() {
  const sources = attachedSources();
  els.sourceStatus.replaceChildren();
  if (!sources.length) {
    els.sourceStatus.hidden = true;
    return;
  }
  els.sourceStatus.hidden = false;
  for (const source of sources) {
    const item = document.createElement("li");
    if (!source.available) {
      item.className = "missing";
      item.textContent = `${source.label}: not attached`;
    } else {
      item.textContent = `${source.label}: ${source.clipCount} files`;
    }
    item.title = source.path;
    els.sourceStatus.append(item);
  }
}

function missingSourceMessage() {
  const missing = attachedSources().filter((item) => !item.available);
  if (!missing.length) {
    return "";
  }
  return `Not attached: ${missing.map((item) => item.path).join("; ")}`;
}

function renderEmpty() {
  if (!state.config || !state.config.hasLibrary) {
    els.empty.hidden = false;
    els.libraryBody.hidden = true;
    els.empty.textContent = "Add clip folders in Folders, then scan.";
    return;
  }
  if (!state.library || state.library.days.length === 0) {
    els.empty.hidden = false;
    els.libraryBody.hidden = true;
    const present = attachedSources().filter((item) => item.available);
    els.empty.textContent = present.length
      ? "No Tesla clip names were found in the attached folders. Names look like 2023-08-21_15-30-45-front.mp4."
      : "No attached source folder. Attach the drive, then Rescan.";
    return;
  }
  els.empty.hidden = true;
  els.libraryBody.hidden = false;
}

function renderMonthNav() {
  const months = state.library ? state.library.months : [];
  els.monthNav.replaceChildren();
  for (const ym of months) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = monthLabel(ym);
    if (ym === state.month) {
      button.setAttribute("aria-current", "true");
    }
    button.addEventListener("click", () => {
      state.month = ym;
      setHash(ym);
      showPage("library");
      renderLibrary();
    });
    els.monthNav.append(button);
  }
}

function renderCalendar() {
  els.calendar.replaceChildren();
  if (!state.month) {
    return;
  }
  const heading = document.createElement("h2");
  heading.textContent = monthLabel(state.month);
  const dow = document.createElement("div");
  dow.className = "dow";
  for (const name of WEEKDAYS) {
    const span = document.createElement("span");
    span.textContent = name;
    dow.append(span);
  }
  const grid = document.createElement("div");
  grid.className = "cal-grid";
  const byDate = new Map((state.library.days || []).map((day) => [day.date, day]));
  const blanks = firstWeekday(state.month);
  for (let i = 0; i < blanks; i += 1) {
    const spacer = document.createElement("div");
    grid.append(spacer);
  }
  const count = daysInMonth(state.month);
  for (let dayNum = 1; dayNum <= count; dayNum += 1) {
    const date = `${state.month}-${String(dayNum).padStart(2, "0")}`;
    const info = byDate.get(date);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cal-day";
    button.disabled = !info;
    if (info) {
      button.classList.add("has-clips");
    }
    if (date === state.day) {
      button.setAttribute("aria-current", "true");
    }
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = String(dayNum);
    const meta = document.createElement("span");
    meta.className = "meta";
    meta.textContent = info ? `${info.eventCount} · ${info.times[0]}` : "";
    button.append(num, meta);
    button.addEventListener("click", () => openDay(date));
    grid.append(button);
  }
  els.calendar.append(heading, dow, grid);
}

async function openDay(date) {
  state.day = date;
  state.month = date.slice(0, 7);
  try {
    state.dayDetail = await api(`/api/days/${date}`);
    showBanner("");
  } catch (err) {
    showBanner(err.message);
    return;
  }
  showPage("day");
  renderSpan();
  renderDayPage();
  setHash(date);
}

function renderDayPage() {
  if (!state.day || !state.dayDetail) {
    return;
  }
  const detail = state.dayDetail;
  const readable = new Date(`${detail.date}T00:00:00`).toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
  els.dayTitle.textContent = readable;
  els.dayMeta.textContent = `${detail.eventCount} events · ${formatDuration(detail.durationSec)}`;
  els.hourScale.replaceChildren();
  for (const hour of [0, 6, 12, 18, 24]) {
    const item = document.createElement("li");
    item.textContent = `${String(hour).padStart(2, "0")}:00`;
    els.hourScale.append(item);
  }
  els.dayRail.replaceChildren();
  els.dayEvents.replaceChildren();
  for (const event of detail.events) {
    const start = new Date(event.start);
    const minutes = start.getHours() * 60 + start.getMinutes() + start.getSeconds() / 60;
    const left = (minutes / 1440) * 100;
    const width = Math.max((event.durationSec / 86400) * 100, 0.7);
    const rail = document.createElement("button");
    rail.type = "button";
    rail.className = "rail-event";
    rail.style.left = `${left}%`;
    rail.style.width = `${width}%`;
    rail.textContent = event.time.slice(0, 5);
    rail.title = `${event.time} ${kindLabel(event.kind)} · ${event.sourceLabel}${placeLine(event) ? ` · ${placeLine(event)}` : ""}`;
    rail.addEventListener("click", () => openEvent(event.id));
    els.dayRail.append(rail);

    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const time = document.createElement("span");
    time.textContent = event.time;
    const kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = kindLabel(event.kind);
    const source = document.createElement("span");
    source.className = "source-tag";
    source.textContent = event.sourceLabel;
    source.title = event.sourcePath;
    const place = document.createElement("span");
    place.className = "place";
    const placeBits = [placeLine(event), coordLine(event)].filter(Boolean);
    place.textContent = placeBits.join(" · ");
    place.title = locationSourceLabel(event.locationSource) || "";
    const cams = document.createElement("span");
    cams.textContent = event.cameras.map((cam) => cam.label).join(" · ");
    const dur = document.createElement("span");
    dur.textContent = formatDuration(event.durationSec);
    button.append(time, kind, source, place, cams, dur);
    button.addEventListener("click", () => openEvent(event.id));
    item.append(button);
    els.dayEvents.append(item);
  }
}

function renderLibrary() {
  renderSpan();
  renderEmpty();
  renderSourceStatus();
  if (!state.library) {
    return;
  }
  showBanner(missingSourceMessage());
  if (state.library.days.length === 0) {
    return;
  }
  renderMonthNav();
  renderCalendar();
}

function syncPlayerState() {
  if (!player) {
    return;
  }
  state.elapsed = player.elapsed();
  state.playing = player.isPlaying();
  for (const camera of state.videos.keys()) {
    const index = player.loadedIndex(camera);
    if (index == null) {
      state.loadedSegment.set(camera, null);
    } else {
      state.loadedSegment.set(camera, index);
    }
  }
}

function pauseAll() {
  if (player) {
    player.pause();
  }
  state.playing = false;
  els.play.textContent = "Play";
  for (const buf of state.buffers.values()) {
    for (const video of buf.videos) {
      video.pause();
    }
  }
}

function playAll() {
  if (player) {
    player.play();
  }
  state.playing = true;
  els.play.textContent = "Pause";
  for (const [camera, video] of state.videos) {
    if (player && player.loadedIndex(camera) == null) {
      continue;
    }
    const playAttempt = video.play();
    if (playAttempt && playAttempt.catch) {
      playAttempt.catch(() => {});
    }
  }
}

function videoUrl(camera, index) {
  return `/api/events/${state.event.id}/cameras/${encodeURIComponent(camera)}/segments/${index}`;
}

function cameraTile(camera) {
  const buf = bufferFor(camera);
  const video = buf ? buf.videos[0] : state.videos.get(camera);
  return video ? video.closest(".cam-tile") : null;
}

function bufferFor(camera) {
  return state.buffers.get(camera);
}

function shownVideo(camera) {
  const buf = bufferFor(camera);
  return buf ? buf.videos[buf.shown] : state.videos.get(camera);
}

function hiddenVideo(camera) {
  const buf = bufferFor(camera);
  return buf ? buf.videos[1 - buf.shown] : null;
}

function nextLoadToken(camera) {
  const token = (state.loadToken.get(camera) || 0) + 1;
  state.loadToken.set(camera, token);
  return token;
}

function loadTokenIsCurrent(camera, token) {
  return state.loadToken.get(camera) === token;
}

function videoHoldsSegment(video, index) {
  return video && video.dataset.segment === String(index) && Boolean(video.getAttribute("src"));
}

function swapIn(camera, incoming, local) {
  const buf = bufferFor(camera);
  const outgoing = buf.videos[buf.shown];
  if (Number.isFinite(local)) {
    incoming.currentTime = local;
  }
  if (incoming !== outgoing) {
    incoming.classList.remove("standby");
    outgoing.classList.add("standby");
    outgoing.pause();
    buf.shown = buf.videos.indexOf(incoming);
    state.videos.set(camera, incoming);
  }
}

function whenFrameReady(video, local, onReady) {
  const show = () => {
    if (local > 0.05 && Math.abs(video.currentTime - local) > 0.12) {
      video.addEventListener("seeked", onReady, { once: true });
      video.currentTime = local;
      return;
    }
    onReady();
  };
  if (video.readyState >= 2) {
    show();
    return;
  }
  video.addEventListener("loadeddata", show, { once: true });
}

function activateClip(camera, video, hit, token) {
  whenFrameReady(video, hit.local, () => {
    if (!loadTokenIsCurrent(camera, token) || !player) {
      return;
    }
    swapIn(camera, video, hit.local);
    player.ready(camera);
    syncPlayerState();
    if (player.isPlaying()) {
      const playAttempt = video.play();
      if (playAttempt && playAttempt.catch) {
        playAttempt.catch(() => {});
      }
    }
    updateViewerHud();
  });
}

function maybePrefetch(camera) {
  if (!player || !state.event || player.isSeeking(camera)) {
    return;
  }
  const track = state.event.cameras.find((item) => item.id === camera);
  const index = player.loadedIndex(camera);
  if (!track || index == null) {
    return;
  }
  const next = track.segments[index + 1];
  if (!next) {
    return;
  }
  const shown = shownVideo(camera);
  const remain = shown && Number.isFinite(shown.duration) ? shown.duration - shown.currentTime : 99;
  if (remain > 5) {
    return;
  }
  const hidden = hiddenVideo(camera);
  if (!hidden || videoHoldsSegment(hidden, next.index)) {
    return;
  }
  hidden.dataset.segment = String(next.index);
  hidden.preload = "auto";
  hidden.src = videoUrl(camera, next.index);
}

function bindPlayer() {
  player = TeslaPlayback.createPlayer({
    durationSec: state.event.durationSec,
    cameras: state.event.cameras,
    host: {
      load(camera, hit) {
        const tile = cameraTile(camera);
        const missing = tile.querySelector(".missing");
        missing.hidden = true;
        const token = nextLoadToken(camera);
        const shown = shownVideo(camera);
        const hidden = hiddenVideo(camera);
        if (videoHoldsSegment(shown, hit.segment.index)) {
          activateClip(camera, shown, hit, token);
          return;
        }
        if (hidden && videoHoldsSegment(hidden, hit.segment.index)) {
          activateClip(camera, hidden, hit, token);
          return;
        }
        const target = hidden && shown.getAttribute("src") ? hidden : shown;
        target.dataset.segment = String(hit.segment.index);
        target.src = videoUrl(camera, hit.segment.index);
        activateClip(camera, target, hit, token);
      },
      sync(camera, local) {
        const video = shownVideo(camera);
        if (video && Math.abs(video.currentTime - local) > 0.25 && !player.isSeeking(camera)) {
          video.currentTime = local;
        }
      },
      clear(camera) {
        const tile = cameraTile(camera);
        const missing = tile.querySelector(".missing");
        missing.hidden = false;
      },
      pause() {
        els.play.textContent = "Play";
        for (const buf of state.buffers.values()) {
          for (const video of buf.videos) {
            video.pause();
          }
        }
      },
    },
  });
}

function seekTo(elapsed) {
  if (!state.event || !player) {
    return;
  }
  player.seekTo(elapsed);
  syncPlayerState();
  updateViewerHud();
}

function masterCamera() {
  return player ? player.masterCamera() : null;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function lerpBox(a, b, t) {
  return {
    x1: lerp(a.x1, b.x1, t),
    y1: lerp(a.y1, b.y1, t),
    x2: lerp(a.x2, b.x2, t),
    y2: lerp(a.y2, b.y2, t),
  };
}

function videoContentRect(video) {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) {
    return null;
  }
  const cw = video.clientWidth;
  const ch = video.clientHeight;
  const scale = Math.min(cw / vw, ch / vh);
  const width = vw * scale;
  const height = vh * scale;
  return {
    left: (cw - width) / 2,
    top: (ch - height) / 2,
    width,
    height,
    vw,
    vh,
  };
}

function boxAtElapsed(hits, elapsed) {
  const list = hits
    .filter((hit) => hit.bbox)
    .slice()
    .sort((a, b) => a.elapsedSec - b.elapsedSec);
  if (!list.length) {
    return null;
  }
  for (let i = 0; i < list.length - 1; i += 1) {
    const a = list[i];
    const b = list[i + 1];
    const gap = b.elapsedSec - a.elapsedSec;
    if (gap > 0 && gap <= 1.5 && elapsed >= a.elapsedSec && elapsed <= b.elapsedSec) {
      return lerpBox(a.bbox, b.bbox, (elapsed - a.elapsedSec) / gap);
    }
  }
    let best = null;
    let bestDist = 1.25;
  for (const hit of list) {
    const dist = Math.abs(hit.elapsedSec - elapsed);
    if (dist <= bestDist) {
      bestDist = dist;
      best = hit.bbox;
    }
  }
  return best;
}

function overlayBoxesAt(elapsed) {
  const plates = state.plateStatus && state.plateStatus.plates ? state.plateStatus.plates : [];
  const boxes = [];
  for (const plate of plates) {
    const selectedHit =
      plate.text === state.selectedPlate && plate.hits && plate.hits[state.plateHitIndex]
        ? plate.hits[state.plateHitIndex]
        : null;
    const byCamera = new Map();
    for (const hit of plate.hits || []) {
      if (!hit.camera || !hit.bbox) {
        continue;
      }
      if (!byCamera.has(hit.camera)) {
        byCamera.set(hit.camera, []);
      }
      byCamera.get(hit.camera).push(hit);
    }
    for (const [camera, hits] of byCamera) {
      let bbox = null;
      if (selectedHit && selectedHit.camera === camera && selectedHit.bbox) {
        bbox = selectedHit.bbox;
      } else {
        bbox = boxAtElapsed(hits, elapsed);
      }
      if (!bbox) {
        continue;
      }
      boxes.push({
        camera,
        text: plate.text,
        jurisdiction: jurisdictionShort(plate),
        bbox,
        selected: plate.text === state.selectedPlate,
      });
    }
  }
  return boxes;
}

function updatePlateOverlays() {
  if (!els.camGrid) {
    return;
  }
  const boxes = state.event ? overlayBoxesAt(state.elapsed) : [];
  for (const tile of els.camGrid.querySelectorAll(".cam-tile")) {
    const overlay = tile.querySelector(".plate-overlay");
    if (!overlay) {
      continue;
    }
    overlay.replaceChildren();
    const camera = tile.dataset.camera;
    const video = shownVideo(camera);
    const rect = video ? videoContentRect(video) : null;
    if (!rect) {
      continue;
    }
    for (const item of boxes) {
      if (item.camera !== camera) {
        continue;
      }
      const glow = document.createElement("div");
      glow.className = item.selected ? "plate-glow selected" : "plate-glow";
      const left = rect.left + (item.bbox.x1 / rect.vw) * rect.width;
      const top = rect.top + (item.bbox.y1 / rect.vh) * rect.height;
      const width = ((item.bbox.x2 - item.bbox.x1) / rect.vw) * rect.width;
      const height = ((item.bbox.y2 - item.bbox.y1) / rect.vh) * rect.height;
      glow.style.left = `${left}px`;
      glow.style.top = `${top}px`;
      glow.style.width = `${Math.max(width, 8)}px`;
      glow.style.height = `${Math.max(height, 8)}px`;
      const label = document.createElement("span");
      label.textContent = item.jurisdiction ? `${item.text} ${item.jurisdiction}` : item.text;
      glow.append(label);
      overlay.append(glow);
    }
  }
}

function updateViewerHud() {
  if (!state.event) {
    return;
  }
  els.viewerClock.textContent = formatClock(state.event.start, state.elapsed);
  els.scrubber.max = String(state.event.durationSec);
  els.scrubber.value = String(state.elapsed);
  els.scrubReadout.textContent = `${formatScrub(state.elapsed)} / ${formatScrub(state.event.durationSec)}`;
  updatePlateOverlays();
}

function setFocus(camera) {
  state.focused = camera;
  els.camGrid.classList.toggle("focus-mode", Boolean(camera));
  els.showAll.hidden = !camera;
  for (const tile of els.camGrid.querySelectorAll(".cam-tile")) {
    tile.classList.toggle("focused", tile.dataset.camera === camera);
  }
  updatePlateOverlays();
}

function buildViewer() {
  els.camGrid.replaceChildren();
  state.videos.clear();
  state.loadedSegment.clear();
  state.buffers.clear();
  state.loadToken.clear();
  player = null;
  els.camGrid.dataset.layout = state.event.layout;
  els.camGrid.classList.remove("focus-mode");
  state.focused = null;
  els.showAll.hidden = true;
  els.viewerTitle.textContent = `${state.event.date} ${state.event.time} · ${kindLabel(state.event.kind)} · ${state.event.sourceLabel} · ${state.event.cameras.length} cameras`;
  renderViewerPlace(state.event);
  const extraIndex = { n: 0 };
  for (const camera of state.event.cameras) {
    const tile = document.createElement("div");
    tile.className = "cam-tile";
    tile.dataset.camera = camera.id;
    tile.dataset.area = AREA_FOR_CAMERA[camera.id] || `extra${extraIndex.n++}`;
    const label = document.createElement("p");
    label.className = "label";
    label.textContent = camera.label;
    const missing = document.createElement("p");
    missing.className = "missing";
    missing.textContent = "No clip at this time";
    missing.hidden = true;
    const videos = [0, 1].map((slot) => {
      const video = document.createElement("video");
      video.playsInline = true;
      video.preload = "auto";
      video.muted = true;
      if (slot === 1) {
        video.classList.add("standby");
      }
      video.addEventListener("timeupdate", () => {
        if (!player || state.videos.get(camera.id) !== video) {
          return;
        }
        player.timeUpdate(camera.id, video.currentTime);
        maybePrefetch(camera.id);
        syncPlayerState();
        updateViewerHud();
      });
      video.addEventListener("error", () => {
        if (!player || !player.isSeeking(camera.id)) {
          return;
        }
        if (video.dataset.segment === String(player.loadedIndex(camera.id))) {
          player.ready(camera.id);
        }
      });
      video.addEventListener("ended", () => {
        if (!player || state.videos.get(camera.id) !== video) {
          return;
        }
        player.ended(camera.id);
        syncPlayerState();
        updateViewerHud();
      });
      return video;
    });
    tile.addEventListener("click", () => {
      setFocus(state.focused === camera.id ? null : camera.id);
    });
    tile.append(videos[0], videos[1], label, missing);
    const overlay = document.createElement("div");
    overlay.className = "plate-overlay";
    tile.append(overlay);
    els.camGrid.append(tile);
    state.buffers.set(camera.id, { videos, shown: 0 });
    state.videos.set(camera.id, videos[0]);
  }
  bindPlayer();
  const start = typeof state.pendingSeek === "number" ? state.pendingSeek : 0;
  state.pendingSeek = null;
  seekTo(start);
  state.selectedPlate = null;
  state.plateHitIndex = 0;
  hidePlateZoom();
  renderPlateMarks();
  if (plateOverlayObserver) {
    plateOverlayObserver.disconnect();
  }
  plateOverlayObserver = new ResizeObserver(() => updatePlateOverlays());
  plateOverlayObserver.observe(els.camGrid);
}

function destroyCarMap() {
  if (carMap) {
    carMap.remove();
    carMap = null;
  }
}

function plateCropUrl(cropId) {
  return cropId ? `/api/plates/crops/${cropId}` : "";
}

function formatSightingWhen(iso, day) {
  if (iso) {
    const stamp = new Date(iso);
    if (!Number.isNaN(stamp.getTime())) {
      return stamp.toLocaleString("en-US", {
        weekday: "short",
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    }
  }
  return day || "";
}

function rememberCarReturn() {
  state.carReturnEventId = state.event ? state.event.id : null;
  state.carReturnDay = state.event ? state.event.date : state.day;
  state.carReturnPlates = Boolean(els.platesView && !els.platesView.hidden);
}

function openCarPage(text) {
  rememberCarReturn();
  setHash(`p/${encodeURIComponent(text)}`);
}

function openCarEvent(eventId, elapsed) {
  state.pendingSeek = typeof elapsed === "number" ? elapsed : 0;
  state.viewerReturnPlate = state.carPlate;
  openEvent(eventId);
}

function leaveCarPage() {
  if (state.carReturnEventId) {
    openEvent(state.carReturnEventId);
    return;
  }
  if (state.carReturnPlates) {
    openPlates();
    return;
  }
  if (state.carReturnDay) {
    openDay(state.carReturnDay);
    return;
  }
  showLibrary();
  setHash(state.month || "");
  renderLibrary();
}

async function loadCarPage(text) {
  state.carPlate = text;
  showPage("car");
  if (els.btnBackCar) {
    if (state.carReturnEventId) {
      els.btnBackCar.textContent = "Back to clip";
    } else if (state.carReturnPlates) {
      els.btnBackCar.textContent = "Back to plates";
    } else if (state.carReturnDay) {
      els.btnBackCar.textContent = "Back to day";
    } else {
      els.btnBackCar.textContent = "Back to calendar";
    }
  }
  if (els.carTitle) {
    els.carTitle.textContent = text;
  }
  if (els.carMeta) {
    els.carMeta.textContent = "Loading…";
  }
  if (els.carSightings) {
    els.carSightings.replaceChildren();
  }
  if (els.carCrop) {
    els.carCrop.hidden = true;
    els.carCrop.removeAttribute("src");
  }
  destroyCarMap();
  if (els.carMapWrap) {
    els.carMapWrap.hidden = true;
  }
  if (els.carMapEmpty) {
    els.carMapEmpty.hidden = true;
  }
  try {
    const dossier = await api(`/api/plates/${encodeURIComponent(text)}`);
    renderCarPage(dossier);
  } catch (err) {
    if (els.carMeta) {
      els.carMeta.textContent = err.message;
    }
    showBanner(err.message);
  }
}

function renderCarPage(dossier) {
  const plate = { jurisdiction: dossier.jurisdiction, text: dossier.text };
  const code = jurisdictionShort(plate);
  if (els.carTitle) {
    els.carTitle.textContent = dossier.text;
    if (code) {
      const badge = document.createElement("span");
      badge.className = "plate-state";
      badge.textContent = code;
      els.carTitle.append(" ", badge);
    }
  }
  if (els.carCrop) {
    if (dossier.cropId) {
      els.carCrop.src = plateCropUrl(dossier.cropId);
      els.carCrop.alt = dossier.text;
      els.carCrop.hidden = false;
    } else {
      els.carCrop.hidden = true;
    }
  }
  const bits = [];
  const guessed = jurisdictionLine(plate);
  if (guessed) {
    bits.push(guessed);
  }
  bits.push(
    `${dossier.eventCount} clip${dossier.eventCount === 1 ? "" : "s"}`,
    `${dossier.appearanceCount} sighting${dossier.appearanceCount === 1 ? "" : "s"}`,
  );
  if (dossier.firstSeen && dossier.lastSeen) {
    const first = formatSightingWhen(dossier.firstSeen);
    const last = formatSightingWhen(dossier.lastSeen);
    bits.push(first === last ? first : `${first} – ${last}`);
  }
  if (dossier.places && dossier.places.length) {
    bits.push(dossier.places.slice(0, 4).join(" · "));
  }
  if (els.carMeta) {
    els.carMeta.textContent = bits.join(" · ");
  }
  document.title = `${dossier.text} · Tesla video viewer`;
  renderCarMap(dossier);
  renderCarSightings(dossier);
}

function renderCarMap(dossier) {
  destroyCarMap();
  const points = dossier.points || [];
  if (!els.carMapWrap || !els.carMapEmpty || !els.carMap) {
    return;
  }
  if (!points.length) {
    els.carMapWrap.hidden = true;
    els.carMapEmpty.hidden = false;
    return;
  }
  els.carMapEmpty.hidden = true;
  els.carMapWrap.hidden = false;
  if (typeof L === "undefined") {
    const fallback = document.createElement("ul");
    fallback.className = "car-map-fallback";
    for (const point of points) {
      const item = document.createElement("li");
      const clocks = (point.sightings || []).map((sight) => {
        const day = sight.day ? sight.day.slice(5).replace("-", "/") : "";
        return [day, sight.clock].filter(Boolean).join(" ");
      }).join(" · ");
      const link = document.createElement("a");
      link.href = point.mapUrl || `https://www.openstreetmap.org/?mlat=${point.latitude}&mlon=${point.longitude}#map=17/${point.latitude}/${point.longitude}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      const coords = `${formatCoord(point.latitude)}, ${formatCoord(point.longitude)}`;
      link.textContent = clocks ? `${coords} · ${clocks}` : coords;
      item.append(link);
      fallback.append(item);
    }
    els.carMap.replaceChildren(fallback);
    return;
  }
  els.carMap.replaceChildren();
  carMap = L.map(els.carMap, { scrollWheelZoom: true });
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap",
  }).addTo(carMap);
  const latlngs = [];
  for (const point of points) {
    const latlng = [point.latitude, point.longitude];
    latlngs.push(latlng);
    const marker = L.marker(latlng).addTo(carMap);
    const clocks = (point.sightings || []).map((sight) => {
      const day = sight.day ? sight.day.slice(5).replace("-", "/") : "";
      return [day, sight.clock].filter(Boolean).join(" ");
    });
    const place = [point.city, point.street].filter(Boolean).join(" · ");
    const label = clocks.join(" · ") || "Seen here";
    marker.bindTooltip(label, { permanent: points.length <= 12, direction: "top" });
    const popup = document.createElement("div");
    popup.className = "car-map-popup";
    const heading = document.createElement("p");
    heading.textContent = place || `${formatCoord(point.latitude)}, ${formatCoord(point.longitude)}`;
    popup.append(heading);
    for (const sight of point.sightings || []) {
      const row = document.createElement("p");
      row.textContent = [sight.day, sight.clock].filter(Boolean).join(" ");
      if (sight.eventId) {
        const open = document.createElement("button");
        open.type = "button";
        open.textContent = "Open clip";
        open.addEventListener("click", () => {
          const event = (dossier.events || []).find((item) => item.eventId === sight.eventId);
          openCarEvent(sight.eventId, event ? event.firstElapsedSec : 0);
        });
        row.append(" ", open);
      }
      popup.append(row);
    }
    marker.bindPopup(popup);
  }
  const path = (dossier.events || [])
    .filter((item) => typeof item.latitude === "number" && typeof item.longitude === "number")
    .map((item) => [item.latitude, item.longitude]);
  const uniquePath = [];
  for (const pair of path) {
    const prev = uniquePath[uniquePath.length - 1];
    if (!prev || prev[0] !== pair[0] || prev[1] !== pair[1]) {
      uniquePath.push(pair);
    }
  }
  if (uniquePath.length >= 2) {
    L.polyline(uniquePath, { color: "#ffc14d", weight: 3, opacity: 0.85 }).addTo(carMap);
  }
  if (latlngs.length === 1) {
    carMap.setView(latlngs[0], 15);
  } else {
    carMap.fitBounds(latlngs, { padding: [28, 28], maxZoom: 16 });
  }
  setTimeout(() => {
    if (carMap) {
      carMap.invalidateSize();
    }
  }, 0);
}

function renderCarSightings(dossier) {
  if (!els.carSightings) {
    return;
  }
  els.carSightings.replaceChildren();
  for (const event of dossier.events || []) {
    const item = document.createElement("li");
    item.className = "car-sighting";
    const head = document.createElement("div");
    head.className = "car-sighting-head";
    if (event.cropId) {
      const img = document.createElement("img");
      img.alt = dossier.text;
      img.src = plateCropUrl(event.cropId);
      head.append(img);
    }
    const body = document.createElement("div");
    const when = document.createElement("p");
    when.className = "car-sighting-when";
    when.textContent = formatSightingWhen(event.time || event.start, event.date);
    const place = document.createElement("p");
    place.className = "car-sighting-place";
    const placeBits = [
      event.kind ? kindLabel(event.kind) : "",
      event.sourceLabel,
      [event.city, event.street].filter(Boolean).join(" · "),
      typeof event.latitude === "number" ? `${formatCoord(event.latitude)}, ${formatCoord(event.longitude)}` : "",
    ].filter(Boolean);
    place.textContent = placeBits.join(" · ");
    if (event.mapUrl) {
      const mapLink = document.createElement("a");
      mapLink.href = event.mapUrl;
      mapLink.target = "_blank";
      mapLink.rel = "noreferrer";
      mapLink.textContent = "Map";
      place.append(" · ", mapLink);
    }
    const hits = document.createElement("p");
    hits.className = "car-sighting-hits";
    const hitBits = (event.hits || []).map((hit) => {
      const clock = hit.clock ? ` (${hit.clock})` : "";
      return `${hit.cameraLabel} ${plateTimeLabel(hit.elapsedSec)}${clock}`;
    });
    hits.textContent = `${event.hitCount} hit${event.hitCount === 1 ? "" : "s"} · ${hitBits.join(" · ")}`;
    const open = document.createElement("button");
    open.type = "button";
    open.textContent = event.available ? "Open clip" : "Clip not in library";
    open.disabled = !event.available;
    open.addEventListener("click", () => openCarEvent(event.eventId, event.firstElapsedSec));
    body.append(when, place, hits, open);
    head.append(body);
    item.append(head);
    if (event.clip && event.clip.videoUrl) {
      const video = document.createElement("video");
      video.controls = true;
      video.preload = "none";
      video.playsInline = true;
      video.src = event.clip.videoUrl;
      const local = Number(event.clip.localSec) || 0;
      const seek = () => {
        if (Number.isFinite(video.duration) && video.duration > 0) {
          video.currentTime = Math.min(local, Math.max(video.duration - 0.05, 0));
        } else {
          video.currentTime = local;
        }
      };
      video.addEventListener("loadedmetadata", seek, { once: true });
      item.append(video);
    }
    els.carSightings.append(item);
  }
}

function showPage(name) {
  if (name !== "viewer") {
    pauseAll();
  }
  if (name !== "viewer" && name !== "car") {
    player = null;
    state.event = null;
    hidePlateZoom();
  }
  if (name !== "car") {
    destroyCarMap();
  }
  els.libraryView.hidden = name !== "library";
  if (els.dayView) {
    els.dayView.hidden = name !== "day";
  }
  if (els.platesView) {
    els.platesView.hidden = name !== "plates";
  }
  if (els.carView) {
    els.carView.hidden = name !== "car";
  }
  els.viewerView.hidden = name !== "viewer";
  if (name === "library") {
    document.title = "Tesla video viewer";
  }
  window.scrollTo(0, 0);
}

function showLibrary() {
  showPage("library");
}

function showViewer() {
  showPage("viewer");
}

function catalogCropUrl(plate) {
  if (!plate || !plate.bestCropId) {
    return "";
  }
  if (state.platesRaw && plate.bestEventId) {
    return `/api/events/${plate.bestEventId}/plates/crops/${plate.bestCropId}/still`;
  }
  return `/api/plates/crops/${plate.bestCropId}`;
}

function catalogStateLabel(plate) {
  const info = plate && plate.jurisdiction;
  if (!info || !info.code) {
    return "Unclassified";
  }
  if (info.confidence >= 0.5) {
    return info.confidence >= 0.7 ? info.code : `${info.code}?`;
  }
  return info.code;
}

function applyCatalogZoomSize() {
  const img = els.platesDetailImg;
  if (!img || !img.naturalWidth) {
    return;
  }
  const scale = state.catalogZoom || 1;
  img.style.width = `${img.naturalWidth * scale}px`;
  img.style.height = `${img.naturalHeight * scale}px`;
  for (const btn of document.querySelectorAll("#plates-detail-scale button")) {
    btn.setAttribute("aria-pressed", String(Number(btn.dataset.zoom) === scale));
  }
}

function selectedCatalogPlate() {
  const plates = state.platesCatalog && state.platesCatalog.plates ? state.platesCatalog.plates : [];
  return plates.find((item) => item.text === state.selectedCatalogText) || null;
}

function renderPlatesDetail() {
  if (!els.platesDetail) {
    return;
  }
  const plate = selectedCatalogPlate();
  if (!plate) {
    els.platesDetail.hidden = true;
    return;
  }
  els.platesDetail.hidden = false;
  els.platesDetailText.textContent = plate.text;
  const info = plate.jurisdiction;
  if (info && info.code) {
    const alts = (info.alternatives || []).map((item) => item.code);
    const conf = Math.round((info.confidence || 0) * 100);
    let line = `${info.name} · ${info.seriesLabel} · ${conf}%`;
    if (alts.length) {
      line += ` · also ${alts.join(", ")}`;
    }
    els.platesDetailState.textContent = line;
  } else {
    els.platesDetailState.textContent = "Unclassified — no matching US serial format";
  }
  const hits = `${plate.appearanceCount} hit${plate.appearanceCount === 1 ? "" : "s"}`;
  const events = `${plate.eventCount} clip${plate.eventCount === 1 ? "" : "s"}`;
  const seen = plate.seenSec ? formatDuration(plate.seenSec) : "";
  const place = [plate.city, plate.street].filter(Boolean).join(" · ");
  const when = plate.firstSeen ? String(plate.firstSeen).replace("T", " ").slice(0, 16) : "";
  els.platesDetailInfo.textContent = [hits, events, seen, when, place].filter(Boolean).join(" · ");
  if (els.openPlateEvent) {
    els.openPlateEvent.hidden = !plate.bestEventId;
  }
  const src = catalogCropUrl(plate);
  els.platesDetailImg.alt = plate.text;
  els.platesDetailImg.onload = () => applyCatalogZoomSize();
  els.platesDetailImg.onerror = () => {
    if (src.includes("/still") && plate.bestCropId) {
      els.platesDetailImg.src = `/api/plates/crops/${plate.bestCropId}`;
    }
  };
  els.platesDetailImg.src = src;
  applyCatalogZoomSize();
}

function renderPlatesCatalog() {
  if (!els.platesCatalog) {
    return;
  }
  const catalog = state.platesCatalog || { plates: [], total: 0, classified: 0, unclassified: 0 };
  const plates = catalog.plates || [];
  if (els.platesMeta) {
    els.platesMeta.textContent = `${catalog.total} stored · ${catalog.classified} classified · ${catalog.unclassified} unclassified`;
  }
  if (els.platesView) {
    els.platesView.classList.toggle("raw-pixels", Boolean(state.platesRaw));
  }
  if (els.platesRawToggle) {
    els.platesRawToggle.checked = Boolean(state.platesRaw);
  }
  const filtered = plates.filter((plate) => {
    if (state.platesFilter === "classified") {
      return Boolean(plate.jurisdiction);
    }
    if (state.platesFilter === "unclassified") {
      return !plate.jurisdiction;
    }
    return true;
  });
  if (state.selectedCatalogText && !filtered.some((item) => item.text === state.selectedCatalogText)) {
    state.selectedCatalogText = filtered.length ? filtered[0].text : null;
  }
  for (const btn of document.querySelectorAll("#plates-filters button")) {
    btn.setAttribute("aria-pressed", String(btn.dataset.filter === state.platesFilter));
  }
  if (els.platesEmpty) {
    if (!plates.length) {
      els.platesEmpty.hidden = false;
      els.platesEmpty.textContent = "No plates stored yet. Open a clip and scan plates.";
    } else if (!filtered.length) {
      els.platesEmpty.hidden = false;
      els.platesEmpty.textContent = state.platesFilter === "unclassified"
        ? "Every stored plate matched a state format."
        : "No classified plates yet.";
    } else {
      els.platesEmpty.hidden = true;
    }
  }
  els.platesCatalog.replaceChildren();
  for (const plate of filtered) {
    const item = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "plate-row";
    if (plate.text === state.selectedCatalogText) {
      row.classList.add("plate-open");
    }
    const img = document.createElement("img");
    img.className = "plates-thumb";
    img.alt = plate.text;
    if (plate.bestCropId) {
      img.src = `/api/plates/crops/${plate.bestCropId}`;
    }
    const text = document.createElement("span");
    text.className = "plates-text";
    text.textContent = plate.text;
    const st = document.createElement("span");
    st.className = plate.jurisdiction ? "plates-state" : "plates-state unknown";
    st.textContent = catalogStateLabel(plate);
    const series = document.createElement("span");
    series.className = "plates-series";
    series.textContent = plate.jurisdiction ? plate.jurisdiction.seriesLabel : "No matching series";
    const hits = document.createElement("span");
    hits.className = "plates-hits";
    hits.textContent = `${plate.appearanceCount}×`;
    const seen = document.createElement("span");
    seen.className = "plates-seen";
    seen.textContent = plate.seenSec ? formatDuration(plate.seenSec) : "";
    const place = document.createElement("span");
    place.className = "plates-place";
    place.textContent = [plate.city, plate.street].filter(Boolean).join(" · ");
    row.append(img, text, st, series, hits, seen, place);
    row.addEventListener("click", () => {
      state.carReturnPlates = true;
      state.carReturnEventId = null;
      state.carReturnDay = null;
      openCarPage(plate.text);
    });
    item.append(row);
    els.platesCatalog.append(item);
  }
  renderPlatesDetail();
}

async function openPlates() {
  showPage("plates");
  setHash("plates");
  try {
    state.platesCatalog = await api("/api/plates");
    showBanner("");
  } catch (err) {
    state.platesCatalog = { plates: [], total: 0, classified: 0, unclassified: 0 };
    showBanner(err.message);
  }
  renderPlatesCatalog();
}

async function openEvent(eventId) {
  try {
    state.event = await api(`/api/events/${eventId}`);
    showBanner("");
  } catch (err) {
    showBanner(err.message);
    return;
  }
  state.day = state.event.date;
  state.month = state.event.date.slice(0, 7);
  showViewer();
  setHash(`e/${eventId}`);
  buildViewer();
  loadPlateStatus();
}

async function dumpScreens(cameras) {
  if (!state.event) {
    return;
  }
  if (Array.isArray(cameras) && cameras.length === 0) {
    showBanner("No camera is loaded.");
    return;
  }
  els.dumpStatus.textContent = "Writing PNGs…";
  try {
    const body = { elapsed_sec: state.elapsed };
    if (Array.isArray(cameras)) {
      body.cameras = cameras;
    }
    const result = await api(`/api/events/${state.event.id}/screenshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    state.lastDumpFolder = result.folder;
    const count = result.written.length;
    const failed = result.failures.length;
    els.dumpStatus.textContent = failed
      ? `Wrote ${count} PNG(s). ${failed} camera(s) had no frame.`
      : `Wrote ${count} PNG(s) to ${result.folder}`;
    els.openDump.hidden = false;
    showBanner("");
  } catch (err) {
    els.dumpStatus.textContent = "";
    showBanner(err.message);
  }
}

function plateTimeLabel(elapsed) {
  return formatScrub(elapsed);
}

function jurisdictionShort(plate) {
  const info = plate && plate.jurisdiction;
  if (!info || !info.code) {
    return "";
  }
  return info.confidence >= 0.5 ? info.code : `${info.code}?`;
}

function jurisdictionLine(plate) {
  const info = plate && plate.jurisdiction;
  if (!info || !info.code) {
    return "";
  }
  if (info.confidence >= 0.7) {
    return `${info.name} · ${info.seriesLabel}`;
  }
  if (info.confidence >= 0.5) {
    return `${info.name}? · ${info.seriesLabel}`;
  }
  const codes = [info.code, ...(info.alternatives || []).map((item) => item.code)].slice(0, 3);
  return codes.join(" / ");
}

function plateHue(text) {
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 360;
  }
  return hash;
}

function hidePlateZoom() {
  if (els.plateZoom) {
    els.plateZoom.hidden = true;
  }
}

function applyPlateZoomSize() {
  const img = els.plateZoomImg;
  if (!img || !img.naturalWidth) {
    return;
  }
  const scale = state.plateZoomScale || 1;
  img.style.width = `${img.naturalWidth * scale}px`;
  img.style.height = `${img.naturalHeight * scale}px`;
  if (els.plateZoomSize) {
    const mode = scale === 1 ? "1:1" : `${scale}× nearest`;
    els.plateZoomSize.textContent = `${img.naturalWidth} × ${img.naturalHeight} px · ${mode}`;
  }
  for (const btn of document.querySelectorAll("#plate-zoom .plate-zoom-scale button")) {
    btn.setAttribute("aria-pressed", String(Number(btn.dataset.zoom) === scale));
  }
}

function loadPlateShot(img, url, fallback) {
  if (!img) {
    return;
  }
  img.onerror = () => {
    if (fallback && img.getAttribute("src") === url) {
      img.src = fallback;
    }
  };
  if (img.getAttribute("src") !== url) {
    img.src = url;
  }
}

function showPlateZoom(plate, hit) {
  if (!els.plateZoom || !els.plateZoomImg || !state.event || !hit || !hit.cropId) {
    hidePlateZoom();
    return;
  }
  els.plateZoom.hidden = false;
  if (els.plateZoomLabel) {
    els.plateZoomLabel.textContent = `${plate.text} · ${hit.cameraLabel} · ${plateTimeLabel(hit.elapsedSec)}`;
  }
  const img = els.plateZoomImg;
  const jpeg = `/api/events/${state.event.id}/plates/crops/${hit.cropId}`;
  const still = `${jpeg}/still`;
  const token = String(hit.cropId);
  img.alt = `${plate.text} plate`;
  img.dataset.token = token;
  img.onload = () => {
    if (img.dataset.token !== token) {
      return;
    }
    applyPlateZoomSize();
  };
  img.onerror = () => {
    if (img.dataset.token !== token) {
      return;
    }
    if (img.getAttribute("src") === still) {
      img.src = jpeg;
    }
  };
  if (img.getAttribute("src") !== still) {
    img.src = still;
  } else if (img.complete && img.naturalWidth) {
    applyPlateZoomSize();
  }
  if (els.plateZoomVehicle) {
    els.plateZoomVehicle.alt = `${plate.text} car`;
    loadPlateShot(els.plateZoomVehicle, `${jpeg}/vehicle`);
  }
  if (els.plateZoomFrame) {
    els.plateZoomFrame.alt = `${plate.text} full frame`;
    loadPlateShot(els.plateZoomFrame, `${jpeg}/frame`);
  }
}

function openPlateShot(kind) {
  if (!els.plateShotDialog || !els.plateShotImg || !state.event) {
    return;
  }
  const plates = state.plateStatus && state.plateStatus.plates ? state.plateStatus.plates : [];
  const plate = plates.find((item) => item.text === state.selectedPlate);
  if (!plate || !plate.hits || !plate.hits.length) {
    return;
  }
  const hit = plate.hits[Math.min(state.plateHitIndex, plate.hits.length - 1)];
  const jpeg = `/api/events/${state.event.id}/plates/crops/${hit.cropId}`;
  const src = kind === "vehicle" ? `${jpeg}/vehicle` : `${jpeg}/frame`;
  els.plateShotCaption.textContent = `${plate.text} · ${kind === "vehicle" ? "car" : "full frame"} · ${plateTimeLabel(hit.elapsedSec)}`;
  els.plateShotImg.alt = els.plateShotCaption.textContent;
  els.plateShotImg.src = src;
  if (typeof els.plateShotDialog.showModal === "function") {
    els.plateShotDialog.showModal();
  }
}

function goToPlateHit(plate, index) {
  if (!plate || !plate.hits || !plate.hits.length) {
    return;
  }
  const bounded = Math.min(Math.max(index, 0), plate.hits.length - 1);
  state.selectedPlate = plate.text;
  state.plateHitIndex = bounded;
  const hit = plate.hits[bounded];
  setFocus(hit.camera);
  seekTo(hit.elapsedSec);
  renderPlates(state.plateStatus);
  showPlateZoom(plate, hit);
}

function renderPlateMarks() {
  if (!els.plateMarks || !state.event) {
    return;
  }
  els.plateMarks.replaceChildren();
  const duration = state.event.durationSec || 0;
  if (!duration) {
    return;
  }
  const plates = state.plateStatus && state.plateStatus.plates ? state.plateStatus.plates : [];
  for (const plate of plates) {
    const hits = plate.hits || [];
    hits.forEach((hit, index) => {
      const mark = document.createElement("button");
      mark.type = "button";
      mark.className = "plate-mark";
      if (plate.text === state.selectedPlate) {
        mark.classList.add("active");
      }
      const hue = plateHue(plate.text);
      mark.style.background = plate.text === state.selectedPlate ? "var(--amber)" : `hsl(${hue} 55% 52%)`;
      mark.style.left = `${(Number(hit.elapsedSec) / duration) * 100}%`;
      const stateCode = jurisdictionShort(plate);
      mark.title = `${plate.text}${stateCode ? ` ${stateCode}` : ""} · ${plateTimeLabel(hit.elapsedSec)} · ${hit.cameraLabel}`;
      mark.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        goToPlateHit(plate, index);
      });
      els.plateMarks.append(mark);
    });
  }
}

function renderPlates(status) {
  if (!els.plateStatus) {
    return;
  }
  state.plateStatus = status || { state: "idle", plates: [] };
  const running = status.state === "loading" || status.state === "running" || status.state === "queued";
  els.findPlates.disabled = running;
  els.findPlates.textContent = status.complete ? "Scan plates again" : "Find plates";
  let line = status.message || "Opening a clip queues a front-camera plate scan if it is not stored yet.";
  if (status.state === "queued") {
    line = status.message || "Queued.";
  }
  if ((status.state === "loading" || status.state === "running") && status.framesTotal) {
    line = `${status.message} ${status.framesDone}/${status.framesTotal} frames`;
    if (status.etaSec != null) {
      line += ` · ~${Math.max(1, Math.round(status.etaSec))}s left`;
    }
  }
  if (status.state === "error" && status.error) {
    line = status.error;
  }
  els.plateStatus.textContent = line;
  els.plateList.replaceChildren();
  const plates = status.plates || [];
  if (state.selectedPlate && !plates.some((item) => item.text === state.selectedPlate)) {
    state.selectedPlate = null;
    state.plateHitIndex = 0;
  }
  for (const plate of plates) {
    const item = document.createElement("li");
    const card = document.createElement("div");
    card.className = "plate-card";
    if (plate.text === state.selectedPlate) {
      card.classList.add("plate-open");
    }
    const img = document.createElement("img");
    img.alt = plate.text;
    img.src = `/api/events/${state.event.id}/plates/crops/${plate.cropId}`;
    const body = document.createElement("div");
    const text = document.createElement("p");
    text.className = "plate-text";
    text.textContent = plate.text;
    text.title = "Open this car’s page";
    text.addEventListener("click", (event) => {
      event.stopPropagation();
      openCarPage(plate.text);
    });
    const stateCode = jurisdictionShort(plate);
    if (stateCode) {
      const badge = document.createElement("span");
      badge.className = "plate-state";
      badge.textContent = stateCode;
      text.append(" ", badge);
    }
    const meta = document.createElement("p");
    meta.className = "plate-meta";
    const conf = Math.round((plate.bestConfidence || 0) * 100);
    const where = `${plate.cameraLabel} · ${plateTimeLabel(plate.firstElapsedSec)} · ${plate.count} hit${plate.count === 1 ? "" : "s"} · ${conf}%`;
    const guessed = jurisdictionLine(plate);
    meta.textContent = guessed ? `${guessed} · ${where}` : where;
    body.append(text, meta);
    const tools = document.createElement("div");
    tools.className = "plate-step";
    const carBtn = document.createElement("button");
    carBtn.type = "button";
    carBtn.textContent = "This car";
    carBtn.addEventListener("click", (event) => {
      event.stopPropagation();
      openCarPage(plate.text);
    });
    tools.append(carBtn);
    if (plate.text === state.selectedPlate && plate.hits && plate.hits.length) {
      const prev = document.createElement("button");
      prev.type = "button";
      prev.textContent = "Prev";
      prev.disabled = state.plateHitIndex <= 0;
      prev.addEventListener("click", (event) => {
        event.stopPropagation();
        goToPlateHit(plate, state.plateHitIndex - 1);
      });
      const next = document.createElement("button");
      next.type = "button";
      next.textContent = "Next";
      next.disabled = state.plateHitIndex >= plate.hits.length - 1;
      next.addEventListener("click", (event) => {
        event.stopPropagation();
        goToPlateHit(plate, state.plateHitIndex + 1);
      });
      const whereHit = document.createElement("span");
      const hit = plate.hits[Math.min(state.plateHitIndex, plate.hits.length - 1)];
      whereHit.textContent = `${state.plateHitIndex + 1} / ${plate.hits.length} · ${plateTimeLabel(hit.elapsedSec)} · ${hit.cameraLabel}`;
      tools.append(prev, next, whereHit);
    }
    body.append(tools);
    card.append(img, body);
    card.addEventListener("click", (event) => {
      if (event.target.closest(".plate-step")) {
        return;
      }
      goToPlateHit(plate, plate.text === state.selectedPlate ? state.plateHitIndex : 0);
    });
    item.append(card);
    els.plateList.append(item);
  }
  renderPlateMarks();
  updatePlateOverlays();
  if (state.selectedPlate) {
    const open = plates.find((item) => item.text === state.selectedPlate);
    const hit = open && open.hits ? open.hits[Math.min(state.plateHitIndex, open.hits.length - 1)] : null;
    if (open && hit) {
      showPlateZoom(open, hit);
    } else {
      hidePlateZoom();
    }
  } else {
    hidePlateZoom();
  }
}

async function pollPlates(watchId) {
  if (watchId !== plateWatchId || !state.event) {
    return;
  }
  try {
    const status = await api(`/api/events/${state.event.id}/plates`);
    if (watchId !== plateWatchId || !state.event) {
      return;
    }
    renderPlates(status);
    if (status.state === "loading" || status.state === "running" || status.state === "queued") {
      setTimeout(() => pollPlates(watchId), 1000);
    }
  } catch (err) {
    if (watchId !== plateWatchId) {
      return;
    }
    showBanner(err.message);
  }
}

function watchPlates() {
  plateWatchId += 1;
  pollPlates(plateWatchId);
}

async function loadPlateStatus() {
  if (!state.event) {
    return;
  }
  try {
    const status = await api(`/api/events/${state.event.id}/plates`);
    renderPlates(status);
    if (status.state === "idle") {
      await startPlateScan(false);
      return;
    }
    if (status.state === "loading" || status.state === "running" || status.state === "queued") {
      watchPlates();
    }
  } catch (err) {
    renderPlates({ state: "idle", plates: [], message: "" });
    showBanner(err.message);
  }
}

async function startPlateScan(force) {
  if (!state.event) {
    return;
  }
  els.findPlates.disabled = true;
  try {
    const status = await api(`/api/events/${state.event.id}/plates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ force: Boolean(force) }),
    });
    renderPlates(status);
    if (status.state === "loading" || status.state === "running" || status.state === "queued") {
      watchPlates();
    }
  } catch (err) {
    els.findPlates.disabled = false;
    showBanner(err.message);
  }
}

async function loadConfigAndLibrary() {
  state.config = await api("/api/config");
  if (state.config.scan) {
    renderScanStatus(state.config.scan);
  }
  if (!state.config.hasLibrary) {
    state.library = null;
    renderLibrary();
    if (state.config.scan && state.config.scan.state === "running") {
      watchScan();
    }
    return;
  }
  state.library = await api("/api/library");
  const hash = parseHash();
  if (!state.month) {
    state.month = hash.month || state.library.months[state.library.months.length - 1] || null;
  }
  renderLibrary();
  if (state.config.scan && state.config.scan.state === "running") {
    watchScan();
  }
}

async function applyHash() {
  const hash = parseHash();
  if (hash.plate) {
    if (state.carPlate === hash.plate && els.carView && !els.carView.hidden) {
      return;
    }
    await loadCarPage(hash.plate);
    return;
  }
  if (hash.eventId) {
    if (state.event && state.event.id === hash.eventId && !els.viewerView.hidden) {
      return;
    }
    if (state.config && state.config.hasLibrary) {
      await openEvent(hash.eventId);
    }
    return;
  }
  if (hash.plates) {
    if (els.platesView && !els.platesView.hidden && state.platesCatalog) {
      return;
    }
    await openPlates();
    return;
  }
  if (hash.day) {
    if (state.day === hash.day && state.dayDetail && state.dayDetail.date === hash.day && els.dayView && !els.dayView.hidden) {
      return;
    }
    await openDay(hash.day);
    return;
  }
  showLibrary();
  if (hash.month) {
    state.month = hash.month;
  }
  renderLibrary();
}

function renderDraftSources() {
  els.sourceList.replaceChildren();
  for (const path of draftSources) {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = path;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Remove";
    remove.addEventListener("click", () => {
      draftSources = draftSources.filter((entry) => entry !== path);
      renderDraftSources();
    });
    item.append(text, remove);
    els.sourceList.append(item);
  }
}

function addDraftSource() {
  const path = els.sourceAdd.value.trim();
  if (!path) {
    return;
  }
  const exists = draftSources.some((entry) => entry.toLowerCase() === path.toLowerCase());
  if (exists) {
    showBanner(`Already listed: ${path}`);
    return;
  }
  draftSources.push(path);
  els.sourceAdd.value = "";
  renderDraftSources();
}

document.getElementById("btn-rescan").addEventListener("click", async () => {
  if (putInFlight) {
    return;
  }
  try {
    state.config = await api("/api/rescan", { method: "POST" });
    renderScanStatus(state.config.scan);
    watchScan();
  } catch (err) {
    showBanner(err.message);
  }
});

document.getElementById("btn-folders").addEventListener("click", () => {
  draftSources = sourceListFromConfig();
  els.outputDir.value = state.config ? state.config.outputDir : "";
  els.sourceAdd.value = "";
  renderDraftSources();
  els.folders.showModal();
});

document.getElementById("btn-add-source").addEventListener("click", addDraftSource);
els.sourceAdd.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    addDraftSource();
  }
});

document.getElementById("folders-form").addEventListener("submit", async (event) => {
  const submitter = event.submitter;
  if (!submitter || submitter.value !== "save") {
    return;
  }
  event.preventDefault();
  if (putInFlight) {
    return;
  }
  putInFlight = true;
  const saveButton = document.getElementById("btn-save-folders");
  saveButton.disabled = true;
  saveButton.textContent = "Saving…";
  try {
    state.config = await api("/api/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sources: draftSources,
        output_dir: els.outputDir.value,
      }),
    });
    els.folders.close();
    renderScanStatus(state.config.scan);
    watchScan();
  } catch (err) {
    showBanner(err.message);
  } finally {
    putInFlight = false;
    saveButton.disabled = false;
    saveButton.textContent = "Save and scan";
  }
});

document.getElementById("btn-back-calendar").addEventListener("click", () => {
  showLibrary();
  setHash(state.month || "");
  renderLibrary();
});

const platesButton = document.getElementById("btn-plates");
if (platesButton) {
  platesButton.addEventListener("click", () => {
    openPlates();
  });
}
const backPlates = document.getElementById("btn-back-plates");
if (backPlates) {
  backPlates.addEventListener("click", () => {
    showLibrary();
    setHash(state.month || "");
    renderLibrary();
  });
}
if (els.platesRawToggle) {
  els.platesRawToggle.addEventListener("change", () => {
    state.platesRaw = els.platesRawToggle.checked;
    renderPlatesCatalog();
  });
}
for (const btn of document.querySelectorAll("#plates-filters button")) {
  btn.addEventListener("click", () => {
    state.platesFilter = btn.dataset.filter || "all";
    renderPlatesCatalog();
  });
}
for (const btn of document.querySelectorAll("#plates-detail-scale button")) {
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    state.catalogZoom = Number(btn.dataset.zoom) || 1;
    applyCatalogZoomSize();
  });
}
if (els.openPlateEvent) {
  els.openPlateEvent.addEventListener("click", () => {
    const plate = selectedCatalogPlate();
    if (plate && plate.bestEventId) {
      openEvent(plate.bestEventId);
    }
  });
}

if (els.btnBackCar) {
  els.btnBackCar.addEventListener("click", () => leaveCarPage());
}

document.getElementById("btn-back").addEventListener("click", () => {
  if (state.viewerReturnPlate) {
    const plate = state.viewerReturnPlate;
    state.viewerReturnPlate = null;
    state.carReturnEventId = state.event ? state.event.id : null;
    state.carReturnDay = state.event ? state.event.date : state.day;
    setHash(`p/${encodeURIComponent(plate)}`);
    return;
  }
  const day = state.event ? state.event.date : state.day;
  if (day) {
    openDay(day);
    return;
  }
  showLibrary();
  setHash(state.month || "");
  renderLibrary();
});

els.play.addEventListener("click", () => {
  if (state.playing) {
    pauseAll();
    return;
  }
  playAll();
});

document.getElementById("btn-back-10").addEventListener("click", () => seekTo(state.elapsed - 10));
document.getElementById("btn-fwd-10").addEventListener("click", () => seekTo(state.elapsed + 10));

els.scrubber.addEventListener("input", () => {
  seekTo(Number(els.scrubber.value));
});

els.showAll.addEventListener("click", () => setFocus(null));

document.getElementById("btn-shot-one").addEventListener("click", () => {
  const camera = state.focused || masterCamera();
  if (!camera) {
    showBanner("Select a camera, or wait until a clip is loaded.");
    return;
  }
  dumpScreens([camera]);
});

document.getElementById("btn-shot-all").addEventListener("click", () => dumpScreens(null));

els.findPlates.addEventListener("click", () => {
  startPlateScan(Boolean(state.plateStatus && state.plateStatus.complete));
});

for (const btn of document.querySelectorAll("#plate-zoom .plate-zoom-scale button")) {
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    state.plateZoomScale = Number(btn.dataset.zoom) || 1;
    applyPlateZoomSize();
  });
}

for (const btn of document.querySelectorAll(".plate-zoom-open")) {
  btn.addEventListener("click", (event) => {
    event.stopPropagation();
    openPlateShot(btn.dataset.shot);
  });
}

els.openDump.addEventListener("click", async () => {
  if (!state.lastDumpFolder) {
    return;
  }
  try {
    await api("/api/open-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: state.lastDumpFolder }),
    });
  } catch (err) {
    showBanner(err.message);
  }
});

document.addEventListener("keydown", (event) => {
  if (event.target && ["INPUT", "TEXTAREA"].includes(event.target.tagName)) {
    return;
  }
  if (els.viewerView.hidden) {
    if (event.key === "Escape" && els.carView && !els.carView.hidden) {
      leaveCarPage();
      return;
    }
    if (event.key === "Escape" && els.platesView && !els.platesView.hidden) {
      document.getElementById("btn-back-plates").click();
      return;
    }
    if (event.key === "Escape" && els.dayView && !els.dayView.hidden) {
      document.getElementById("btn-back-calendar").click();
    }
    return;
  }
  if (event.key === " ") {
    event.preventDefault();
    if (state.playing) {
      pauseAll();
    } else {
      playAll();
    }
  } else if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    const step = event.ctrlKey || event.metaKey ? 60 : 10;
    const delta = event.key === "ArrowLeft" ? -step : step;
    seekTo(state.elapsed + delta);
  } else if (event.key === "Escape") {
    if (state.focused) {
      setFocus(null);
    } else {
      document.getElementById("btn-back").click();
    }
  } else if (event.key === "s") {
    dumpScreens([state.focused || masterCamera()].filter(Boolean));
  } else if (event.key === "S") {
    dumpScreens(null);
  }
});

window.addEventListener("hashchange", () => {
  applyHash();
});

loadConfigAndLibrary()
  .then(() => applyHash())
  .catch((err) => showBanner(err.message));
