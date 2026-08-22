"use strict";

const fs = require("fs");
const path = require("path");
const playback = require("../web/playback.js");

let failed = 0;

function assert(condition, message) {
  if (condition) {
    return;
  }
  failed += 1;
  console.error(`FAIL  ${message}`);
}

function simulate(event, options) {
  const dt = (options && options.dt) || 0.05;
  const ignoreEnded = Boolean(options && options.ignoreEnded);
  const videos = new Map();
  const pending = [];
  const visited = new Map();
  const host = {
    load(camera, hit) {
      pending.push({ camera, hit });
    },
    sync(camera, local) {
      const video = videos.get(camera);
      if (video && video.index != null && Math.abs(video.currentTime - local) > 0.25) {
        video.currentTime = local;
      }
    },
    clear(camera) {
      videos.set(camera, { currentTime: 0, duration: 0, index: null });
    },
    pause() {},
  };
  const player = playback.createPlayer({
    durationSec: event.durationSec,
    cameras: event.cameras,
    host,
  });
  for (const camera of event.cameras) {
    videos.set(camera.id, { currentTime: 0, duration: 0, index: null });
    visited.set(camera.id, new Set());
  }

  function flushLoads() {
    const batch = pending.splice(0);
    for (const item of batch) {
      videos.set(item.camera, {
        currentTime: item.hit.local,
        duration: item.hit.segment.durationSec,
        index: item.hit.segment.index,
      });
      visited.get(item.camera).add(item.hit.segment.index);
      player.ready(item.camera);
    }
  }

  player.play();
  player.seekTo(0);
  flushLoads();

  let stuck = 0;
  let lastElapsed = player.elapsed();
  const freezeAt = [];
  const maxTicks = Math.ceil(event.durationSec / dt) + 200;
  for (let tick = 0; tick < maxTicks && player.isPlaying(); tick += 1) {
    const ended = [];
    for (const camera of event.cameras) {
      if (player.isSeeking(camera.id)) {
        continue;
      }
      const video = videos.get(camera.id);
      if (video.index == null) {
        continue;
      }
      video.currentTime = Math.min(video.currentTime + dt, video.duration);
      if (video.currentTime >= video.duration - 1e-9) {
        ended.push(camera.id);
      }
    }
    for (const camera of event.cameras) {
      if (player.isSeeking(camera.id)) {
        continue;
      }
      const video = videos.get(camera.id);
      if (video.index == null) {
        continue;
      }
      player.timeUpdate(camera.id, video.currentTime);
    }
    for (const cameraId of ended) {
      if (!ignoreEnded) {
        player.ended(cameraId);
      }
    }
    flushLoads();
    const elapsed = player.elapsed();
    if (Math.abs(elapsed - lastElapsed) < 1e-9) {
      stuck += 1;
    } else {
      stuck = 0;
    }
    lastElapsed = elapsed;
    if (stuck >= 8 && player.isPlaying()) {
      freezeAt.push(elapsed);
      break;
    }
  }

  const frontVisited = [...(visited.get("front") || [])].sort((a, b) => a - b);
  return {
    elapsed: player.elapsed(),
    playing: player.isPlaying(),
    freezeAt: freezeAt[0],
    frontVisited,
    frontIndex: player.loadedIndex("front"),
  };
}

const recent = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures", "event_2026-08-21_17-26-55.json"), "utf8")
);

const recentRun = simulate(recent);
assert(
  recentRun.freezeAt == null,
  `17:26:55 Recent event froze at ${recentRun.freezeAt}s (the 1:01 bug)`
);
assert(
  recentRun.elapsed >= recent.durationSec - 0.2,
  `17:26:55 should reach ~${recent.durationSec}s, got ${recentRun.elapsed}`
);
assert(!recentRun.playing, "player should pause at the real end, not mid-event");
assert(
  JSON.stringify(recentRun.frontVisited) === "[0,1,2,3,4,5,6]",
  `front should play all 7 files, visited ${recentRun.frontVisited}`
);

const overlap = {
  durationSec: 121,
  cameras: [
    {
      id: "front",
      segments: [
        { index: 0, offsetSec: 0, durationSec: 61 },
        { index: 1, offsetSec: 60, durationSec: 61 },
      ],
    },
    {
      id: "right_repeater",
      segments: [
        { index: 0, offsetSec: 0, durationSec: 60.4 },
        { index: 1, offsetSec: 60, durationSec: 61 },
      ],
    },
  ],
};
const overlapRun = simulate(overlap);
assert(
  overlapRun.freezeAt == null,
  `overlapping 61s files froze at ${overlapRun.freezeAt}s`
);
assert(
  overlapRun.elapsed >= 120,
  `overlapping files should play through 2:00, got ${overlapRun.elapsed}`
);
assert(
  JSON.stringify(overlapRun.frontVisited) === "[0,1]",
  `overlapping files should hand off to file 2, visited ${overlapRun.frontVisited}`
);

const firstFile = playback.segmentAt(recent.cameras[1].segments, 61.0);
assert(firstFile && firstFile.segment.index === 0, "61.0s still belongs to the first file");
const afterGap = playback.segmentAt(recent.cameras[1].segments, 66.0);
assert(afterGap && afterGap.segment.index === 1, "66.0s must be the second file, not a freeze");
const inHole = playback.segmentAt(recent.cameras[1].segments, 63.0);
assert(inHole == null, "the 61.5–66s hole has no footage");

const frozen = simulate(recent, { ignoreEnded: true });
assert(
  frozen.freezeAt != null && frozen.freezeAt < 66,
  `without ended-handoff the 1:01 freeze must be detected, got freezeAt=${frozen.freezeAt}`
);

if (failed) {
  process.exit(1);
}
console.log("playback stitch: 4 checks passed");
