// Slides: keyboard, hash routing, scale to fit, figures with hover, the typed command.
const slides = [...document.querySelectorAll(".slide")];
const count = document.querySelector("[data-count]");
const label = document.querySelector("[data-status]");
const flow = window.matchMedia("(max-width: 820px)");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let current = 0;

function fit() {
  const room = window.innerHeight - 34;   // the status line keeps its height
  const scale = Math.min(window.innerWidth / 1280, room / 720);
  document.documentElement.style.setProperty("--fit", flow.matches ? 1 : scale.toFixed(4));
  document.querySelector(".deck").style.bottom = flow.matches ? "" : "34px";
}

function show(index, push = true) {
  current = Math.max(0, Math.min(slides.length - 1, index));
  slides.forEach((slide, i) => slide.classList.toggle("is-current", i === current));
  count.textContent = `${String(current + 1).padStart(2, "0")}/${String(slides.length).padStart(2, "0")}`;
  label.textContent = slides[current].dataset.label;
  document.title = `${slides[current].dataset.label} · Neighborhood DNA`;
  if (push) history.replaceState(null, "", `#${current + 1}`);
  if (flow.matches) slides[current].scrollIntoView({ block: "start" });
}

function fromHash() {
  const wanted = parseInt(location.hash.slice(1), 10);
  show(Number.isFinite(wanted) ? wanted - 1 : 0, false);
}

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  if (event.target.closest("pre, input, textarea")) return;   // arrows scroll the code
  const keys = { ArrowRight: 1, PageDown: 1, " ": 1, ArrowLeft: -1, PageUp: -1 };
  if (event.key in keys && !flow.matches) { event.preventDefault(); show(current + keys[event.key]); }
  if (event.key === "Home") show(0);
  if (event.key === "End") show(slides.length - 1);
  if (event.key === "f") document.documentElement.requestFullscreen?.();
});
document.querySelector("[data-prev]").addEventListener("click", () => show(current - 1));
document.querySelector("[data-next]").addEventListener("click", () => show(current + 1));

let startX = null;
document.addEventListener("touchstart", (e) => { startX = e.touches[0].clientX; }, { passive: true });
document.addEventListener("touchend", (e) => {
  if (startX === null || flow.matches) return;
  const moved = e.changedTouches[0].clientX - startX;
  if (Math.abs(moved) > 60) show(current + (moved < 0 ? 1 : -1));
  startX = null;
});

window.addEventListener("resize", fit);
window.addEventListener("hashchange", fromHash);
flow.addEventListener("change", () => { fit(); show(current, false); });

// Figures arrive as <img>. Over http they are swapped for inline SVG so that every
// mark can answer the pointer; from file:// the image simply stays.
const tip = document.querySelector(".tip");
function place(event) {
  const pad = 14;
  const box = tip.getBoundingClientRect();
  const x = Math.min(event.clientX + pad, window.innerWidth - box.width - pad);
  const y = Math.min(event.clientY + pad, window.innerHeight - box.height - pad);
  tip.style.transform = `translate(${Math.max(pad, x)}px, ${Math.max(pad, y)}px)`;
}
async function inline(figure) {
  try {
    const response = await fetch(figure.dataset.svg);
    if (!response.ok) return;
    const parsed = new DOMParser().parseFromString(await response.text(), "image/svg+xml");
    const svg = parsed.documentElement;
    if (svg.nodeName !== "svg") return;
    svg.querySelectorAll("script, foreignObject").forEach((node) => node.remove());
    svg.setAttribute("aria-label", figure.querySelector("img").alt);
    svg.querySelectorAll("rect > title, circle > title, path > title, polygon > title").forEach((title) => {
      const mark = title.parentNode;
      mark.dataset.tip = title.textContent;
      mark.setAttribute("tabindex", "0");
      mark.setAttribute("aria-label", title.textContent);
      title.remove();
    });
    figure.replaceChildren(document.importNode(svg, true));
  } catch { /* offline or file://: keep the image */ }
}
document.addEventListener("pointermove", (event) => {
  const mark = event.target.closest?.("[data-tip]");
  if (!mark) { tip.hidden = true; return; }
  tip.textContent = mark.dataset.tip;
  tip.hidden = false;
  place(event);
});
document.addEventListener("focusin", (event) => {
  const mark = event.target.closest?.("[data-tip]");
  if (!mark) { tip.hidden = true; return; }
  const box = mark.getBoundingClientRect();
  tip.textContent = mark.dataset.tip;
  tip.hidden = false;
  place({ clientX: box.right, clientY: box.top });
});
document.querySelectorAll("figure[data-svg]").forEach(inline);

// The command on the first slide is typed once; its output is the real one.
const terminal = document.querySelector(".terminal");
if (terminal) {
  const command = terminal.dataset.command;
  const output = terminal.dataset.output;
  const cmd = terminal.querySelector(".cmd");
  const out = terminal.querySelector(".out");
  if (calm || flow.matches) {
    cmd.textContent = command;
    out.textContent = output;
  } else {
    let typed = 0;
    const timer = setInterval(() => {
      cmd.textContent = command.slice(0, ++typed);
      if (typed < command.length) return;
      clearInterval(timer);
      setTimeout(() => { out.textContent = output; }, 450);
    }, 28);
  }
}

// The code slide: copy, and an outline that scrolls to the lines of each step.
const code = document.querySelector(".code pre");
if (code) {
  const lines = [...code.querySelectorAll(".l")];
  document.querySelector("[data-copy]").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    try {
      await navigator.clipboard.writeText(lines.map((line) => line.textContent).join("\n") + "\n");
      button.textContent = "Copied";
    } catch {
      button.textContent = "Select and copy";
    }
    setTimeout(() => { button.textContent = "Copy"; }, 1600);
  });
  document.querySelectorAll(".outline button").forEach((button) => {
    button.addEventListener("click", () => {
      const [from, to] = button.dataset.lines.split("-").map(Number);
      document.querySelectorAll(".outline button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      lines.forEach((line, i) => line.classList.toggle("on", i + 1 >= from && i + 1 <= to));
      code.scrollTo({ top: lines[from - 1].offsetTop - 12, behavior: calm ? "auto" : "smooth" });
    });
  });
}

fit();
fromHash();
