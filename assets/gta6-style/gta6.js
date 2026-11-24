/* GTA VI style prompt builder page. The prompt itself comes from gta6_prompt.js (the node pack's logic). */
(async function () {
  "use strict";
  const G = window.GTA6;
  const $ = id => document.getElementById(id);
  let db;
  try { db = await (await fetch("/assets/gta6-style/presets.json?v=1")).json(); }
  catch (err) { $("g6-error").hidden = false; $("g6-error").textContent = "The presets didn't load. Reload the page to try again."; return; }
  const O = G.options(db);
  const MAX = 4;
  const MODE_LABEL = ["One photo", "A photo per person", "Text only"];
  const MODE_HINT = [
    "One photo of one person. The face comes from your photo.",
    "One photo for each person, up to four. Person 1 is image 1, person 2 is image 2.",
    "No photo. Describe each person in their details.",
  ];
  const LABEL = {theme: "Theme", style_variant: "Style", background: "Background", hue: "Colours", vehicle: "Vehicle",
                 aspect: "Size", hair: "Hair", facial_hair: "Facial hair", outfit: "Outfit", accessory: "Accessory", pose: "Pose",
                 group_setup: "Group setup", title_space: "Space for a title"};

  const state = {
    mode: 0,
    theme: Object.fromEntries(Object.entries(O.theme).map(([k, v]) => [k, v[0]])),
    sign_text: "",
    people: [{g: "female", f: {}}],
    builder: {group_setup: "auto", title_space: "off"},
    your_prompt: "",
  };

  const el = (tag, attrs = {}, kids = []) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "text") n.textContent = v; else if (k in n && typeof v !== "string") n[k] = v; else n.setAttribute(k, v);
    }
    for (const k of [].concat(kids)) if (k) n.append(k);
    return n;
  };
  function select(label, opts, value, onchange) {
    const s = el("select");
    for (const o of opts) s.append(el("option", {value: o, text: o}));
    s.value = value;
    s.addEventListener("change", () => { onchange(s.value); update(); });
    return el("label", {class: "g6-field"}, [el("span", {text: label}), s]);
  }
  function input(label, value, placeholder, onchange, wide) {
    const i = el("input", {type: "text", placeholder});
    i.value = value;
    i.addEventListener("input", () => { onchange(i.value); update(); });
    return el("label", {class: "g6-field" + (wide ? " g6-wide" : "")}, [el("span", {text: label}), i]);
  }

  // ---------------------------------------------------------------- render controls
  function renderMode() {
    const box = $("g6-mode");
    box.replaceChildren(...MODE_LABEL.map((m, i) => {
      const b = el("button", {type: "button", role: "radio", "aria-checked": String(state.mode === i), text: m});
      b.addEventListener("click", () => { state.mode = i; renderAll(); });
      return b;
    }));
    $("g6-mode-hint").textContent = MODE_HINT[state.mode];
  }
  function renderTheme() {
    const t = state.theme;
    $("g6-theme").replaceChildren(
      ...["theme", "style_variant", "background", "hue", "vehicle", "aspect"].map(k => select(LABEL[k], O.theme[k], t[k], v => (t[k] = v))),
      input("Sign text", state.sign_text, "Empty means signs stay blank", v => (state.sign_text = v), true));
  }
  function renderPeople() {
    const text = state.mode === 2;
    $("g6-people-hint").textContent = state.mode === 0
      ? "Anything left on keep from photo stays as it is in your photo."
      : text ? "Left to right. Details continue \"a woman ...\" or \"a man ...\", for example: of Korean descent in her late twenties."
             : "Left to right, in the same order as your photos. Anything left on keep from photo stays as it is in that photo.";
    $("g6-people").replaceChildren(...state.people.map((p, i) => {
      const opts = O[p.g];
      const fields = Object.keys(opts).map(k => {
        let list = opts[k];
        if (text && list[0] === G.KEEP) list = ["(any)", ...list.slice(1)];  // nothing to keep without a photo
        const cur = p.f[k] === undefined ? list[0] : (p.f[k] === G.KEEP && text ? "(any)" : p.f[k]);
        return select(LABEL[k], list, cur, v => (p.f[k] = v === "(any)" ? G.KEEP : v));
      });
      fields.push(input("Details", p.f.details || "", text ? "of Korean descent in her late twenties" : "holding a champagne flute",
                        v => (p.f.details = v), true));
      const rm = el("button", {type: "button", class: "g6-rm", text: "Remove", "aria-label": `Remove person ${i + 1}`});
      rm.addEventListener("click", () => { state.people.splice(i, 1); renderAll(); });
      rm.hidden = state.people.length === 1;
      return el("li", {class: "g6-person"}, [
        el("div", {class: "g6-person-head"}, [el("strong", {text: `Person ${i + 1}`}), el("span", {text: p.g === "female" ? "woman" : "man"}), rm]),
        el("div", {class: "g6-grid"}, fields)]);
    }));
    const full = state.people.length >= (state.mode === 0 ? 1 : MAX);
    $("g6-add").querySelectorAll("button").forEach(b => (b.disabled = full));
  }
  function renderScene() {
    const b = state.builder;
    $("g6-scene").replaceChildren(...["group_setup", "title_space"].map(k => select(LABEL[k], O.builder[k], b[k], v => (b[k] = v))));
    $("g6-your").value = state.your_prompt;
  }
  function renderAll() { renderMode(); renderTheme(); renderPeople(); renderScene(); update(); }

  // ---------------------------------------------------------------- prompt
  function update() {
    const err = $("g6-error");
    try {
      const th = G.theme(db, Object.assign({}, state.theme, {sign_text: state.sign_text}));
      const ppl = state.people.map(p => G.person(db, p.g, p.f));
      const r = G.build(db, th, ppl, Object.assign({mode: G.MODES[state.mode], your_prompt: state.your_prompt}, state.builder));
      err.hidden = true;
      $("g6-prompt").value = r.prompt;
      $("g6-style").value = r.style_only;
      $("g6-size").textContent = `${r.width} × ${r.height}`;
      $("g6-count").textContent = `${r.prompt.split(/\s+/).length} words`;
      $("g6-images").textContent = state.mode === 2 ? "No image input needed."
        : state.mode === 0 ? "Connect your photo as image 1."
        : "Connect " + state.people.map((p, i) => `person ${i + 1}'s photo as image ${i + 1}`).join(", ") + ".";
    } catch (x) {
      err.hidden = false;
      err.textContent = state.mode === 0 && state.people.length > 1
        ? "One photo takes one person. Remove the others, or switch to a photo per person."
        : x.message;
    }
  }
  $("g6-your").addEventListener("input", e => { state.your_prompt = e.target.value; update(); });
  $("g6-add").addEventListener("click", e => {
    const g = e.target.closest("[data-add]");
    if (g && state.people.length < MAX) { state.people.push({g: g.dataset.add, f: {}}); renderPeople(); update(); }
  });
  document.querySelectorAll("[data-g6copy]").forEach(btn => {
    const label = btn.textContent;
    btn.addEventListener("click", async () => {
      const ta = $(btn.dataset.g6copy);
      try { await navigator.clipboard.writeText(ta.value); btn.textContent = "Copied"; }
      catch { ta.select(); btn.textContent = "Selected, press Ctrl+C"; }
      setTimeout(() => (btn.textContent = label), 2200);
    });
  });

  // ---------------------------------------------------------------- showcase -> builder
  document.addEventListener("click", e => {
    const b = e.target.closest(".g6-load");
    if (!b) return;
    const c = window.GTA6_CASES[+b.dataset.case];
    state.mode = G.MODES.indexOf(c.mode);
    state.theme = Object.fromEntries(Object.entries(O.theme).map(([k, v]) => [k, c.theme[k] || v[0]]));
    state.sign_text = c.theme.sign_text || "";
    state.people = c.people.map(p => {
      const f = Object.assign({}, p); delete f.t;
      return {g: p.t === "W" ? "female" : "male", f};
    });
    state.builder = {group_setup: (c.builder || {}).group_setup || "auto", title_space: (c.builder || {}).title_space || "off"};
    state.your_prompt = (c.builder || {}).your_prompt || "";
    renderAll();
    $("builder").scrollIntoView({behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"});
  });

  renderAll();
})();
