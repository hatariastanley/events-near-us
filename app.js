/* Triangle Family Weekend — renders data/events.json into ranked day sections.
 * Contract: data/events.json schema is defined in docs/plans/ (the ONLY interface
 * between the refresh pipeline and this frontend). Do not change field names
 * without updating the scraper and REFRESH.md together. */

const NEARBY_TOWNS = ["Holly Springs", "Apex", "Cary", "Fuquay-Varina", "Morrisville", "New Hill"];

const FILTERS = {
  all: () => true,
  free: (e) => /free/i.test(e.cost || ""),
  outdoor: (e) => e.indoor === false,
  indoor: (e) => e.indoor === true,
  nearby: (e) => NEARBY_TOWNS.includes(e.city),
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
  return `<article class="card">
    ${scoreBadge(e.family_score)}
    <div class="card-body">
      <h3>${escapeHtml(e.title)}</h3>
      <p class="meta"><strong>${escapeHtml(time)}</strong>${place ? ` · ${escapeHtml(place)}` : ""}${e.cost ? ` · ${escapeHtml(e.cost)}` : ""}</p>
      <p class="why">${escapeHtml(e.why)}</p>
      <div class="tags">${(e.tags || []).map(tagChip).join("")}${link}</div>
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
      .sort((a, b) => b.family_score - a.family_score);
    document.getElementById(`cards-${day}`).innerHTML = events.map(cardHtml).join("");
    shown += events.length;
  }
  document.getElementById("empty-state").hidden = shown > 0;
}

function bindFilters() {
  document.getElementById("filters").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".chip");
    if (!btn) return;
    document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("is-active", c === btn));
    render(btn.dataset.filter);
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
    bindFilters();
    render();
  } catch (err) {
    document.getElementById("events-root").innerHTML =
      `<p class="empty-state">Couldn't load events (${escapeHtml(err.message)}). Check back soon.</p>`;
  }
}

main();
