/* GTA VI style prompt builder: a line-for-line port of nodes.py, so the website writes the same prompt
   the ComfyUI nodes do. parity_test.py checks the two against each other over thousands of random settings.

   const db = await (await fetch("presets.json")).json();
   const theme = GTA6.theme(db, {theme, style_variant, background, hue, vehicle, sign_text, aspect});
   const people = [GTA6.person(db, "female", {hair, outfit, accessory, pose, details}), ...];
   const {prompt, width, height, style_only} = GTA6.build(db, theme, people, {mode, group_setup, your_prompt, title_space});
*/
(function (root) {
  "use strict";
  const KEEP = "keep from photo", OFF = "off", THEME = "(from theme)", FROM_GROUP = "(from group setup)";
  const MODES = ["one photo, one person", "one photo per person (image 1, 2, ...)", "text only (no photo)"];
  const NUM = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"};
  const ORD = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"};
  const PRON = {female: ["she", "her", "her", "woman"], male: ["he", "his", "him", "man"]};
  const TITLE_SPACE = {"off": null, "auto": "auto", "left side": "left", "right side": "right", "top": "top"};
  const TITLE_FRAMING = {
    left: "Compose a wide landscape frame like official crime-game key art: {fig} stand in the right half of the frame, shown from the " +
          "knees up, while the left half is open sky and simple distant background with no figures in it, leaving a large empty " +
          "space for a title.",
    right: "Compose a wide landscape frame like official crime-game key art: {fig} stand in the left half of the frame, shown from the " +
           "knees up, while the right half is open sky and simple distant background with no figures in it, leaving a large empty " +
           "space for a title.",
    top: "Compose the frame like an official crime-game cover poster: {fig} fill the lower half of the frame, while the upper " +
         "half above their heads is open sky with only palm silhouettes at the edges, leaving a large empty space for a title.",
  };

  const byName = (items, n) => (items || []).find(i => i.name === n) || null;
  const cap = s => s.slice(0, 1).toUpperCase() + s.slice(1);
  const rep = (s, a, b) => s.split(a).join(b);
  const ord = i => ORD[i] || (i + "th");
  const num = n => NUM[n] || String(n);
  function join(items) {
    items = items.filter(Boolean);
    if (items.length === 1) return items[0];
    return items.length ? items.slice(0, -1).join(", ") + " and " + items[items.length - 1] : "";
  }

  function options(db) {
    const names = a => a.map(i => i.name);
    const person = g => {
      const o = {hair: [KEEP, ...names(db[g].hair)]};
      if (g === "male") o.facial_hair = [KEEP, ...names(db[g].facial_hair)];
      o.outfit = [KEEP, ...names(db[g].outfit)];
      o.accessory = [OFF, ...names(db[g].accessory)];
      o.pose = [FROM_GROUP, ...names(db.pose)];
      return o;
    };
    return {
      theme: {theme: names(db.theme), style_variant: names(db.style_variant), background: [THEME, ...names(db.location)],
              hue: [THEME, ...names(db.palette)], vehicle: [OFF, ...names(db.vehicle)], aspect: names(db.aspect)},
      female: person("female"), male: person("male"),
      builder: {mode: MODES, group_setup: names(db.group_setup), title_space: Object.keys(TITLE_SPACE)},
    };
  }

  function theme(db, o) {
    const t = byName(db.theme, o.theme), a = byName(db.aspect, o.aspect);
    return {
      variant: byName(db.style_variant, o.style_variant),
      lighting: byName(db.lighting, t.lighting).text,
      bg: byName(db.background_treatment, t.background_treatment).text,
      palette: byName(db.palette, o.hue === THEME ? t.palette : o.hue).text,
      location: byName(db.location, o.background === THEME ? t.location : o.background),
      vehicle: byName(db.vehicle, o.vehicle),
      sign_text: (o.sign_text || "").trim(),
      framing: t.framing || null,
      w: a.w, h: a.h,
    };
  }

  function person(db, g, f) {
    const sec = db[g];
    const p = {gender: g, keep: [], details: (f.details || "").trim()};
    const pose = byName(db.pose, f.pose || "");
    p.pose = pose ? pose.text : "";
    const lists = {hair: sec.hair, facial_hair: sec.facial_hair || [], outfit: sec.outfit, accessory: sec.accessory};
    for (const k of (g === "male" ? ["hair", "facial_hair", "outfit", "accessory"] : ["hair", "outfit", "accessory"])) {
      const v = f[k] === undefined ? (k === "accessory" ? OFF : KEEP) : f[k];
      if (v === KEEP) p.keep.push(k);
      const item = byName(lists[k], v);
      p[k] = item ? item.text : "";
    }
    return p;
  }

  function refs(people, mode) {
    const n = people.length;
    const counts = {female: 0, male: 0};
    people.forEach(p => counts[p.gender]++);
    people.forEach((p, k) => {
      const i = k + 1;
      const [sub, pos, obj, noun] = PRON[p.gender];
      Object.assign(p, {sub, pos, obj, noun});
      let ref;
      if (mode === MODES[0] && n >= 3) ref = `the ${ord(i)} person from the left`;
      else if (n === 1 || counts[p.gender] === 1) ref = `the ${noun}`;
      else if (mode === MODES[0] && n === 2) ref = `the ${noun} on the ${i === 1 ? "left" : "right"}`;
      else if (mode === MODES[0]) ref = `the ${ord(i)} person from the left`;
      else ref = `the ${ord(i)} ${noun}`;
      p.ref = ref;
      p.first = mode === MODES[1] ? `${ref} in <image${i}>` : ref;
      p.r_sub = n === 1 ? sub : ref;
      p.r_obj = n === 1 ? obj : ref;
      p.r_pos = n === 1 ? pos : ref + "'s";
    });
  }

  const render = (v, lighting, who) =>
    [`Render ${who} with ${v.shading}.`, `Light ${who} with ${lighting}.`, `Draw ${who} with ${v.line_art}.`, `Show ${v.detail}.`];

  function build(db, th, people, o) {
    const mode = o.mode || MODES[0], group_setup = o.group_setup || "auto";
    const your_prompt = o.your_prompt || "", title_space = o.title_space || "off";
    people = (people || []).map(p => Object.assign({}, p, {keep: [...p.keep]}));
    const text_mode = mode === MODES[2], per_photo = mode === MODES[1];
    if (!people.length) throw new Error(`'${mode}' needs at least one person.`);
    if (mode === MODES[0] && people.length !== 1)
      throw new Error("'one photo, one person' takes exactly one person. For groups, use one photo per person.");
    refs(people, mode);
    const n = people.length, group = n !== 1;
    const v = th.variant, medium = v.medium;
    const S = [];
    const keptOf = p => [["hairstyle", "hair"], ["facial hair", "facial_hair"], ["clothing", "outfit"]].filter(([, f]) => p.keep.includes(f)).map(([k]) => k);

    // 1. operation + identity
    const all_keep = people.every(p => p.keep.includes("hair") && p.keep.includes("outfit"));
    if (text_mode) {
      const descs = people.map(p => `a ${p.noun}` + (p.details ? ` ${p.details}` : ""));
      S.push(`Create ${medium}, showing ${join(descs)}.`);
    } else if (n === 1) {
      const p = people[0];
      const kept = ["facial identity", ...keptOf(p)];
      S.push(`Create a new illustrated scene of the ${p.noun} in the image, keeping ${p.pos} ${join(kept)} exactly as shown in the image, ` +
             `and change the rendering medium from photograph to ${medium}.`);
    } else {
      const who = per_photo ? join(people.map(p => p.first)) : `the ${num(n)} people in the image`;
      const where = per_photo ? "their image" : "the image";
      const kept = all_keep ? "facial identity, hairstyle and clothing" : "facial identity";
      S.push(`Create a new illustrated scene of ${who}, keeping each person's ${kept} exactly as shown in ${where}, ` +
             `and change the rendering medium from photograph to ${medium}.`);
    }

    // 2. per-person overrides
    people.forEach((p, k) => {
      const i = k + 1;
      if (group && !text_mode && !all_keep) {
        const kept = keptOf(p);
        if (kept.length) S.push(`Keep ${p.r_pos} ${join(kept)} as shown in ${per_photo ? `<image${i}>` : "the image"}.`);
      }
      if (p.hair) S.push(text_mode ? `Give ${p.r_obj} ${p.hair}.` : `Restyle ${p.r_pos} hair into ${p.hair}.`);
      if (p.facial_hair) S.push(`Give ${p.r_obj} ${p.facial_hair}.`);
      if (p.outfit) S.push(`Dress ${p.r_obj} in ${p.outfit}` + (p.accessory ? `, with ${p.accessory}` : "") + ".");
      else if (p.accessory) S.push(`Add ${p.accessory} to ${p.r_obj}.`);
      if (p.details && !text_mode) S.push(`Show ${p.r_obj} ${p.details}.`);
    });

    // 3. rendering
    S.push(...render(v, th.lighting, group ? "every figure" : people[0].obj));
    if (!text_mode && group)
      S.push("Redraw every face, body and garment fully in this illustrated style, so each person matches the drawn look of the scene around them.");

    // 4. group setup + vehicle
    const veh = th.vehicle;
    const car = veh ? veh.text : "a car";
    let gs = byName(db.group_setup, group_setup);
    if (group_setup === "auto") {
      const key = veh && veh.place === "behind" ? "Leaning on the car" : (group ? "Key-art lineup" : "Hero pose, facing viewer");
      gs = byName(db.group_setup, key);
    }
    const all_ref = n <= 2 ? join(people.map(p => p.ref)) : `all ${num(n)} people`;
    let t = group ? gs.group : gs.solo;
    if (n === 1 && people[0].pose && group_setup === "auto") t = "";
    if (t) {
      t = rep(t, "{All}", cap(all_ref));
      t = rep(t, "{Sub}", n === 1 ? cap(people[0].sub) : "");
      t = rep(t, "{car}", car);
      t = rep(t, "{pos}", n === 1 ? people[0].pos : "their");
      S.push(t);
    }
    if (veh && !gs.car) {
      const them = group ? "them" : people[0].obj;
      S.push({behind: `${cap(car)} is parked behind ${them}.`, sky: `${cap(car)} flies overhead in the sky.`,
              aboard: `${cap(group ? "they" : people[0].sub)} ride${group ? "" : "s"} aboard ${car}.`}[veh.place]);
    }
    for (const p of people) if (p.pose) S.push(`${cap(p.r_sub)} ${rep(p.pose, "{pos}", p.pos)}.`);

    // 5. user's specifics
    if (your_prompt.trim()) S.push(your_prompt.trim());

    // 6. scene, sign text, background
    const loc = th.location;
    S.push(`Set the scene ${loc.text}.`);
    const st = th.sign_text;
    if (!st) S.push("All signage is drawn as blank panels and abstract neon shapes.");
    else if (loc.sign) S.push(cap(rep(loc.sign, "{text}", st)) + ", and any other signs are blank panels and abstract neon shapes.");
    else S.push(`A sign in the background reads "${st}", and any other signs are blank panels and abstract neon shapes.`);
    S.push(`Build the background as ${th.bg}, using ${th.palette}.`);

    // 7. framing
    const portrait = th.h > th.w;
    let side = TITLE_SPACE[title_space] || null;
    if (side === "auto") side = portrait || th.h === th.w || n >= 3 ? "top" : "left";
    if (side) S.push(TITLE_FRAMING[side]);
    else {
      let fr = th.framing;
      if (!fr) {
        const big = n >= 3;
        fr = portrait ? (big ? "Full body, centred" : "Low-angle hero, 3/4 body") : (big ? "Wide group shot" : "Wide, figures on left third (default)");
      }
      S.push(`Compose ${byName(db.framing, fr).text}.`);
    }
    const prompt = rep(S.join(" "), "{fig}", n === 1 ? "the figure" : "the figures");
    const style_only = rep([`Draw it as ${medium}.`, ...render(v, th.lighting, "the figures"),
                            `Build the background as ${th.bg}, using ${th.palette}.`].join(" "), "{fig}", "the figures");
    return {prompt, width: th.w, height: th.h, style_only};
  }

  const api = {KEEP, OFF, THEME, FROM_GROUP, MODES, options, theme, person, build};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.GTA6 = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
