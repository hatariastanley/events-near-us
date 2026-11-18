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
  // With a ZIP set, "nearby" shows all events; distance breaks score ties.
  nearby: (e) => home ? true : NEARBY_TOWNS.includes(e.city),
  gentle: (e) => !(e.tags || []).includes("scary") && !(e.tags || []).includes("21+"),
};

let allEvents = [];
let woodcreekData = null;

async function loadEvents() {
  const res = await fetch("data/events.json");
  if (!res.ok) throw new Error(`events.json: ${res.status}`);
  return res.json();
}

async function loadWoodcreekEvents() {
  const res = await fetch("data/woodcreek_events.json");
  if (!res.ok) throw new Error(`woodcreek_events.json: ${res.status}`);
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

function cardHtml(e, dateStr, showDate = false) {
  const time = e.end ? `${e.start}–${e.end}` : e.start || "All day";
  const place = [e.venue, e.city].filter(Boolean).join(", ");
  const link = e.url
    ? `<a class="event-link" href="${escapeAttr(e.url)}" target="_blank" rel="noopener">Details →</a>`
    : "";
  const dist = eventDistanceMi(e);
  const distChip = dist != null ? `<span class="tag distance">${dist} mi</span>` : "";
  const evtKey = `${e.id}-${dateStr}`;
  window._evtMap[evtKey] = e;
  const dateLabel = showDate && dateStr ? `${escapeHtml(fmtCardDate(dateStr))} · ` : "";
  return `<article class="card">
    ${scoreBadge(e.family_score)}
    <div class="card-body">
      <h3>${escapeHtml(e.title)}</h3>
      <p class="meta">${dateLabel}<strong>${escapeHtml(time)}</strong>${place ? ` · ${escapeHtml(place)}` : ""}${e.cost ? ` · ${escapeHtml(e.cost)}` : ""}</p>
      ${e.why ? `<p class="why">${escapeHtml(e.why)}</p>` : ""}
      <div class="tags">${distChip}${(e.tags || []).map(tagChip).join("")}${link}</div>
      ${calendarLinks(e, dateStr)}
    </div>
  </article>`;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const escapeAttr = escapeHtml;

function parseTime(timeStr) {
  if (!timeStr) return null;
  const m = timeStr.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)?/i);
  if (!m) return null;
  let h = parseInt(m[1], 10);
  const min = m[2] ? parseInt(m[2], 10) : 0;
  const ampm = (m[3] || "").toLowerCase();
  if (ampm === "pm" && h < 12) h += 12;
  if (ampm === "am" && h === 12) h = 0;
  return { h, min };
}

function toIcsDateTime(dateStr, timeStr, allDay = false) {
  const d = new Date(dateStr + "T12:00:00");
  if (allDay) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}${m}${day}`;
  }
  const t = parseTime(timeStr);
  if (!t) return null;
  d.setHours(t.h, t.min, 0, 0);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hr = String(t.h).padStart(2, "0");
  const mi = String(t.min).padStart(2, "0");
  return `${y}${mo}${day}T${hr}${mi}00`;
}

function toGcalDateTime(dateStr, timeStr) {
  const d = new Date(dateStr + "T12:00:00");
  const t = parseTime(timeStr);
  if (!t) return null;
  d.setHours(t.h, t.min, 0, 0);
  const y = d.getFullYear();
  const mo = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hr = String(t.h).padStart(2, "0");
  const mi = String(t.min).padStart(2, "0");
  return `${y}${mo}${day}T${hr}${mi}00`;
}

function addHours(dateTimeStr, hours) {
  const y = parseInt(dateTimeStr.slice(0, 4), 10);
  const mo = parseInt(dateTimeStr.slice(4, 6), 10) - 1;
  const d = parseInt(dateTimeStr.slice(6, 8), 10);
  const h = parseInt(dateTimeStr.slice(9, 11), 10);
  const mi = parseInt(dateTimeStr.slice(11, 13), 10);
  const dt = new Date(y, mo, d, h + hours, mi);
  const ny = dt.getFullYear();
  const nm = String(dt.getMonth() + 1).padStart(2, "0");
  const nd = String(dt.getDate()).padStart(2, "0");
  const nh = String(dt.getHours()).padStart(2, "0");
  const nmi = String(dt.getMinutes()).padStart(2, "0");
  return `${ny}${nm}${nd}T${nh}${nmi}00`;
}

function buildGoogleCalUrl(event, dateStr) {
  const title = event.title || "Event";
  const location = [event.venue, event.city].filter(Boolean).join(", ");
  const description = [event.why || event.description || "", event.url ? `Details: ${event.url}` : ""].filter(Boolean).join("\n\n");
  
  let dates;
  const startTime = event.start;
  const endTime = event.end;
  const isAllDay = !startTime || /all\s*day/i.test(startTime);
  
  if (isAllDay) {
    const d = new Date(dateStr + "T12:00:00");
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const nextDay = new Date(d.getTime() + 86400000);
    const ny = nextDay.getFullYear();
    const nm = String(nextDay.getMonth() + 1).padStart(2, "0");
    const nd = String(nextDay.getDate()).padStart(2, "0");
    dates = `${y}${m}${day}/${ny}${nm}${nd}`;
  } else {
    const start = toGcalDateTime(dateStr, startTime);
    if (!start) return null;
    let end;
    if (endTime && parseTime(endTime)) {
      end = toGcalDateTime(dateStr, endTime);
    } else {
      end = addHours(start, 2);
    }
    dates = `${start}/${end}`;
  }
  
  const params = new URLSearchParams({
    action: "TEMPLATE",
    text: title,
    dates: dates,
    location: location,
    details: description,
    ctz: "America/New_York"
  });
  return `https://calendar.google.com/calendar/render?${params.toString()}`;
}

function buildIcsContent(event, dateStr) {
  const title = event.title || "Event";
  const location = [event.venue, event.city].filter(Boolean).join(", ");
  const description = [event.why || event.description || "", event.url ? `Details: ${event.url}` : ""].filter(Boolean).join("\\n\\n");
  const uid = `${event.id || Math.random().toString(36).slice(2)}-${dateStr}@trianglefamilyweekend`;
  
  const startTime = event.start;
  const endTime = event.end;
  const isAllDay = !startTime || /all\s*day/i.test(startTime);
  
  let dtstart, dtend;
  if (isAllDay) {
    dtstart = `DTSTART;VALUE=DATE:${toIcsDateTime(dateStr, null, true)}`;
    const nextDay = new Date(new Date(dateStr + "T12:00:00").getTime() + 86400000);
    const ny = nextDay.getFullYear();
    const nm = String(nextDay.getMonth() + 1).padStart(2, "0");
    const nd = String(nextDay.getDate()).padStart(2, "0");
    dtend = `DTEND;VALUE=DATE:${ny}${nm}${nd}`;
  } else {
    const start = toIcsDateTime(dateStr, startTime);
    if (!start) return null;
    let end;
    if (endTime && parseTime(endTime)) {
      end = toIcsDateTime(dateStr, endTime);
    } else {
      end = addHours(start, 2);
    }
    dtstart = `DTSTART;TZID=America/New_York:${start}`;
    dtend = `DTEND;TZID=America/New_York:${end}`;
  }
  
  const now = new Date();
  const stamp = `${now.getUTCFullYear()}${String(now.getUTCMonth() + 1).padStart(2, "0")}${String(now.getUTCDate()).padStart(2, "0")}T${String(now.getUTCHours()).padStart(2, "0")}${String(now.getUTCMinutes()).padStart(2, "0")}${String(now.getUTCSeconds()).padStart(2, "0")}Z`;
  
  return `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Triangle Family Weekend//EN
BEGIN:VEVENT
UID:${uid}
DTSTAMP:${stamp}
${dtstart}
${dtend}
SUMMARY:${title.replace(/[,;]/g, "\\$&")}
LOCATION:${location.replace(/[,;]/g, "\\$&")}
DESCRIPTION:${description.replace(/[,;]/g, "\\$&")}
END:VEVENT
END:VCALENDAR`;
}

function downloadIcs(event, dateStr) {
  const ics = buildIcsContent(event, dateStr);
  if (!ics) return;
  const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${(event.title || "event").replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function calendarLinks(event, dateStr) {
  const gcalUrl = buildGoogleCalUrl(event, dateStr);
  if (!gcalUrl) return "";
  return `<div class="cal-links">
    <a href="${escapeAttr(gcalUrl)}" target="_blank" rel="noopener" class="cal-btn gcal" title="Add to Google Calendar">📅 Google</a>
    <button type="button" class="cal-btn ics" onclick="downloadIcs(window._evtMap['${event.id}-${dateStr}'], '${dateStr}')" title="Download .ics for Apple/Outlook">📥 .ics</button>
  </div>`;
}

window._evtMap = {};

function fmtDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "long", day: "numeric" });
}

function fmtCardDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

function fmtWeekRange(startDate) {
  const end = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate() + 6);
  const startMonth = startDate.toLocaleDateString("en-US", { month: "short" });
  const endMonth = end.toLocaleDateString("en-US", { month: "short" });
  if (startMonth === endMonth) {
    return `${startMonth} ${startDate.getDate()}–${end.getDate()}`;
  }
  return `${startMonth} ${startDate.getDate()} – ${endMonth} ${end.getDate()}`;
}

const WEEKEND_COUNT = 6;

function fmtShortDate(iso) {
  return new Date(iso + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function addDaysISO(iso, days) {
  const d = new Date(iso + "T12:00:00");
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function weekendForOffset(offset) {
  if (!weekendDates.fri) return {};
  if (offset === 0) return weekendDates;
  const fri = weekendDates.fri;
  const sat = weekendDates.sat || addDaysISO(fri, 1);
  const sun = weekendDates.sun || addDaysISO(fri, 2);
  const shift = offset * 7;
  return { fri: addDaysISO(fri, shift), sat: addDaysISO(sat, shift), sun: addDaysISO(sun, shift) };
}

function weekendOptionLabel(offset, dates) {
  const start = new Date(dates.fri + "T12:00:00");
  const end = new Date(dates.sun + "T12:00:00");
  const startMonth = start.toLocaleDateString("en-US", { month: "short" });
  const endMonth = end.toLocaleDateString("en-US", { month: "short" });
  const range = startMonth === endMonth && start.getFullYear() === end.getFullYear()
    ? `${startMonth} ${start.getDate()}–${end.getDate()}`
    : `${fmtShortDate(dates.fri)}–${fmtShortDate(dates.sun)}`;
  if (offset === 0) return `This weekend · ${range}`;
  if (offset === 1) return `Next weekend · ${range}`;
  return `Weekend of ${range}`;
}

function sortEventsForFilter(events, filter) {
  return events.sort((a, b) => {
    if (b.family_score !== a.family_score) return b.family_score - a.family_score;
    if (filter === "nearby" && home) {
      return (eventDistanceMi(a) ?? 9999) - (eventDistanceMi(b) ?? 9999);
    }
    return 0;
  });
}

let weekendDates = {};
let activeWeekend = 0;

function render(filter = "all") {
  const match = FILTERS[filter] || FILTERS.all;
  let shown = 0;
  for (const day of ["fri", "sat", "sun"]) {
    const dateStr = weekendDates[day] || "";
    const events = allEvents
      .filter((e) => (e.days || [e.day]).includes(day) && match(e));
    sortEventsForFilter(events, filter);
    document.getElementById(`cards-${day}`).innerHTML = events.map((e) => cardHtml(e, dateStr)).join("");
    shown += events.length;
  }
  document.getElementById("empty-state").hidden = shown > 0;
}

function renderWeekend(offset, filter = "all") {
  if (offset === 0) {
    restoreWeekendView(weekendDates);
    render(filter);
    return;
  }

  const dates = weekendForOffset(offset);
  restoreWeekendView(dates);
  const match = FILTERS[filter] || FILTERS.all;
  let shown = 0;
  for (const day of ["fri", "sat", "sun"]) {
    const dateStr = dates[day] || "";
    const events = allEvents.filter((e) => e.date === dateStr && match(e));
    sortEventsForFilter(events, filter);
    document.getElementById(`cards-${day}`).innerHTML = events.map((e) => cardHtml(e, dateStr)).join("");
    shown += events.length;
  }
  const empty = document.getElementById("empty-state");
  empty.textContent = `No events found for ${weekendOptionLabel(offset, dates)}.`;
  empty.hidden = shown > 0;
}

let activeFilter = "all";
let activeTab = "weekend";

function fmtFullDate(iso) {
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });
}

function woodcreekCardHtml(e) {
  const time = e.end ? `${e.start}–${e.end}` : e.start || "";
  const dateStrDisplay = fmtFullDate(e.date);
  const evtKey = `${e.id}-${e.date}`;
  window._evtMap[evtKey] = e;
  return `<article class="card woodcreek-card">
    <div class="card-body">
      <h3>${escapeHtml(e.title)}</h3>
      <p class="meta"><strong>${escapeHtml(dateStrDisplay)}</strong>${time ? ` · ${escapeHtml(time)}` : ""}${e.venue ? ` · ${escapeHtml(e.venue)}` : ""}${e.cost ? ` · ${escapeHtml(e.cost)}` : ""}</p>
      ${e.description ? `<p class="description">${escapeHtml(e.description)}</p>` : ""}
      ${calendarLinks(e, e.date)}
    </div>
  </article>`;
}

function renderWoodcreek() {
  if (!woodcreekData) return;
  const allWcEvents = woodcreekData.events || [];
  const container = document.getElementById("woodcreek-cards");
  const sourceEl = document.getElementById("woodcreek-source");
  const emptyEl = document.getElementById("woodcreek-empty");

  if (woodcreekData.source_info) {
    const info = woodcreekData.source_info;
    sourceEl.textContent = `Source: ${info.source_name || "Woodcreek Newsletter"} (${info.organizer || "Woodcreek HOA"})`;
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const upcomingEvents = allWcEvents.filter((e) => {
    if (!e.date) return false;
    const eventDate = new Date(e.date + "T23:59:59");
    return eventDate >= today;
  });

  if (upcomingEvents.length === 0) {
    container.innerHTML = "";
    emptyEl.hidden = false;
  } else {
    const sorted = [...upcomingEvents].sort((a, b) => new Date(a.date) - new Date(b.date));
    container.innerHTML = sorted.map(woodcreekCardHtml).join("");
    emptyEl.hidden = true;
  }
}

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("is-active", t.dataset.tab === tab);
  });

  const weekendRoot = document.getElementById("events-root");
  const woodcreekRoot = document.getElementById("woodcreek-root");
  const filters = document.getElementById("filters");
  const rangeSelector = document.getElementById("range-selector");

  if (tab === "weekend") {
    weekendRoot.hidden = false;
    woodcreekRoot.hidden = true;
    filters.hidden = false;
    rangeSelector.hidden = false;
    renderWeekend(activeWeekend, activeFilter);
  } else if (tab === "woodcreek") {
    weekendRoot.hidden = true;
    woodcreekRoot.hidden = false;
    filters.hidden = true;
    rangeSelector.hidden = true;
    renderWoodcreek();
  }
}

function restoreWeekendView(dates = weekendDates) {
  const container = document.getElementById("events-root");
  container.innerHTML = `
    <section class="day-section" data-day="fri" aria-labelledby="day-fri">
      <h2 id="day-fri"><span class="day-name">Friday</span><span class="day-date" id="date-fri">${fmtDate(dates.fri || "")}</span></h2>
      <div class="cards" id="cards-fri"></div>
    </section>
    <section class="day-section" data-day="sat" aria-labelledby="day-sat">
      <h2 id="day-sat"><span class="day-name">Saturday</span><span class="day-date" id="date-sat">${fmtDate(dates.sat || "")}</span></h2>
      <div class="cards" id="cards-sat"></div>
    </section>
    <section class="day-section" data-day="sun" aria-labelledby="day-sun">
      <h2 id="day-sun"><span class="day-name">Sunday</span><span class="day-date" id="date-sun">${fmtDate(dates.sun || "")}</span></h2>
      <div class="cards" id="cards-sun"></div>
    </section>
    <p class="empty-state" id="empty-state" hidden>No events match those filters this weekend.</p>
  `;
}

function bindTabs() {
  document.getElementById("tabs").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".tab");
    if (!btn) return;
    switchTab(btn.dataset.tab);
  });
}

function populateWeekendSelect() {
  const select = document.getElementById("range-select");
  if (!select) return;
  select.innerHTML = "";
  for (let i = 0; i < WEEKEND_COUNT; i++) {
    const dates = weekendForOffset(i);
    const option = document.createElement("option");
    option.value = String(i);
    option.textContent = weekendOptionLabel(i, dates);
    select.appendChild(option);
  }
  select.value = String(activeWeekend);
}

function bindRangeSelector() {
  const select = document.getElementById("range-select");
  select.addEventListener("change", () => {
    activeWeekend = parseInt(select.value, 10) || 0;
    renderWeekend(activeWeekend, activeFilter);
  });
}

function bindFilters() {
  document.getElementById("filters").addEventListener("click", (ev) => {
    const btn = ev.target.closest(".chip");
    if (!btn || btn.classList.contains("zip-btn")) return;
    document.querySelectorAll(".chip").forEach((c) => {
      if (!c.classList.contains("zip-btn")) c.classList.toggle("is-active", c === btn);
    });
    activeFilter = btn.dataset.filter;
    renderWeekend(activeWeekend, activeFilter);
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
      renderWeekend(activeWeekend, "nearby");
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
    weekendDates = wk;
    for (const day of ["fri", "sat", "sun"]) {
      if (wk[day]) document.getElementById(`date-${day}`).textContent = fmtDate(wk[day]);
    }
    populateWeekendSelect();
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

    try {
      woodcreekData = await loadWoodcreekEvents();
    } catch {
      woodcreekData = { events: [] };
    }

    bindTabs();
    bindRangeSelector();
    bindFilters();
    renderWeekend(activeWeekend, activeFilter);
  } catch (err) {
    document.getElementById("events-root").innerHTML =
      `<p class="empty-state">Couldn't load events (${escapeHtml(err.message)}). Check back soon.</p>`;
  }
}

main();
