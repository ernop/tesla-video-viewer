(function (root) {
  const MASTER_ORDER = ["front", "back", "left_repeater", "right_repeater"];

  function segmentAt(segments, elapsed) {
    if (!segments || !segments.length) {
      return null;
    }
    for (let index = 0; index < segments.length; index += 1) {
      const segment = segments[index];
      const next = segments[index + 1];
      const local = elapsed - segment.offsetSec;
      if (local < -0.05) {
        continue;
      }
      if (next && elapsed >= next.offsetSec) {
        continue;
      }
      if (local <= segment.durationSec + 0.08) {
        return { segment, local: Math.max(0, local) };
      }
    }
    return null;
  }

  function followingSegment(segments, index) {
    if (!segments || index == null || index + 1 >= segments.length) {
      return null;
    }
    return segments[index + 1];
  }

  function masterCamera(cameraIds, loaded) {
    for (const id of MASTER_ORDER) {
      if (cameraIds.indexOf(id) !== -1 && loaded.get(id) != null) {
        return id;
      }
    }
    for (const id of cameraIds) {
      if (loaded.get(id) != null) {
        return id;
      }
    }
    return null;
  }

  function createPlayer(options) {
    const durationSec = options.durationSec;
    const cameras = options.cameras;
    const host = options.host || {};
    const byId = new Map(cameras.map((camera) => [camera.id, camera]));
    const cameraIds = cameras.map((camera) => camera.id);
    const seeking = new Set();
    const loaded = new Map();
    let elapsed = 0;
    let playing = false;

    function emitPause() {
      playing = false;
      if (host.pause) {
        host.pause();
      }
    }

    function loadCamera(camera, time) {
      const track = byId.get(camera);
      const hit = track ? segmentAt(track.segments, time) : null;
      if (!hit) {
        seeking.delete(camera);
        if (loaded.get(camera) == null) {
          if (host.clear) {
            host.clear(camera);
          }
          return;
        }
        loaded.set(camera, null);
        if (host.clear) {
          host.clear(camera);
        }
        return;
      }
      if (loaded.get(camera) === hit.segment.index) {
        if (host.sync) {
          host.sync(camera, hit.local);
        }
        return;
      }
      loaded.set(camera, hit.segment.index);
      seeking.add(camera);
      if (host.load) {
        host.load(camera, hit);
      }
    }

    function seekTo(time) {
      elapsed = Math.min(Math.max(time, 0), durationSec);
      for (const id of cameraIds) {
        loadCamera(id, elapsed);
      }
    }

    function timeUpdate(camera, currentTime) {
      if (!playing || seeking.has(camera)) {
        return;
      }
      if (masterCamera(cameraIds, loaded) !== camera) {
        return;
      }
      const index = loaded.get(camera);
      const track = byId.get(camera);
      const segment = track && index != null ? track.segments[index] : null;
      if (!segment) {
        return;
      }
      elapsed = segment.offsetSec + currentTime;
      const hit = segmentAt(track.segments, elapsed);
      if (hit && hit.segment.index !== index) {
        seekTo(elapsed);
        return;
      }
      if (!hit) {
        const following = followingSegment(track.segments, index);
        if (following) {
          seekTo(Math.max(elapsed, following.offsetSec));
          return;
        }
        emitPause();
        return;
      }
      for (const id of cameraIds) {
        if (id !== camera) {
          loadCamera(id, elapsed);
        }
      }
      if (elapsed >= durationSec - 0.05) {
        emitPause();
      }
    }

    function ended(camera) {
      if (seeking.has(camera) || !playing) {
        return;
      }
      const index = loaded.get(camera);
      if (masterCamera(cameraIds, loaded) !== camera) {
        loadCamera(camera, elapsed);
        return;
      }
      const track = byId.get(camera);
      const following = track ? followingSegment(track.segments, index) : null;
      if (!following) {
        emitPause();
        return;
      }
      seekTo(Math.max(elapsed, following.offsetSec));
    }

    return {
      play() {
        playing = true;
      },
      pause() {
        playing = false;
      },
      seekTo,
      timeUpdate,
      ended,
      ready(camera) {
        seeking.delete(camera);
      },
      elapsed() {
        return elapsed;
      },
      isPlaying() {
        return playing;
      },
      isSeeking(camera) {
        return seeking.has(camera);
      },
      loadedIndex(camera) {
        return loaded.get(camera);
      },
      masterCamera() {
        return masterCamera(cameraIds, loaded);
      },
    };
  }

  const api = { segmentAt, followingSegment, masterCamera, createPlayer };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.TeslaPlayback = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
