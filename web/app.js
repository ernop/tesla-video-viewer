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
  seeking: false,
  lastDumpFolder: null,
  videos: new Map(),
  loadedSegment: new Map(),
};

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
  monthNav: document.getElementById("month-nav"),
  calendar: document.getElementById("calendar"),
  dayPanel: document.getElementById("day-panel"),
  dayTitle: document.getElementById("day-title"),
  dayMeta: document.getElementById("day-meta"),
  dayRail: document.getElementById("day-rail"),
  hourScale: document.getElementById("hour-scale"),
  dayEvents: document.getElementById("day-events"),
  viewerView: document.getElementById("viewer-view"),
  viewerTitle: document.getElementById("viewer-title"),
  viewerClock: document.getElementById("viewer-clock"),
  camGrid: document.getElementById("cam-grid"),
  play: document.getElementById("btn-play"),
  scrubber: document.getElementById("scrubber"),
  scrubReadout: document.getElementById("scrub-readout"),
  showAll: document.getElementById("btn-show-all"),
  dumpStatus: document.getElementById("dump-status"),
  openDump: document.getElementById("btn-open-dump"),
  sourceStatus: document.getElementById("source-status"),
  folders: document.getElementById("folders-dialog"),
  sourceList: document.getElementById("source-list"),
  sourceAdd: document.getElementById("source-add-input"),
  outputDir: document.getElementById("output-dir-input"),
  scanStatus: document.getElementById("scan-status"),
  scanPanel: document.getElementById("scan-panel"),
  scanLog: document.getElementById("scan-log"),
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
      state.day = null;
      state.month = ym;
      setHash(ym);
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
  setHash(date);
  renderLibrary();
}

function renderDayPanel() {
  if (!state.day || !state.dayDetail) {
    els.dayPanel.hidden = true;
    return;
  }
  els.dayPanel.hidden = false;
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
    rail.title = `${event.time} ${kindLabel(event.kind)} · ${event.sourceLabel}`;
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
    const cams = document.createElement("span");
    cams.textContent = event.cameras.map((cam) => cam.label).join(" · ");
    const dur = document.createElement("span");
    dur.textContent = formatDuration(event.durationSec);
    button.append(time, kind, source, cams, dur);
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
  renderDayPanel();
}

function pauseAll() {
  state.playing = false;
  els.play.textContent = "Play";
  for (const video of state.videos.values()) {
    video.pause();
  }
}

function playAll() {
  state.playing = true;
  els.play.textContent = "Pause";
  for (const [camera, video] of state.videos) {
    if (state.loadedSegment.get(camera) == null) {
      continue;
    }
    const playAttempt = video.play();
    if (playAttempt && playAttempt.catch) {
      playAttempt.catch(() => {});
    }
  }
}

function segmentAt(camera, elapsed) {
  const track = state.event.cameras.find((item) => item.id === camera);
  if (!track) {
    return null;
  }
  for (const segment of track.segments) {
    const local = elapsed - segment.offsetSec;
    if (local < -0.05) {
      continue;
    }
    if (local <= segment.durationSec + 0.08) {
      return { segment, local: Math.max(0, local) };
    }
  }
  return null;
}

function videoUrl(camera, index) {
  return `/api/events/${state.event.id}/cameras/${encodeURIComponent(camera)}/segments/${index}`;
}

function loadCamera(camera, elapsed, video) {
  const hit = segmentAt(camera, elapsed);
  const tile = video.closest(".cam-tile");
  const missing = tile.querySelector(".missing");
  if (!hit) {
    state.loadedSegment.set(camera, null);
    video.removeAttribute("src");
    video.load();
    missing.hidden = false;
    return;
  }
  missing.hidden = true;
  const already = state.loadedSegment.get(camera);
  if (already === hit.segment.index && video.src) {
    if (Math.abs(video.currentTime - hit.local) > 0.25 && !state.seeking) {
      video.currentTime = hit.local;
    }
    return;
  }
  state.loadedSegment.set(camera, hit.segment.index);
  state.seeking = true;
  video.src = videoUrl(camera, hit.segment.index);
  const onReady = () => {
    video.currentTime = hit.local;
    state.seeking = false;
    if (state.playing) {
      const playAttempt = video.play();
      if (playAttempt && playAttempt.catch) {
        playAttempt.catch(() => {});
      }
    }
  };
  video.addEventListener("loadedmetadata", onReady, { once: true });
}

function seekTo(elapsed) {
  if (!state.event) {
    return;
  }
  state.elapsed = Math.min(Math.max(elapsed, 0), state.event.durationSec);
  for (const [camera, video] of state.videos) {
    loadCamera(camera, state.elapsed, video);
  }
  updateViewerHud();
}

function masterCamera() {
  const preferred = ["front", "back", "left_repeater", "right_repeater"];
  for (const id of preferred) {
    if (state.videos.has(id) && state.loadedSegment.get(id) != null) {
      return id;
    }
  }
  for (const [id, loaded] of state.loadedSegment) {
    if (loaded != null) {
      return id;
    }
  }
  return null;
}

function onTimeUpdate(camera, video) {
  if (!state.playing || state.seeking) {
    return;
  }
  if (masterCamera() !== camera) {
    return;
  }
  const hit = segmentAt(camera, state.elapsed);
  const index = state.loadedSegment.get(camera);
  const track = state.event.cameras.find((item) => item.id === camera);
  const segment = track.segments[index];
  if (!segment) {
    return;
  }
  state.elapsed = segment.offsetSec + video.currentTime;
  if (hit && hit.segment.index !== index) {
    seekTo(state.elapsed);
    return;
  }
  for (const [other, otherVideo] of state.videos) {
    if (other === camera) {
      continue;
    }
    loadCamera(other, state.elapsed, otherVideo);
  }
  updateViewerHud();
  if (state.elapsed >= state.event.durationSec - 0.05) {
    pauseAll();
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
}

function setFocus(camera) {
  state.focused = camera;
  els.camGrid.classList.toggle("focus-mode", Boolean(camera));
  els.showAll.hidden = !camera;
  for (const tile of els.camGrid.querySelectorAll(".cam-tile")) {
    tile.classList.toggle("focused", tile.dataset.camera === camera);
  }
}

function buildViewer() {
  els.camGrid.replaceChildren();
  state.videos.clear();
  state.loadedSegment.clear();
  els.camGrid.dataset.layout = state.event.layout;
  els.camGrid.classList.remove("focus-mode");
  state.focused = null;
  els.showAll.hidden = true;
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
    const video = document.createElement("video");
    video.playsInline = true;
    video.preload = "auto";
    video.muted = true;
    video.addEventListener("timeupdate", () => onTimeUpdate(camera.id, video));
    video.addEventListener("ended", () => {
      const next = segmentAt(camera.id, state.elapsed + 0.05);
      if (next && next.segment.index !== state.loadedSegment.get(camera.id)) {
        loadCamera(camera.id, state.elapsed + 0.05, video);
        return;
      }
      if (masterCamera() === camera.id) {
        pauseAll();
      }
    });
    tile.addEventListener("click", () => {
      setFocus(state.focused === camera.id ? null : camera.id);
    });
    tile.append(video, label, missing);
    els.camGrid.append(tile);
    state.videos.set(camera.id, video);
  }
  els.viewerTitle.textContent = `${state.event.date} ${state.event.time} · ${kindLabel(state.event.kind)} · ${state.event.sourceLabel} · ${state.event.cameras.length} cameras`;
  seekTo(0);
}

function showLibrary() {
  pauseAll();
  els.viewerView.hidden = true;
  els.libraryView.hidden = false;
  state.event = null;
}

function showViewer() {
  els.libraryView.hidden = true;
  els.viewerView.hidden = false;
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
  if (hash.eventId) {
    if (state.event && state.event.id === hash.eventId && !els.viewerView.hidden) {
      return;
    }
    if (state.config && state.config.hasLibrary) {
      await openEvent(hash.eventId);
    }
    return;
  }
  showLibrary();
  if (hash.day) {
    if (state.day === hash.day && state.dayDetail && state.dayDetail.date === hash.day) {
      renderLibrary();
      return;
    }
    await openDay(hash.day);
    return;
  }
  if (hash.month) {
    state.month = hash.month;
    state.day = null;
    renderLibrary();
  }
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

document.getElementById("btn-back").addEventListener("click", () => {
  const day = state.event ? state.event.date : state.day;
  showLibrary();
  if (day) {
    openDay(day);
  } else {
    setHash(state.month || "");
    renderLibrary();
  }
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
