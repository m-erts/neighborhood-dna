// The map explorer. Reads the GeoJSON that dna.py writes; nothing else.
// Every string that comes from a file goes into the page through textContent.
const CITIES = ["hiroshima", "belgrade", "amsterdam", "london"];
const NS = "http://www.w3.org/2000/svg";
const $ = (selector) => document.querySelector(selector);
const map = $("[data-map]");
const tip = $(".tip");
const state = { mode: "share", city: null, data: null, picked: null, taxonomy: null };

function el(tag, attributes = {}, text) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}
const title = (key) => key.charAt(0).toUpperCase() + key.slice(1);
const percent = (share) => `${Math.round(share * 100)}%`;
const branch = (key) => state.taxonomy.branches[key] || { label: key.replaceAll("_", " "), colour: "#64748B" };
const shade = (share) => state.taxonomy.ramp.find((step) => share < step.below).colour;

function notice(message) {
  const box = $("[data-notice]");
  box.textContent = message || "";
  box.hidden = !message;
}

// A GeoJSON from dna.py, checked before anything is drawn.
function valid(data) {
  if (!data || data.type !== "FeatureCollection" || !Array.isArray(data.features)) return false;
  if (data.features.length === 0 || data.features.length > 20000) return false;
  return data.features.every((feature) => {
    const p = feature.properties, g = feature.geometry;
    return p && g && g.type === "Polygon" && Array.isArray(g.coordinates?.[0])
      && typeof p.top_share === "number" && typeof p.poi === "number"
      && p.dna && typeof p.dna === "object" && typeof p.h3 === "string";
  });
}

function draw() {
  const features = state.data.features;
  const rings = features.map((feature) => feature.geometry.coordinates[0]);
  const lons = rings.flat().map((point) => point[0]);
  const lats = rings.flat().map((point) => point[1]);
  const [west, east] = [Math.min(...lons), Math.max(...lons)];
  const [south, north] = [Math.min(...lats), Math.max(...lats)];
  const kx = 111.32 * Math.cos(((south + north) / 2) * Math.PI / 180), ky = 110.574;
  const width = (east - west) * kx, height = (north - south) * ky;   // kilometres
  map.setAttribute("viewBox", `${-width * 0.02} ${-height * 0.02} ${width * 1.04} ${height * 1.04}`);
  map.setAttribute("aria-label", `${features.length} H3 cells of ${state.city}`);
  const cells = document.createDocumentFragment(), flagged = document.createDocumentFragment();
  features.forEach((feature, index) => {
    const points = rings[index].slice(0, -1)
      .map(([lon, lat]) => `${((lon - west) * kx).toFixed(3)},${((north - lat) * ky).toFixed(3)}`).join(" ");
    const p = feature.properties;
    const polygon = document.createElementNS(NS, "polygon");
    polygon.setAttribute("points", points);
    polygon.setAttribute("fill", state.mode === "share" ? shade(p.top_share) : branch(p.dominant).colour);
    polygon.dataset.index = index;
    cells.append(polygon);
    if (p.flagged ?? p.top_share >= 0.5) {
      const ring = document.createElementNS(NS, "polygon");
      ring.setAttribute("points", points);
      ring.setAttribute("class", "ring");
      ring.setAttribute("vector-effect", "non-scaling-stroke");
      flagged.append(ring);
    }
  });
  map.replaceChildren(cells, flagged);
  if (state.picked !== null) pick(state.picked);
  legend();
}

function legend() {
  const box = $("[data-legend]");
  const items = [];
  if (state.mode === "share") {
    for (const step of state.taxonomy.ramp) items.push([step.colour, `top share ${step.label}`]);
  } else {
    const present = new Set(state.data.features.map((f) => f.properties.dominant));
    for (const [key, item] of Object.entries(state.taxonomy.branches)) {
      if (present.has(key)) items.push([item.colour, item.label]);
    }
  }
  box.replaceChildren(...items.map(([colour, text]) => {
    const item = el("span");
    const swatch = el("i");
    swatch.style.background = colour;
    item.append(swatch, document.createTextNode(text));
    return item;
  }));
  const flag = el("span");
  flag.append(el("i", { class: "ring" }), document.createTextNode("flagged: one function holds half the places"));
  box.append(flag);
}

function facts(target, pairs) {
  target.replaceChildren(...pairs.map(([name, value, flag]) => {
    const item = el("div");
    const shown = String(value);
    const kind = [flag ? "flag" : "", shown.length > 8 ? "long" : ""].join(" ").trim();
    item.append(el("dt", {}, name), el("dd", kind ? { class: kind } : {}, shown));
    return item;
  }));
}

function cityPanel() {
  const cells = state.data.features.map((f) => f.properties);
  const meta = state.data.metadata || {};
  const sorted = cells.map((c) => c.hill_q2).sort((a, b) => a - b);
  $("[data-city-title]").textContent = title(state.city);
  facts($("[data-city-facts]"), [
    ["cells", cells.length.toLocaleString("en")],
    ["places", cells.reduce((sum, c) => sum + c.poi, 0).toLocaleString("en")],
    ["flagged", cells.filter((c) => c.flagged ?? c.top_share >= 0.5).length],
    ["median Hill q2", sorted[Math.floor(sorted.length / 2)].toFixed(2)],
    ["taxonomy level", meta.taxonomy_level ?? "?"],
    ["release", String(meta.source ?? "?").split("/").pop().slice(0, 14)],
  ]);
  const bars = el("div", { class: "bars" });
  for (const [name, share] of Object.entries(meta.providers_pct || {})) {
    if (share < 0.05) continue;
    const row = el("div");
    const track = el("b");
    const fill = el("i");
    fill.style.width = `${Math.min(100, share)}%`;
    track.append(fill);
    row.append(el("span", {}, name), track, el("span", {}, share.toFixed(1)));
    bars.append(row);
  }
  $("[data-providers]").replaceChildren(bars);

  const flaggedCells = state.data.features
    .map((feature, index) => ({ p: feature.properties, index }))
    .filter(({ p }) => p.flagged ?? p.top_share >= 0.5)
    .sort((a, b) => b.p.top_share - a.p.top_share);
  const list = $("[data-shortlist]");
  if (flaggedCells.length === 0) {
    list.replaceChildren(el("li", { class: "empty" }, "No cell in this file reaches a top share of 0.5."));
    return;
  }
  list.replaceChildren(...flaggedCells.map(({ p, index }) => {
    const item = el("li");
    const button = el("button", { type: "button" });
    button.append(el("span", {}, branch(p.dominant).label), el("span", {}, p.top_share.toFixed(2)),
      el("span", {}, `${p.poi.toLocaleString("en")} places`));
    button.addEventListener("click", () => pick(index));
    item.append(button);
    return item;
  }));
}

function pick(index) {
  state.picked = index;
  map.querySelectorAll(".picked").forEach((node) => node.remove());
  const cell = map.querySelector(`polygon[data-index="${index}"]`);
  for (const layer of cell ? ["picked casing", "picked"] : []) {
    const mark = document.createElementNS(NS, "polygon");   // drawn last: nothing covers it
    mark.setAttribute("points", cell.getAttribute("points"));
    mark.setAttribute("class", layer);
    map.append(mark);
  }
  const p = state.data.features[index].properties;
  const box = $("[data-cell]");
  const heading = el("h2", {}, `${branch(p.dominant).label} leads with ${percent(p.top_share)}`);
  const id = el("p", { class: "id" }, `H3 cell ${p.h3}`);
  const numbers = el("dl", { class: "facts" });
  facts(numbers, [
    ["places", p.poi.toLocaleString("en")],
    ["Hill q1", p.hill_q1.toFixed(2)],
    ["Hill q2", p.hill_q2.toFixed(2)],
    ["top share", p.top_share.toFixed(2), p.flagged ?? p.top_share >= 0.5],
    ["categories", p.richness ?? Object.keys(p.dna).length],
    ["HDBSCAN", p.cluster === undefined ? "?" : p.cluster < 0 ? "noise" : `cluster ${p.cluster}`],
  ]);
  const bar = el("div", { class: "dna", role: "img", "aria-label": "Share of places by function" });
  const order = Object.keys(state.taxonomy.branches);
  const keys = Object.keys(p.dna).sort((a, b) => (order.indexOf(a) + 99) % 99 - (order.indexOf(b) + 99) % 99);
  for (const key of keys) {
    const part = el("span", { title: `${branch(key).label} ${percent(p.dna[key])}` });
    part.style.flex = String(p.dna[key]);
    part.style.background = branch(key).colour;
    bar.append(part);
  }
  const table = el("table", { class: "shares" });
  const head = el("tr");
  head.append(el("th", {}, "function"), el("th", {}, "share"), el("th", {}, "tf-idf"));
  table.append(head);
  for (const [key, share] of Object.entries(p.dna)) {
    const row = el("tr");
    const name = el("td");
    const swatch = el("i");
    swatch.style.background = branch(key).colour;
    name.append(swatch, document.createTextNode(branch(key).label));
    row.append(name, el("td", {}, percent(share)), el("td", {}, (p.tfidf?.[key] ?? 0).toFixed(3)));
    table.append(row);
  }
  box.replaceChildren(heading, id, numbers, bar, table);
  $(".panel").scrollTo({ top: 0 });
  if (window.matchMedia("(max-width: 900px)").matches) box.scrollIntoView({ block: "start" });
}

function show(data, name) {
  state.data = data;
  state.city = name;
  state.picked = null;
  document.querySelectorAll("[data-city]").forEach((button) =>
    button.setAttribute("aria-pressed", String(button.dataset.city === name)));
  const box = $("[data-cell]");
  box.replaceChildren(el("h2", {}, "Pick a cell"),
    el("p", { class: "hint" }, "Click a hexagon, or a row of the shortlist below, to read its DNA."));
  draw();
  cityPanel();
}

async function load(city) {
  try {
    const response = await fetch(`data/${city}.geojson`);
    if (!response.ok) throw new Error(response.status);
    notice("");
    show(await response.json(), city);
  } catch {
    notice("The sample cities load over http only. Run `make serve` in the repository, or open a GeoJSON written by dna.py with the button above.");
  }
}

function open(file) {
  const reader = new FileReader();
  reader.addEventListener("load", () => {
    try {
      const data = JSON.parse(reader.result);
      if (!valid(data)) throw new Error("shape");
      notice("");
      show(data, file.name.replace(/\.(geo)?json$/i, "").slice(0, 40));
    } catch {
      notice("That file is not a GeoJSON written by dna.py: every feature needs a polygon and the properties h3, poi, top_share and dna.");
    }
  });
  reader.readAsText(file);
}

map.addEventListener("click", (event) => {
  const index = event.target.dataset?.index;
  if (index !== undefined) pick(Number(index));
});
map.addEventListener("pointermove", (event) => {
  const index = event.target.dataset?.index;
  if (index === undefined) { tip.hidden = true; return; }
  const p = state.data.features[Number(index)].properties;
  tip.textContent = `${branch(p.dominant).label} ${percent(p.top_share)}\n${p.poi.toLocaleString("en")} places, Hill q2 ${p.hill_q2.toFixed(2)}`;
  tip.hidden = false;
  const box = tip.getBoundingClientRect();
  const x = Math.min(event.clientX + 14, window.innerWidth - box.width - 14);
  const y = Math.min(event.clientY + 14, window.innerHeight - box.height - 14);
  tip.style.transform = `translate(${x}px, ${y}px)`;
});
map.addEventListener("pointerleave", () => { tip.hidden = true; });

document.querySelectorAll("[data-mode]").forEach((button) => button.addEventListener("click", () => {
  state.mode = button.dataset.mode;
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
  if (state.data) draw();
}));
$("[data-file]").addEventListener("change", (event) => event.target.files[0] && open(event.target.files[0]));
const zone = $(".map");
zone.addEventListener("dragover", (event) => { event.preventDefault(); zone.classList.add("is-over"); });
zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
zone.addEventListener("drop", (event) => {
  event.preventDefault();
  zone.classList.remove("is-over");
  if (event.dataTransfer.files[0]) open(event.dataTransfer.files[0]);
});

// Colours and the order of the functions are shared with the figures: docs/data/taxonomy.json.
const FALLBACK = { clusters: [], ramp: [
  { below: 0.25, colour: "#0C4A6E", label: "under 0.25" }, { below: 0.3, colour: "#0369A1", label: "0.25 to 0.30" },
  { below: 0.4, colour: "#0EA5E9", label: "0.30 to 0.40" }, { below: 0.5, colour: "#38BDF8", label: "0.40 to 0.50" },
  { below: 9, colour: "#BAE6FD", label: "0.50 and over" }] };
(async () => {
  let taxonomy = FALLBACK;
  try {
    const response = await fetch("data/taxonomy.json");
    if (response.ok) taxonomy = await response.json();
  } catch { /* file://: the fallback ramp is enough to draw a dropped file */ }
  state.taxonomy = { ramp: taxonomy.ramp, branches: Object.fromEntries(
    taxonomy.clusters.flatMap((cluster) => cluster.branches.map((b) => [b.key, b]))) };
  $("[data-cities]").replaceChildren(...CITIES.map((city) => {
    const button = el("button", { type: "button", "data-city": city, "aria-pressed": "false" }, title(city));
    button.addEventListener("click", () => load(city));
    return button;
  }));
  const wanted = new URLSearchParams(location.search).get("city");
  load(CITIES.includes(wanted) ? wanted : "hiroshima");
})();
