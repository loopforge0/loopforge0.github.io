// Loop Forge. Small behaviour shared by every page. Search loads Orama only when someone uses it.

// Colour theme. Pages follow the system setting. Pressing the toggle stores an override in this browser only
// (no cookie, nothing sent anywhere), and switching back to the system's own theme deletes it again.
{
  const root = document.documentElement;
  const system = matchMedia("(prefers-color-scheme: dark)");
  const systemTheme = () => (system.matches ? "dark" : "light");
  const current = () => root.dataset.theme || systemTheme();
  const label = (btn) => {
    const next = current() === "dark" ? "light" : "dark";
    btn.setAttribute("aria-label", `Switch to ${next} mode`);
    btn.title = `Switch to ${next} mode`;
  };
  document.querySelectorAll("[data-theme-toggle]").forEach((btn) => {
    label(btn);
    btn.addEventListener("click", () => {
      const next = current() === "dark" ? "light" : "dark";
      try {
        if (next === systemTheme()) {
          delete root.dataset.theme;
          localStorage.removeItem("theme");
        } else {
          root.dataset.theme = next;
          localStorage.setItem("theme", next);
        }
      } catch {
        root.dataset.theme = next;
      }
      label(btn);
    });
    system.addEventListener("change", () => label(btn));
  });
}

// The banner reel plays only when motion is welcome and it is on screen, and can be paused.
{
  const reel = document.querySelector("[data-reel]");
  const still = matchMedia("(prefers-reduced-motion: reduce)");
  if (reel && !still.matches) {
    let paused = false;
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "reel-toggle";
    const sync = () => (toggle.textContent = paused ? "Play background" : "Pause background");
    toggle.addEventListener("click", () => {
      paused = !paused;
      paused ? reel.pause() : reel.play().catch(() => {});
      sync();
    });
    sync();
    reel.after(toggle);
    new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting && !paused) reel.play().catch(() => {});
      else reel.pause();
    }).observe(reel);
  }
}

// Site search, powered by Orama over assets/search-index.json.
document.querySelectorAll("[data-finder]").forEach((form) => {
  const input = form.querySelector("input");
  const panel = form.querySelector(".finder-results");
  let db = null;
  let docs = null;
  let loading = null;
  let timer = 0;

  const load = () =>
    (loading ||= Promise.all([
      import("/assets/vendor/orama-3.1.18.min.js"),
      fetch("/assets/search-index.json").then((r) => r.json()),
    ]).then(async ([orama, list]) => {
      docs = new Map(list.map((d) => [d.id, d]));
      db = orama.create({ schema: { title: "string", body: "string", tags: "string", video: "string" } });
      await orama.insertMultiple(db, list.map(({ id, title, body, tags, video }) => ({ id, title, body, tags, video })));
      return orama;
    }));

  const close = () => {
    panel.hidden = true;
    input.setAttribute("aria-expanded", "false");
  };

  const show = (term, hits) => {
    const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
    const rows = hits.map(({ id }) => {
      const d = docs.get(id);
      const where = d.kind === "Project" ? "Project" : `Prompt from ${d.video}`;
      return `<a href="${d.url}"><img src="${d.thumb}" alt="" loading="lazy"><span><b>${esc(d.title)}</b><small>${esc(where)}</small></span></a>`;
    });
    panel.innerHTML = rows.length
      ? rows.join("")
      : `<p class="none">Nothing matches “${esc(term)}”. Try a technique, like camera or speech, or a model name.</p>`;
    panel.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  const run = async () => {
    const term = input.value.trim();
    if (!term) return close();
    const orama = await load();
    const { hits } = await orama.search(db, {
      term,
      properties: ["title", "body", "tags", "video"],
      boost: { title: 3, tags: 2 },
      tolerance: term.length > 4 ? 1 : 0,
      limit: 8,
    });
    if (input.value.trim() === term) show(term, hits);
  };

  input.addEventListener("focus", () => load(), { once: true });
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 90);
  });
  // Enter opens the top result; there is no results page to submit to.
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const first = panel.querySelector("a");
    if (!panel.hidden && first) location.href = first.href;
  });
  form.addEventListener("keydown", (e) => {
    const links = [...panel.querySelectorAll("a")];
    const at = links.indexOf(document.activeElement);
    if (e.key === "Escape") {
      close();
      input.focus();
    } else if (e.key === "ArrowDown" && links.length) {
      e.preventDefault();
      links[Math.min(at + 1, links.length - 1)].focus();
    } else if (e.key === "ArrowUp" && at >= 0) {
      e.preventDefault();
      at === 0 ? input.focus() : links[at - 1].focus();
    }
  });
  document.addEventListener("click", (e) => {
    if (!form.contains(e.target)) close();
  });
});

// Prompt variants (As generated / Revised, one per model, ...)
document.querySelectorAll("[data-tabs]").forEach((root) => {
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  const select = (tab) => {
    tabs.forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
    });
  };
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(tab));
    tab.addEventListener("keydown", (e) => {
      const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      const next = tabs[(i + step + tabs.length) % tabs.length];
      select(next);
      next.focus();
    });
  });
});

// Copy copies exactly what the model was given: the text content of the visible prompt.
document.querySelectorAll("[data-copy]").forEach((btn) => {
  const label = btn.textContent;
  btn.addEventListener("click", async () => {
    const panel = [...document.querySelectorAll(".script")].find((el) => !el.closest("[hidden]"));
    if (!panel) return;
    try {
      await navigator.clipboard.writeText(panel.textContent);
      btn.textContent = "Copied";
    } catch {
      const range = document.createRange();
      range.selectNodeContents(panel);
      const sel = getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = "Selected, press Ctrl+C";
    }
    setTimeout(() => (btn.textContent = label), 2200);
  });
});

// Pointing at a <Picture 2> lights up every <Picture 2> in the prompt.
document.querySelectorAll(".script").forEach((script) => {
  const light = (tag, on) =>
    script.querySelectorAll(`.t[data-tag="${tag}"]`).forEach((el) => el.classList.toggle("lit", on));
  script.addEventListener("pointerover", (e) => {
    const t = e.target.closest(".t");
    if (t) light(t.dataset.tag, true);
  });
  script.addEventListener("pointerout", (e) => {
    const t = e.target.closest(".t");
    if (t) light(t.dataset.tag, false);
  });
});
