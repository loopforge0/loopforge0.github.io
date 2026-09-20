/* The comparison player for /upscaler-shootout/.
 *
 * One source, N methods, all playing the same frame at the same moment, with a shared
 * zoom and pan so every pane shows the same region of the picture. Everything the page
 * needs is in window.SHOOTOUT, written into the page by tools/build_shootout.py.
 *
 * The whole point of the page is judging fine detail in motion, so two things matter more
 * than anything else here: the panes must not drift apart, and zooming must reach true
 * native pixels rather than stopping at a blurry approximation of them.
 */
(function () {
  "use strict";

  var DATA = window.SHOOTOUT;
  if (!DATA) return;

  var FPS = 24;
  var FRAME = 1 / FPS;
  var SYNC_TOLERANCE = FRAME * 0.75; // a pane more than about one frame out gets pulled back
  var root = document.querySelector("[data-player]");
  if (!root) return;

  var byId = {};
  DATA.methods.forEach(function (m) { byId[m.id] = m; });

  // ------------------------------------------------------------------ state
  var state = {
    source: DATA.sources[0].id,
    picked: DATA.defaultPick.slice(),
    mode: "split",
    zoom: 1,
    // pan is in fractions of the frame, 0.5/0.5 is centred
    px: 0.5,
    py: 0.5,
    playing: false,
    pixelated: false,
  };

  var panes = [];      // { method, video, wrap, el }
  var master = null;

  // ------------------------------------------------------------------ helpers
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function source() {
    return DATA.sources.filter(function (s) { return s.id === state.source; })[0];
  }

  function cell(methodId) {
    return DATA.cells[methodId][state.source];
  }

  function mediaUrl(path) {
    return DATA.mediaBase + "/" + path;
  }

  function currentTime() {
    return master && isFinite(master.video.currentTime) ? master.video.currentTime : 0;
  }

  function frameOf(t) {
    return Math.min(DATA.frames - 1, Math.max(0, Math.round(t * FPS)));
  }

  // ------------------------------------------------------------------ building panes
  function buildPanes() {
    var stage = root.querySelector("[data-stage]");
    stage.innerHTML = "";
    panes = [];
    master = null;

    var ids = state.picked;
    stage.className = "sh-stage sh-" + state.mode;
    stage.style.setProperty("--panes", String(ids.length));
    // The sources are 1.75:1, not 16:9. Taking the ratio from the clip rather than
    // assuming one means nothing is ever cropped out of a comparison.
    var s = source();
    stage.style.setProperty("--ar", s.target[0] + " / " + s.target[1]);
    // numeric form of the same ratio, so CSS can cap the stage by height and still
    // shrink the width to match instead of letterboxing
    var wrap = stage.parentNode;
    if (wrap) wrap.style.setProperty("--arn", (s.target[0] / s.target[1]).toFixed(4));

    ids.forEach(function (id, i) {
      var m = byId[id];
      var c = cell(id);

      var pane = el("div", "sh-pane");
      pane.style.setProperty("--tier", m.tierColour);

      var view = el("div", "sh-view");
      var video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.loop = false;             // the loop is driven centrally so panes restart together
      video.preload = "auto";
      video.poster = mediaUrl(c.poster);
      video.src = mediaUrl(c.clip);
      video.setAttribute("aria-label", m.name + " on " + source().label);
      view.appendChild(video);

      var tag = el("div", "sh-tag");
      tag.appendChild(el("b", null, m.name));
      var sub = el("span", null, m.tier);
      tag.appendChild(sub);
      view.appendChild(tag);

      pane.appendChild(view);

      var facts = el("div", "sh-facts");
      var bits = [];
      if (c.wall) bits.push(c.wall);
      if (c.peak_vram_mib) bits.push((c.peak_vram_mib / 1024).toFixed(1) + " GB peak");
      if (c.service) bits.push(c.delivered[0] + "x" + c.delivered[1] + " delivered");
      if (!bits.length) bits.push(m.kind);
      facts.textContent = bits.join(" · ");
      pane.appendChild(facts);

      stage.appendChild(pane);
      var entry = { method: m, video: video, view: view, pane: pane };
      panes.push(entry);
      if (i === 0) master = entry;
    });

    if (state.mode === "split" && panes.length === 2) addDivider(stage);

    applyTransform();
    attachSync();
    updateReadout();
  }

  // The split view is one pane clipped by a draggable divider over the other, so the two
  // halves are the same picture at the same instant rather than two boxes side by side.
  function addDivider(stage) {
    var handle = el("div", "sh-divider");
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-label", "Drag to compare");
    handle.setAttribute("tabindex", "0");
    stage.appendChild(handle);

    var split = 0.5;
    function place() {
      stage.style.setProperty("--split", (split * 100).toFixed(2) + "%");
    }
    place();

    function moveTo(clientX) {
      var r = stage.getBoundingClientRect();
      split = Math.min(1, Math.max(0, (clientX - r.left) / r.width));
      place();
    }
    handle.addEventListener("pointerdown", function (e) {
      handle.setPointerCapture(e.pointerId);
      handle.dataset.dragging = "1";
      e.preventDefault();
    });
    handle.addEventListener("pointermove", function (e) {
      if (handle.dataset.dragging) moveTo(e.clientX);
    });
    handle.addEventListener("pointerup", function (e) {
      delete handle.dataset.dragging;
      handle.releasePointerCapture(e.pointerId);
    });
    handle.addEventListener("keydown", function (e) {
      var step = e.shiftKey ? 0.1 : 0.02;
      if (e.key === "ArrowLeft") { split = Math.max(0, split - step); place(); e.preventDefault(); }
      if (e.key === "ArrowRight") { split = Math.min(1, split + step); place(); e.preventDefault(); }
    });
  }

  // ------------------------------------------------------------------ zoom and pan

  // Screen pixels per video pixel at the current zoom. The zoom buttons are multiples of
  // fit-to-width, and fit-to-width is not the same magnification on every clip: a
  // 2688-wide output sits at about 0.42x native in this column, a 2048-wide one at 0.55x.
  // So "4x" means 1.7x native on one clip and 2.2x on another, and "2x" leaves both still
  // downscaled. Anything that depends on seeing real pixels has to ask this, not the zoom.
  function magnification() {
    if (!panes.length) return 0;
    var shown = panes[0].view.getBoundingClientRect().width * state.zoom;
    return shown / source().target[0];
  }

  function applyTransform() {
    var z = state.zoom;
    // translate so that (px, py) of the frame sits in the middle of the viewport
    var tx = (0.5 - state.px) * 100;
    var ty = (0.5 - state.py) * 100;
    var mag = magnification();
    panes.forEach(function (p) {
      p.video.style.transform = "scale(" + z + ") translate(" + tx + "%, " + ty + "%)";
      // Below 1x native the browser is discarding pixels, so nearest-neighbour would show
      // which ones it chose to drop rather than what the upscaler produced.
      p.video.style.imageRendering = (state.pixelated && mag >= 1) ? "pixelated" : "auto";
    });
    root.classList.toggle("sh-zoomed", z > 1);
    var loupe = root.querySelector("[data-loupe]");
    if (loupe) loupe.hidden = z <= 1;
    positionLoupe();
    updatePixelButton(mag);
    updateReadout();
  }

  function updatePixelButton(mag) {
    var px = root.querySelector("[data-pixelate]");
    if (!px) return;
    px.disabled = mag < 1;
    px.title = mag >= 1
      ? "Nearest-neighbour instead of smoothing, so you see the pixels the method wrote. "
        + "Currently " + mag.toFixed(1) + "x native."
      : "Zoom in further first. At " + mag.toFixed(2) + "x native the frame is still being "
        + "scaled down, so there are no real pixels to show.";
  }

  function clampPan() {
    // at zoom z the visible window is 1/z of the frame, so the centre cannot go closer
    // to an edge than half of that without showing blank
    var half = 0.5 / state.zoom;
    state.px = Math.min(1 - half, Math.max(half, state.px));
    state.py = Math.min(1 - half, Math.max(half, state.py));
  }

  function setZoom(z) {
    state.zoom = z;
    clampPan();
    applyTransform();
    root.querySelectorAll("[data-zoom]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(Number(b.dataset.zoom) === z));
    });
  }

  function attachPan(stage) {
    var dragging = false, lastX = 0, lastY = 0;
    stage.addEventListener("pointerdown", function (e) {
      if (state.zoom <= 1 || e.target.classList.contains("sh-divider")) return;
      dragging = true; lastX = e.clientX; lastY = e.clientY;
      stage.setPointerCapture(e.pointerId);
      stage.classList.add("sh-grabbing");
    });
    stage.addEventListener("pointermove", function (e) {
      if (!dragging) return;
      var r = stage.getBoundingClientRect();
      state.px -= (e.clientX - lastX) / (r.width * state.zoom);
      state.py -= (e.clientY - lastY) / (r.height * state.zoom);
      lastX = e.clientX; lastY = e.clientY;
      clampPan();
      applyTransform();
    });
    ["pointerup", "pointercancel"].forEach(function (ev) {
      stage.addEventListener(ev, function (e) {
        if (!dragging) return;
        dragging = false;
        stage.releasePointerCapture(e.pointerId);
        stage.classList.remove("sh-grabbing");
      });
    });
    // clicking into the picture at 1x zooms to that point, which is faster than
    // zooming then hunting for the thing you wanted to look at
    stage.addEventListener("click", function (e) {
      if (state.zoom > 1 || !e.target.matches("video")) return;
      var r = e.target.getBoundingClientRect();
      state.px = (e.clientX - r.left) / r.width;
      state.py = (e.clientY - r.top) / r.height;
      setZoom(2);
    });
  }

  // A small map of where the zoom window sits in the whole frame, because at 4x it is
  // otherwise impossible to tell which part of the shot you are looking at.
  function positionLoupe() {
    var loupe = root.querySelector("[data-loupe]");
    if (!loupe || loupe.hidden) return;
    var box = loupe.querySelector(".sh-loupe-box");
    var size = 100 / state.zoom;
    box.style.width = size + "%";
    box.style.height = size + "%";
    box.style.left = (state.px * 100 - size / 2) + "%";
    box.style.top = (state.py * 100 - size / 2) + "%";
  }

  // ------------------------------------------------------------------ playback sync
  var rafId = null;

  function attachSync() {
    panes.forEach(function (p) {
      p.video.addEventListener("loadedmetadata", updateReadout);
    });
    if (rafId) cancelAnimationFrame(rafId);
    tick();
  }

  function tick() {
    rafId = requestAnimationFrame(tick);
    if (!master) return;
    var t = master.video.currentTime;

    // central loop: when the master reaches the end everything restarts together, so the
    // panes cannot slowly fan out over repeated plays the way per-element loop does
    if (state.playing && master.video.ended) {
      seek(0);
      play();
      return;
    }
    if (state.playing) {
      panes.forEach(function (p) {
        if (p === master) return;
        if (Math.abs(p.video.currentTime - t) > SYNC_TOLERANCE) p.video.currentTime = t;
      });
    }
    updateScrub(t);
  }

  function play() {
    state.playing = true;
    panes.forEach(function (p) { var q = p.video.play(); if (q && q.catch) q.catch(function () {}); });
    root.querySelector("[data-play]").setAttribute("aria-pressed", "true");
    root.querySelector("[data-play]").textContent = "Pause";
  }

  function pause() {
    state.playing = false;
    panes.forEach(function (p) { p.video.pause(); });
    root.querySelector("[data-play]").setAttribute("aria-pressed", "false");
    root.querySelector("[data-play]").textContent = "Play";
  }

  function seek(t) {
    t = Math.min(DATA.duration, Math.max(0, t));
    panes.forEach(function (p) { p.video.currentTime = t; });
    updateScrub(t);
  }

  function step(frames) {
    pause();
    seek(frameOf(currentTime()) * FRAME + frames * FRAME);
  }

  function updateScrub(t) {
    var scrub = root.querySelector("[data-scrub]");
    if (scrub && document.activeElement !== scrub) scrub.value = String(frameOf(t));
    var read = root.querySelector("[data-frame]");
    if (read) read.textContent = "frame " + (frameOf(t) + 1) + " / " + DATA.frames;
  }

  // ------------------------------------------------------------------ chrome
  function updateReadout() {
    var s = source();
    var out = root.querySelector("[data-geometry]");
    if (out) {
      var mag = magnification();
      out.textContent = s.width + "x" + s.height + " source → " +
        s.target[0] + "x" + s.target[1] + " output, " + DATA.frames + " frames at " + FPS + " fps"
        + (mag ? "  ·  showing " + mag.toFixed(2) + "x native" : "");
    }
    var blurb = root.querySelector("[data-source-blurb]");
    if (blurb) blurb.textContent = s.blurb;
  }

  function pickMethod(id) {
    var i = state.picked.indexOf(id);
    if (i >= 0) {
      if (state.picked.length <= 2) return;   // two is the minimum a comparison can be
      state.picked.splice(i, 1);
    } else {
      state.picked.push(id);
      // A third method cannot be shown as a split, so asking for one is a request for the
      // grid. Silently dropping the oldest pick instead would lose the pane someone was
      // half way through comparing.
      if (state.mode === "split" && state.picked.length > 2) setMode("grid");
    }
    syncChips();
    rebuild();
  }

  function syncChips() {
    root.querySelectorAll("[data-method]").forEach(function (b) {
      var on = state.picked.indexOf(b.dataset.method) >= 0;
      b.setAttribute("aria-pressed", String(on));
      var n = state.picked.indexOf(b.dataset.method);
      b.dataset.slot = on ? String(n + 1) : "";
    });
  }

  function setMode(mode) {
    state.mode = mode;
    if (mode === "split" && state.picked.length > 2) state.picked = state.picked.slice(-2);
    root.querySelectorAll("[data-mode]").forEach(function (o) {
      o.setAttribute("aria-pressed", String(o.dataset.mode === mode));
    });
  }

  function rebuild() {
    var t = currentTime();
    var wasPlaying = state.playing;
    buildPanes();
    seek(t);
    if (wasPlaying) play(); else pause();
  }

  // ------------------------------------------------------------------ wiring
  root.querySelectorAll("[data-source]").forEach(function (b) {
    b.addEventListener("click", function () {
      state.source = b.dataset.source;
      root.querySelectorAll("[data-source]").forEach(function (o) {
        o.setAttribute("aria-pressed", String(o === b));
      });
      rebuild();
    });
  });

  root.querySelectorAll("[data-method]").forEach(function (b) {
    b.addEventListener("click", function () { pickMethod(b.dataset.method); });
  });

  root.querySelectorAll("[data-mode]").forEach(function (b) {
    b.addEventListener("click", function () {
      setMode(b.dataset.mode);
      syncChips();
      rebuild();
    });
  });

  root.querySelectorAll("[data-zoom]").forEach(function (b) {
    b.addEventListener("click", function () { setZoom(Number(b.dataset.zoom)); });
  });

  var pixelate = root.querySelector("[data-pixelate]");
  if (pixelate) {
    pixelate.addEventListener("click", function () {
      state.pixelated = !state.pixelated;
      pixelate.setAttribute("aria-pressed", String(state.pixelated));
      applyTransform();
    });
  }

  root.querySelector("[data-play]").addEventListener("click", function () {
    if (state.playing) pause(); else play();
  });
  root.querySelector("[data-back]").addEventListener("click", function () { step(-1); });
  root.querySelector("[data-fwd]").addEventListener("click", function () { step(1); });

  var scrub = root.querySelector("[data-scrub]");
  scrub.max = String(DATA.frames - 1);
  scrub.addEventListener("input", function () {
    pause();
    seek(Number(scrub.value) * FRAME);
  });

  // Keyboard, because comparing two upscalers is frame-by-frame work and reaching for
  // the mouse for every frame makes it unbearable.
  document.addEventListener("keydown", function (e) {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;
    // Only while the player is actually on screen, so Space still scrolls the page
    // everywhere else. Stealing the spacebar from someone reading the findings would be
    // its own small bug.
    var box = root.querySelector("[data-stage]").getBoundingClientRect();
    if (box.bottom < 0 || box.top > window.innerHeight) return;
    if (e.key === " ") { e.preventDefault(); state.playing ? pause() : play(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); step(-1); }
    else if (e.key === "ArrowRight") { e.preventDefault(); step(1); }
    else if (e.key === "1") setZoom(1);
    else if (e.key === "2") setZoom(2);
    else if (e.key === "4") setZoom(4);
  });

  attachPan(root.querySelector("[data-stage]"));
  syncChips();
  buildPanes();
  setZoom(1);

  // ------------------------------------------------------------------ extras
  // The extra sections reuse the same synced-playback trick without the zoom chrome:
  // a row of clips that all start together when any one of them is played.
  document.querySelectorAll("[data-syncrow]").forEach(function (row) {
    var vids = Array.prototype.slice.call(row.querySelectorAll("video"));
    var playing = false;
    var lead = vids[0];
    row.querySelectorAll("[data-rowplay]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        playing = !playing;
        btn.textContent = playing ? "Pause all" : "Play all";
        vids.forEach(function (v) {
          v.currentTime = 0;
          if (playing) { var q = v.play(); if (q && q.catch) q.catch(function () {}); } else v.pause();
        });
      });
    });
    setInterval(function () {
      if (!playing) return;
      vids.forEach(function (v) {
        if (v !== lead && Math.abs(v.currentTime - lead.currentTime) > SYNC_TOLERANCE) {
          v.currentTime = lead.currentTime;
        }
      });
    }, 250);
  });
})();
