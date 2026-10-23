/* Triangle Family Weekend — renders data/events.json into ranked day sections.
 * Contract: data/events.json schema is defined in docs/plans/ (the ONLY interface
 * between the refresh pipeline and this frontend). Do not change field names
 * without updating the scraper and REFRESH.md together. */

const NEARBY_TOWNS = ["Holly Springs", "Apex", "Cary", "Fuquay-Varina", "Morrisville", "New Hill",
                      "Wake Forest", "Knightdale", "Garner"];

// Town centroids (lat,lng) for distance sorting — Triangle NC.
const TOWN_COORDS = {
  "Holly Springs": [35.651, -78.834], "Apex": [35.733, -78.851], "Cary": [35.791, -78.781],
  "Fuquay-Varina": [35.584, -78.800], "Morrisville": [35.823, -78.825], "New Hill": [35.678, -78.940],
  "Wake Forest": [35.980, -78.510], "Knightdale": [35.788, -78.480], "Garner": [35.711, -78.614],
  "Raleigh": [35.780, -78.639], "Durham": [35.994, -78.899], "Chapel Hill": [35.913, -79.056],
  "Carrboro": [35.910, -79.075], "Hillsborough": [36.075, -79.100], "Wendell": [35.781, -78.370],
  "Clayton": [35.650, -78.456], "Youngsville": [36.025, -78.474], "Pittsboro": [35.720, -79.177],
  "Sanford": [35.480, -79.180], "Zebulon": [35.824, -78.315],
};

let home = null; // {zip, lat, lng} once the user sets a ZIP

function haversineMi(a, b) {
  const R = 3958.8, rad = (d) => (d * Math.PI) / 180;
  const dLat = rad(b[0] - a[0]), dLng = rad(b[1] - a[1]);
  const h = Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

function eventDistanceMi(e) {
  if (!home) return null;
  let coords = TOWN_COORDS[e.city];
  if (!coords) {
    const hay = `${e.city || ""} ${e.venue || ""} ${e.title || ""}`.toLowerCase();
    for (const [town, c] of Object.entries(TOWN_COORDS)) {
      if (hay.includes(town.toLowerCase())) { coords = c; break; }
    }
  }
  return coords ? Math.round(haversineMi([home.lat, home.lng], coords)) : null;
}

async function geocodeZip(zip) {
  const res = await fetch(`https://api.zippopotam.us/us/${zip}`);
  if (!res.ok) throw new Error("ZIP not found");
  const data = await res.json();
  const place = data.places?.[0];
  if (!place) throw new Error("ZIP not found");
  return { zip, lat: parseFloat(place.latitude), lng: parseFloat(place.longitude) };
}

const FILTERS = {
  all: () => true,
  free: (e) => /free/i.test(e.cost || ""),
  outdoor: (e) => e.indoor === false,
  indoor: (e) => e.indoor === true,
  // With a ZIP set, "nearby" shows everything sorted by distance instead.
  nearby: (e) => home ? true : NEARBY_TOWNS.includes(e.city),
  gentle: (e) => !(e.tags || []).includes("scary") && !(e.tags || []).includes("21+"),
};

let allEvents = [];

async function loadEvents() {
  const res = await fetch("data/events.json");
  if (!res.ok) throw new Error(`events.json: ${res.status}`);
  return res.json();
}

function scoreBadge(score) {
  const top = score >= 85 ? " top" : "";
  return `<div class="score" title="Family-fit score">
    <span class="score-num${top}">${score}</span>
    <span class="score-label">family fit</span>
  </div>`;
}

function tagChip(tag) {
  const cls = tag === "free" ? " free" : tag === "scary" || tag === "21+" ? " caution" : "";
  return `<span class="tag${cls}">${escapeHtml(tag)}</span>`;
}

function cardHtml(e) {
  const time = e.end ? `${e.start}–${e.end}` : e.start || "All day";
  const place = [e.venue, e.city].filter(Boolean).join(", ");
  const link = e.url
    ? `<a class="event-link" href="${escapeAttr(e.url)}" target="_blank" rel="noopener">Details →</a>`
    : "";
  const dist = eventDistanceMi(e);
  const distChip = dist != null ? `<span class="tag distance">${dist} mi</span>` : "";
  return `<article class="card">
    ${scoreBadge(e.family_score)}
    <div class="card-body">
      <h3>${escapeHtml(e.title)}</h3>
      <p class="meta"><strong>${escapeHtml(time)}</strong>${place ? ` · ${escapeHtml(place)}` : ""}${e.cost ? ` · ${escapeHtml(e.cost)}` : ""}</p>
      ${e.why ? `<p class="why">${escapeHtml(e.why)}</p>` : ""}
      <div class="tags">${distChip}${(e.tags || []).map(tagChip).join("")}${link}</div>
    </div>
  </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const escapeAttr = escapeHtml;

function fmtDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

function render(filter = "all") {
  const match = FILTERS[filter] || FILTERS.all;
  let shown = 0;
  for (const day of ["fri", "sat", "sun"]) {
    const events = allEvents
      .filter((e) => (e.days || [e.day]).includes(day) && match(e))
      .sort((a, b) => {
        if (filter === "nearby" && home) {
          const da = eventDistanceMi(a) ?? 9999, db = eventDistanceMi(b) ?? 9999;
          if (da !== db) return da - db;
        }
        return b.family_score - a.family_score;
      });
    document.getElementById(`cards-${day}`).innerHTML = events.map(cardHtml).join("");
    shown += events.length;
  }
  document.getElementById("empty-state").hidden = shown > 0;
}

let activeFilter = "all";

function bindFilters() {
  document.getElementById("filters").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".chip");
    if (!btn || btn.classList.contains("zip-btn")) return;
    document.querySelectorAll(".chip").forEach((c) => {
      if (!c.classList.contains("zip-btn")) c.classList.toggle("is-active", c === btn);
    });
    activeFilter = btn.dataset.filter;
    render(activeFilter);
  });

  document.getElementById("zip-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = document.getElementById("zip-input");
    const status = document.getElementById("zip-status");
    const zip = input.value.trim();
    if (!/^\d{5}$/.test(zip)) {
      status.textContent = "Enter a 5-digit ZIP";
      status.classList.add("error");
      return;
    }
    status.textContent = "…";
    status.classList.remove("error");
    try {
      home = await geocodeZip(zip);
      localStorage.setItem("home", JSON.stringify(home));
      status.textContent = `Sorting from ${zip}`;
      // Jump straight to distance view — that's why they set it.
      document.querySelectorAll(".chip").forEach((c) => {
        if (!c.classList.contains("zip-btn"))
          c.classList.toggle("is-active", c.dataset.filter === "nearby");
      });
      activeFilter = "nearby";
      render("nearby");
    } catch {
      status.textContent = "ZIP not recognized";
      status.classList.add("error");
    }
  });
}

async function main() {
  try {
    const data = await loadEvents();
    allEvents = data.events || [];
    const wk = data.weekend || {};
    for (const day of ["fri", "sat", "sun"]) {
      if (wk[day]) document.getElementById(`date-${day}`).textContent = fmtDate(wk[day]);
    }
    if (data.generated_at) {
      const when = new Date(data.generated_at).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
      document.getElementById("updated-stamp").textContent = `Updated ${when} · ${allEvents.length} events`;
    }
    const saved = localStorage.getItem("home");
    if (saved) {
      try {
        home = JSON.parse(saved);
        document.getElementById("zip-input").value = home.zip;
        document.getElementById("zip-status").textContent = `Sorting from ${home.zip}`;
      } catch { localStorage.removeItem("home"); home = null; }
    }
    bindFilters();
    render();
  } catch (err) {
    document.getElementById("events-root").innerHTML =
      `<p class="empty-state">Couldn't load events (${escapeHtml(err.message)}). Check back soon.</p>`;
  }
}

main();
